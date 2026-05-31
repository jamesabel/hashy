from pathlib import Path

import pytest

from hashy import cachy
from hashy.cache import CachyDBDict, cachy_decompress, CacheReadError, clear_counters, get_counters

from .cache_directory import get_cache_directory


def test_cachy_decompress_raises_on_garbage():
    # Not valid lzma/pickle data -> should be reported as an unreadable cache entry, not a raw lzma/pickle error.
    with pytest.raises(CacheReadError):
        cachy_decompress(b"this is not valid lzma data")


def test_compress_decompress_passthrough_without_compression(monkeypatch):
    # When compression is disabled, compress/decompress are pass-throughs.
    import hashy.cache as cache_mod

    monkeypatch.setattr(cache_mod, "USE_COMPRESSION", False)

    data = {"a": 1, "b": [1, 2, 3]}
    out = cache_mod.cachy_compress(data)
    assert out is data  # no transformation when compression is off
    assert cache_mod.cachy_decompress(out) == data


def test_cachy_discards_corrupt_file_entry():
    cache_dir = get_cache_directory()

    calls = []

    @cachy(cache_dir=cache_dir)
    def corrupt_file_func(p):
        calls.append(p)
        return p * 10

    clear_counters()

    assert corrupt_file_func(5) == 50  # miss -> compute + store
    assert corrupt_file_func(5) == 50  # hit -> no recompute
    assert len(calls) == 1
    assert get_counters().cache_hit_counter == 1

    # Corrupt every stored payload in the cache table so decompression fails.
    cache_file_path = Path(cache_dir, "corrupt_file_func_cache.sqlite")
    with CachyDBDict(cache_file_path, "corrupt_file_func") as db:
        for k in list(db.keys()):
            db[k] = b"not-valid-lzma-garbage"
        db.commit()

    # The corrupt entry is detected, discarded, and the value recomputed (counts as a miss).
    clear_counters()
    assert corrupt_file_func(5) == 50
    assert len(calls) == 2
    assert get_counters().cache_miss_counter == 1

    # The bad entry was replaced with a valid one, so the next call is a clean hit (no recompute).
    assert corrupt_file_func(5) == 50
    assert len(calls) == 2
    assert get_counters().cache_hit_counter == 1


def test_cachy_discards_corrupt_in_memory_entry(monkeypatch):
    cache_dir = get_cache_directory()

    calls = []

    @cachy(cache_dir=cache_dir, in_memory=True)
    def corrupt_mem_func(p):
        calls.append(p)
        return p + 1

    clear_counters()

    assert corrupt_mem_func(7) == 8  # miss -> compute + store (db and in-memory)
    assert len(calls) == 1

    # Make only the next decompress call (the in-memory read) raise, then behave normally for the file read.
    import hashy.cache as cache_mod

    real_decompress = cache_mod.cachy_decompress
    state = {"first": True}

    def flaky_decompress(data):
        if state["first"]:
            state["first"] = False
            raise CacheReadError("simulated unreadable in-memory entry")
        return real_decompress(data)

    monkeypatch.setattr(cache_mod, "cachy_decompress", flaky_decompress)

    clear_counters()
    # In-memory read raises -> entry discarded -> falls through to the (valid) file cache -> hit, no recompute.
    assert corrupt_mem_func(7) == 8
    assert len(calls) == 1
    assert get_counters().cache_hit_counter == 1


def test_cachy_callable_max_cache_size():
    # max_cache_size may be a callable that returns the limit; exercise that branch.
    clear_counters()

    @cachy(cache_dir=get_cache_directory(), max_cache_size=lambda: 200_000)
    def callable_lru_func(_size):
        return list(range(_size))

    iterations = 100
    for iteration in range(iterations):
        callable_lru_func(iteration * 100)

    counters = get_counters()
    assert counters.cache_miss_counter == iterations
    assert counters.cache_hit_counter == 0
