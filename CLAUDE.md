# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`hashy` is a small published PyPI library (`pip install hashy`) providing two things:

1. Hash functions (md5/sha256/sha512) for strings, files, bytes, and complex types (dict/list/set).
2. `cachy` — a persistent, thread/process-safe function-result cache decorator backed by sqlite.

Public API is re-exported from `hashy/__init__.py`. Implementation is split by input type: `string_hash.py`, `file_hash.py`, `bytes.py`, `dls_hash.py` (dict/list/set), and `cache.py` (`cachy`).

## Commands

The project is managed with `uv`; all packaging and tool configuration lives in `pyproject.toml` (hatchling build backend, version read from `hashy/__version__.py`) and dependencies are pinned in `uv.lock`. There is no `setup.py` or requirements file.

- Set up / update the environment (`.venv`): `uv sync`
- Run all tests: `uv run pytest -s test_hashy` (matches CI)
- Run a single test: `uv run pytest -s test_hashy/test_cachy.py::test_cachy_simple`
- Coverage (HTML report): `uv run pytest --cov-report=html --cov` (config in `[tool.coverage.run]`)
- Type check: `uv run ty check` (checks `hashy` only, per `[tool.ty.src]`)
- Lint: `uv run ruff check` (ruff's default rule set; `--fix` to apply fixes)
- Format: `uv run ruff format` (line length 192, not default 88)
- Add a dependency: `uv add <pkg>` (runtime) or `uv add --dev <pkg>`; commit the updated `uv.lock`
- Build: `uv build`. Publish to PyPI: publish a GitHub release (or run the `Publish to PyPI` workflow); `.github/workflows/publish.yml` builds and uploads with Provenance through a PyPI trusted publisher. Never upload from a workstation, which cannot produce Provenance.

CI (`.github/workflows/python-package.yml`) runs ruff (lint + format check), ty and `pytest -s test_hashy` on every released Python from the minimum supported (3.12, set by `msqlite`) through the latest stable release (3.15), plus the 3.16 pre-release and free-threaded 3.14t and 3.15t.

**Free-threaded Python.** hashy supports it. On a free-threaded build the top-level `conftest.py` imports `gilguard` (a dev dependency), which fails the test run if any import re-enables the GIL; CI also runs `python -m gilguard` there. gilguard raises on a GIL build, so it is never imported on one. To test locally: `uv run --python 3.14t pytest test_hashy` (use a separate `UV_PROJECT_ENVIRONMENT` to keep `.venv` as it is). In-process shared state must stay safe without the GIL: update counters only through `CacheCounters.increment()` (locked; `+=` loses counts), and read the in-memory cache with a single lookup, never check-then-read.

Inside the package, import from the defining submodule (`from .dls_hash import ...`), never from `hashy` itself: ruff sorts the imports in `hashy/__init__.py`, so nothing may depend on their order.

## Key design points

**Hashing complex types (`dls_hash.py`).** Dict/list/set hashes are produced by `dls_sort` → `json_dumps` → string hash. `dls_sort` recursively sorts dicts by key and sorts sets (which have no inherent order), but **preserves list order**. This makes hashes deterministic across runs/processes regardless of dict insertion order or set iteration order. `json_dumps` uses no-whitespace separators and a `convert_serializable_special_cases` default handler for `Enum` (→ name) and `Decimal` (→ int/float). These hashes are hashy-specific and not comparable to external tools — unlike string/file/bytes hashes, which are conventional.

**`cachy` cache keys.** The cache key is `get_dls_sha512([get_dls_sha512(args), get_dls_sha512(kwargs)])` — i.e. arguments are hashed via the dls machinery. This is why arguments don't need to be picklable or hashable in the usual sense, but they DO need to be json-serializable through `dls_sort`/`convert_serializable_special_cases`.

**`cachy` storage layout.** Each decorated function gets its own sqlite file `{cache_dir}/{function_name}_cache.sqlite` (default `cache_dir` is the OS user cache dir via `platformdirs`). Within that file there are up to two tables, each accessed through a mapping-style view class:
- `{function_name}` (`CachyDBDict`, `key TEXT PRIMARY KEY, value BLOB`) — the actual cached payloads (lzma-compressed pickle; see `cachy_compress`/`cachy_decompress` and the `USE_COMPRESSION` flag).
- `{function_name}_metadata` (`CachyMetadataDBDict`, `key, read_timestamp REAL, write_timestamp REAL`) — `CacheMetadata`, kept separate so updating LRU read-times or expiry doesn't rewrite the (large) payload row. This metadata table is only created/used when `cache_life` or `max_cache_size` is set.

The file's layout version is stamped in `PRAGMA user_version` (`CACHE_FORMAT_VERSION`); a file in any other version (e.g. the pickled `sqlitedict` tables hashy < 0.15 wrote) has its tables dropped and recreated on first use.

**Unreadable entries are misses.** `cachy_decompress` converts every exception in `_UNREADABLE_PAYLOAD_ERRORS` into `CacheReadError`, and both read paths answer that by logging a WARNING, discarding the entry and recomputing. The tuple covers corruption, transient OOM, and a pickle whose class has moved, been removed or changed shape (`ImportError`, `AttributeError`, `ValueError`, `TypeError`). A cache must never make a call fail that would have succeeded without it. A class whose shape changed in a way that still unpickles is not detectable; callers version their cache key for that.

**Concurrency model.** Thread/process safety comes from `msqlite` (sqlite itself is not concurrent-safe). Every view read is its own read transaction and every write its own `BEGIN IMMEDIATE` write transaction (WAL mode, nothing held open while the decorated function computes). A view holds one connection for the span of its `with` block and closes it on exit, so no connection outlives a call: hashy's tests delete cache files between calls, which Windows refuses while a connection is open. `msqlite` retries `database is locked` with jittered backoff for up to `LOCK_TIMEOUT_S` (30 s) and then raises `MSQLiteTimeoutError`; `_CachyCache` catches that at each cache operation, logs a WARNING (a lost store also increments `cache_store_failed_counter`) and the caller still gets its result. Any other `sqlite3.OperationalError` is a real fault and propagates. When changing cache code, preserve this "never crash the caller on a locked db, never lose a store silently" contract, and never nest a write transaction inside another on the same thread (it would wait on itself until the timeout).

**Cache eviction / `max_cache_size`.** LRU eviction is driven by on-disk file size (`cache_file_path.stat().st_size`), not entry count. After deleting the least-recently-read entry it runs `VACUUM` to actually shrink the file. `max_cache_size` may be an int or a callable returning an int.

**Counters.** `CacheCounters` (memory hit / hit / miss / expired / eviction) are module-global in `cache.py`, accessed via `get_counters()` / `clear_counters()` and incremented only through the locked `CacheCounters.increment()`. Tests assert exact counter values, so changes to the hit/miss/expiry logic will require updating those assertions.

## Test notes

- `test_hashy/conftest.py` wipes the test cache directory once per session (autouse fixture). Tests that assert counter values also delete their own sqlite file in setup to keep counts deterministic — follow that pattern for new `cachy` tests.
- There is a separate `build/lib/hashy/` tree (build artifact) — edit only the top-level `hashy/` package.
