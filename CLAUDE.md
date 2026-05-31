# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`hashy` is a small published PyPI library (`pip install hashy`) providing two things:

1. Hash functions (md5/sha256/sha512) for strings, files, bytes, and complex types (dict/list/set).
2. `cachy` — a persistent, thread/process-safe function-result cache decorator backed by sqlite.

Public API is re-exported from `hashy/__init__.py`. Implementation is split by input type: `string_hash.py`, `file_hash.py`, `bytes.py`, `dls_hash.py` (dict/list/set), and `cache.py` (`cachy`).

## Commands

The `scripts/*.bat` files assume a `venv/` created via `scripts/make_venv_dev.bat` and `cd` up one level (run them from `scripts/`). Direct equivalents:

- Run all tests: `pytest -s test_hashy` (matches CI)
- Run a single test: `pytest -s test_hashy/test_cachy.py::test_cachy_simple`
- Coverage (HTML report): `pytest --cov-report=html --cov` (config in `.coveragerc`)
- Type check: `mypy -m hashy` and `mypy -m test_hashy` (config in `mypy.ini`)
- Lint: `flake8 --ignore=E402,F401,W503,E203,E501 hashy`
- Format: `black -l 192 hashy test_hashy setup.py` (line length 192, not default 88)
- Build + publish: `scripts/pypi.bat` (bdist_wheel + twine upload)

CI (`.github/workflows/python-package.yml`) runs flake8 + `pytest -s test_hashy` on Python 3.10–3.13.

## Key design points

**Hashing complex types (`dls_hash.py`).** Dict/list/set hashes are produced by `dls_sort` → `json_dumps` → string hash. `dls_sort` recursively sorts dicts by key and sorts sets (which have no inherent order), but **preserves list order**. This makes hashes deterministic across runs/processes regardless of dict insertion order or set iteration order. `json_dumps` uses no-whitespace separators and a `convert_serializable_special_cases` default handler for `Enum` (→ name) and `Decimal` (→ int/float). These hashes are hashy-specific and not comparable to external tools — unlike string/file/bytes hashes, which are conventional.

**`cachy` cache keys.** The cache key is `get_dls_sha512([get_dls_sha512(args), get_dls_sha512(kwargs)])` — i.e. arguments are hashed via the dls machinery. This is why arguments don't need to be picklable or hashable in the usual sense, but they DO need to be json-serializable through `dls_sort`/`convert_serializable_special_cases`.

**`cachy` storage layout.** Each decorated function gets its own sqlite file `{cache_dir}/{function_name}_cache.sqlite` (default `cache_dir` is the OS user cache dir via `platformdirs`). Within that file there are up to two `sqlitedict` tables:
- `{function_name}` — the actual cached payloads (lzma-compressed pickle; see `cachy_compress`/`cachy_decompress` and the `USE_COMPRESSION` flag).
- `{function_name}_metadata` — `CacheMetadata` (read/write timestamps), kept separate so updating LRU read-times or expiry doesn't rewrite the (large) payload row. This metadata table is only created/used when `cache_life` or `max_cache_size` is set.

**Concurrency model.** Thread/process safety comes from `sqlitedict` (sqlite itself is not concurrent-safe). `CachyDBDict` forces `journal_mode="WAL"`. Expect transient `sqlite3.OperationalError` (db locked) under concurrent access — the code treats these as non-fatal: the metadata update path retries up to 100 times with jittered sleeps, and commit/VACUUM failures are logged and swallowed. When changing cache code, preserve this "never crash the caller on a locked db" contract.

**Cache eviction / `max_cache_size`.** LRU eviction is driven by on-disk file size (`cache_file_path.stat().st_size`), not entry count. After deleting the least-recently-read entry it runs `VACUUM` to actually shrink the file. `max_cache_size` may be an int or a callable returning an int.

**Counters.** `CacheCounters` (memory hit / hit / miss / expired / eviction) are module-global in `cache.py`, accessed via `get_counters()` / `clear_counters()`. Tests assert exact counter values, so changes to the hit/miss/expiry logic will require updating those assertions.

## Test notes

- `test_hashy/conftest.py` wipes the test cache directory once per session (autouse fixture). Tests that assert counter values also delete their own sqlite file in setup to keep counts deterministic — follow that pattern for new `cachy` tests.
- There is a separate `build/lib/hashy/` tree (build artifact) — edit only the top-level `hashy/` package.
