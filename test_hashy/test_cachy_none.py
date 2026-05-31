from pathlib import Path
from datetime import timedelta
import os


from hashy import cachy
from hashy.cache import clear_counters, get_counters

cache_life = timedelta(days=1)

cache_directory = Path(os.environ.get("RUNNER_TEMP", "temp"))  # for GitHub actions


def test_cachy_cache_do_not_cache_none():

    @cachy(cache_life, cache_directory)
    def func_none(p):
        return None

    clear_counters()
    assert func_none(1) is None  # miss
    assert func_none(1) is None  # miss (since function returns None)
    counters = get_counters()
    assert counters.cache_hit_counter == 0
    assert counters.cache_miss_counter == 2


def test_cachy_cache_do_cache_none():

    @cachy(cache_life, cache_directory, True)
    def func_none(p):
        return None

    clear_counters()
    assert func_none(1) is None  # miss
    assert func_none(1) is None  # hit
    counters = get_counters()
    assert counters.cache_hit_counter == 1
    assert counters.cache_miss_counter == 1


def test_cachy_in_memory_do_not_cache_none():
    # With cache_none=False, a None result must not be cached in memory either:
    # every call is a fresh miss and the function is re-run.
    calls = []

    @cachy(cache_dir=cache_directory, in_memory=True)
    def func_none_in_memory(p):
        calls.append(p)
        return None

    clear_counters()
    assert func_none_in_memory(1) is None  # miss
    assert func_none_in_memory(1) is None  # miss again (None is not cached, so it is recomputed)
    counters = get_counters()
    assert counters.cache_memory_hit_counter == 0
    assert counters.cache_hit_counter == 0
    assert counters.cache_miss_counter == 2
    assert len(calls) == 2


def test_cachy_in_memory_cache_none_when_enabled():
    # With cache_none=True, a cached None is a genuine in-memory hit: counted once
    # (not double-counted as memory hit + file hit) and not recomputed.
    calls = []

    @cachy(cache_dir=cache_directory, cache_none=True, in_memory=True)
    def func_none_in_memory_cached(p):
        calls.append(p)
        return None

    clear_counters()
    assert func_none_in_memory_cached(1) is None  # miss -> stored in file + in-memory caches
    assert func_none_in_memory_cached(1) is None  # in-memory hit
    counters = get_counters()
    assert counters.cache_memory_hit_counter == 1
    assert counters.cache_hit_counter == 1
    assert counters.cache_miss_counter == 1
    assert len(calls) == 1
