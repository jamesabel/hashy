from pathlib import Path
from datetime import timedelta
import os


from hashy import cachy
from hashy.cache import clear_counters, get_counters, CacheCounters

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