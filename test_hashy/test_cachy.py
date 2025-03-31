import time
from pathlib import Path
from datetime import timedelta
import os
from pprint import pformat
from typing import List
import math

from hashy import cachy
from hashy.cache import get_cache_dir, CacheCounters, clear_counters, get_counters

cache_life = timedelta(days=1)


def get_cache_directory() -> Path:
    cache_directory = Path(os.environ.get("RUNNER_TEMP", "temp"))  # for GitHub actions
    return cache_directory


def test_a_cachy_zero_life():

    clear_counters()

    @cachy(timedelta(seconds=0), get_cache_directory())
    def func(p):
        return p

    assert func(1) == 1
    assert get_counters() == CacheCounters(cache_memory_hit_counter=0, cache_hit_counter=0, cache_miss_counter=1, cache_expired_counter=0)
    time.sleep(0.1)  # cache will expire
    assert func(1) == 1
    assert get_counters() == CacheCounters(cache_memory_hit_counter=0, cache_hit_counter=0, cache_miss_counter=2, cache_expired_counter=1)


def test_cachy_simple():

    @cachy(cache_life, get_cache_directory())
    def cachy_simple_func(p):
        return p

    clear_counters()
    # delete the DB so the cache counts are correct
    if (glob_results := list(get_cache_directory().glob("cachy_simple_func*"))) and len(glob_results) > 0:
        glob_results[0].unlink(missing_ok=True)

    assert cachy_simple_func(1) == 1
    assert get_counters() == CacheCounters(cache_memory_hit_counter=0, cache_hit_counter=0, cache_miss_counter=1, cache_expired_counter=0)
    assert cachy_simple_func(1) == 1
    assert get_counters() == CacheCounters(cache_memory_hit_counter=0, cache_hit_counter=1, cache_miss_counter=1, cache_expired_counter=0)
    assert cachy_simple_func(1) == 1
    assert get_counters() == CacheCounters(cache_memory_hit_counter=0, cache_hit_counter=2, cache_miss_counter=1, cache_expired_counter=0)
    assert cachy_simple_func(2) == 2
    assert get_counters() == CacheCounters(cache_memory_hit_counter=0, cache_hit_counter=2, cache_miss_counter=2, cache_expired_counter=0)
    assert cachy_simple_func(2) == 2
    assert get_counters() == CacheCounters(cache_memory_hit_counter=0, cache_hit_counter=3, cache_miss_counter=2, cache_expired_counter=0)
    assert pformat(get_counters()) == "cache_memory_hit_counter=0,cache_hit_counter=3,cache_miss_counter=2,cache_expired_counter=0"


def test_cachy_simple_in_memory():

    @cachy(cache_life, get_cache_directory(), in_memory=True)
    def cachy_simple_func(p):
        return p

    clear_counters()
    # delete the DB so the cache counts are correct
    if (glob_results := list(get_cache_directory().glob("cachy_simple_func*"))) and len(glob_results) > 0:
        glob_results[0].unlink(missing_ok=True)

    assert cachy_simple_func(1) == 1
    assert get_counters() == CacheCounters(cache_memory_hit_counter=0, cache_hit_counter=0, cache_miss_counter=1, cache_expired_counter=0)
    assert cachy_simple_func(1) == 1
    assert get_counters() == CacheCounters(cache_memory_hit_counter=1, cache_hit_counter=1, cache_miss_counter=1, cache_expired_counter=0)
    assert cachy_simple_func(1) == 1
    assert get_counters() == CacheCounters(cache_memory_hit_counter=2, cache_hit_counter=2, cache_miss_counter=1, cache_expired_counter=0)
    assert cachy_simple_func(2) == 2
    assert get_counters() == CacheCounters(cache_memory_hit_counter=2, cache_hit_counter=2, cache_miss_counter=2, cache_expired_counter=0)
    assert cachy_simple_func(2) == 2
    assert get_counters() == CacheCounters(cache_memory_hit_counter=3, cache_hit_counter=3, cache_miss_counter=2, cache_expired_counter=0)
    assert pformat(get_counters()) == "cache_memory_hit_counter=3,cache_hit_counter=3,cache_miss_counter=2,cache_expired_counter=0"


def test_cachy_dict():
    @cachy(cache_life, get_cache_directory())
    def func(p):
        return p

    data = {"a": 1, "b": 2}
    assert func(data) == data
    assert func(data) == data


def test_cachy_performance_small_data():
    # test that cachy is actually caching

    clear_counters()

    short_time = 0.05
    long_time = 10.0 * short_time

    @cachy(cache_life, get_cache_directory())
    def takes_a_long_time(p):
        time.sleep(1.5 * long_time)
        return p

    data = {"a": 1, "b": 2}

    start = time.time()
    assert takes_a_long_time(data) == data
    duration = time.time() - start
    # print(f"{duration=}")
    assert long_time <= duration

    start = time.time()
    assert takes_a_long_time(data) == data
    duration = time.time() - start
    # print(f"{duration=}")
    assert duration < short_time


def test_cachy_performance_time_consuming_data_calculation():

    clear_counters()

    # cache in DB (not in memory)
    @cachy(cache_life, get_cache_directory())
    def time_consuming_data_calculation(n):
        result = sum([math.sin(i) for i in range(int(n))])
        return result

    start = time.time()
    big_n = int(1e7)
    time_consuming_data_calculation(big_n)
    cold_duration = 1000.0 * (time.time() - start)  # mS

    start = time.time()
    time_consuming_data_calculation(big_n)
    warm_duration = 1000.0 * (time.time() - start)  # mS

    speedup = cold_duration / warm_duration
    print(f"{cold_duration=:.2f} mS,{warm_duration=:.2f} mS,{speedup=:.2f}x")

    assert speedup > 20  # speedup for using DB (109x has been seen)


def test_cachy_performance_time_consuming_data_calculation_in_memory():

    clear_counters()

    # cache in memory (no cache life given = infinite)
    @cachy(cache_dir=get_cache_directory(), in_memory=True)
    def time_consuming_data_calculation_in_memory(n):
        result = sum([math.sin(i) for i in range(int(n))])
        return result

    start = time.time()
    big_n = int(1e7)
    time_consuming_data_calculation_in_memory(big_n)
    cold_duration = 1000.0 * (time.time() - start)  # mS

    start = time.time()
    time_consuming_data_calculation_in_memory(big_n)
    warm_duration = 1000.0 * (time.time() - start)  # mS

    speedup = cold_duration / warm_duration
    print(f"{cold_duration=:.2f} mS,{warm_duration=:.2f} mS,{speedup=:.2f}x")

    assert speedup > 1000  # speedup for in-memory caching (7500x has been seen)


def test_cachy_complex():
    @cachy(cache_life, get_cache_directory())
    def func(a, b, c):
        return [a, b, c]

    data = {"a": 1, "b": 2}
    assert func(data, data, c=data) == [data, data, data]


def test_get_cache_dir():
    assert isinstance(get_cache_dir(), Path)


def test_cachy_dir_default_quick():
    @cachy(timedelta(seconds=1))
    def func(a):
        return a + a

    assert func(2) == 4
    assert func(2) == 4


def test_cachy_dir_default_slow():
    @cachy(timedelta(days=1))
    def func(a):
        return a + a

    assert func(2) == 4
    assert func(2) == 4


def test_cachy_all_defaults():

    clear_counters()

    @cachy(cache_dir=get_cache_directory())
    def func(a):
        time.sleep(0.1)
        return a + a

    time_a = time.time()
    assert func(2) == 4
    time_b = time.time()
    assert func(2) == 4
    time_c = time.time()
    duration_a = time_b - time_a
    duration_b = time_c - time_b
    assert duration_a > 2 * duration_b


def test_cachy_different_values():

    clear_counters()

    @cachy(cache_dir=get_cache_directory())
    def func(a):
        time.sleep(0.1)
        return a + a

    assert func(2) == 4
    assert func(3) == 6
    assert func(2) == 4


def test_cachy_big_data():

    @cachy(cache_life, get_cache_directory())
    def big_to_little(a: List[int]) -> int:
        return len(a)

    @cachy(cache_life, get_cache_directory())
    def little_to_big(a: int) -> List[int]:
        return [v for v in range(a)]

    clear_counters()
    for n in (100, int(1e6)):
        data = [v for v in range(n)]

        # bools since if there's a mis-compare the diff will be printed which takes a really long time
        assert bool(big_to_little(data) == n)
        assert bool(little_to_big(n) == data)
        assert bool(little_to_big(n) == data)
        assert bool(little_to_big(n) == data)
        assert bool(big_to_little(data) == n)

    assert get_counters() == CacheCounters(cache_memory_hit_counter=0, cache_hit_counter=6, cache_miss_counter=4, cache_expired_counter=0)
