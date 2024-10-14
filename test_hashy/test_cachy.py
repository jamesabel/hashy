import time
from pathlib import Path
from datetime import timedelta
import os
import shutil
from pprint import pformat
from typing import List

from hashy import cachy
from hashy.cache import get_cache_dir, CacheCounters, clear_counters, get_counters

cache_life = timedelta(days=1)

cache_directory = Path(os.environ.get("RUNNER_TEMP", "temp"))  # for GitHub actions


def rm_cache_dir():
    shutil.rmtree(cache_directory, ignore_errors=True)


def test_a_cachy_zero_life():
    rm_cache_dir()
    clear_counters()

    @cachy(timedelta(seconds=0), cache_directory)
    def func(p):
        return p

    assert func(1) == 1
    assert get_counters() == CacheCounters(cache_hit_counter=0, cache_miss_counter=1, cache_load_counter=0, cache_expired_counter=0)
    time.sleep(0.1)  # cache will expire
    assert func(1) == 1
    assert get_counters() == CacheCounters(cache_hit_counter=0, cache_miss_counter=2, cache_load_counter=0, cache_expired_counter=1)


def test_cachy_simple():
    rm_cache_dir()
    clear_counters()

    @cachy(cache_life, cache_directory)
    def func(p):
        return p

    assert func(1) == 1
    assert get_counters() == CacheCounters(cache_hit_counter=0, cache_miss_counter=1, cache_load_counter=0, cache_expired_counter=0)
    assert func(1) == 1
    assert get_counters() == CacheCounters(cache_hit_counter=1, cache_miss_counter=1, cache_load_counter=0, cache_expired_counter=0)
    assert func(1) == 1
    assert get_counters() == CacheCounters(cache_hit_counter=2, cache_miss_counter=1, cache_load_counter=0, cache_expired_counter=0)
    assert func(2) == 2
    assert get_counters() == CacheCounters(cache_hit_counter=2, cache_miss_counter=2, cache_load_counter=0, cache_expired_counter=0)
    assert func(2) == 2
    assert get_counters() == CacheCounters(cache_hit_counter=3, cache_miss_counter=2, cache_load_counter=0, cache_expired_counter=0)
    assert pformat(get_counters()) == "cache_hit_counter=3,cache_miss_counter=2,cache_load_counter=0,cache_expired_counter=0"


def test_cachy_dict():
    @cachy(cache_life, cache_directory)
    def func(p):
        return p

    data = {"a": 1, "b": 2}
    assert func(data) == data
    assert func(data) == data


def test_cachy_performance():
    # test that cachy is actually caching

    rm_cache_dir()
    clear_counters()

    short_time = 0.01
    long_time = 0.1

    @cachy(cache_life, cache_directory)
    def takes_a_long_time(p):
        time.sleep(1.01 * long_time)
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


def test_cachy_complex():
    @cachy(cache_life, cache_directory)
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

    rm_cache_dir()
    clear_counters()

    @cachy(cache_dir=cache_directory)
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

    rm_cache_dir()
    clear_counters()

    @cachy(cache_dir=cache_directory)
    def func(a):
        time.sleep(0.1)
        return a + a

    assert func(2) == 4
    assert func(3) == 6
    assert func(2) == 4


def test_cachy_big_data():

    @cachy(cache_life, cache_directory)
    def big_to_little(a: List[int]) -> int:
        return len(a)

    @cachy(cache_life, cache_directory)
    def little_to_big(a: int) -> List[int]:
        return [v for v in range(a)]

    rm_cache_dir()
    clear_counters()
    for n in (100, 1000):
        data = [v for v in range(n)]

        # bools since if there's a mis-compare the diff will be printed which takes a really long time
        assert bool(big_to_little(data) == n)
        assert bool(little_to_big(n) == data)
        assert bool(little_to_big(n) == data)
        assert bool(little_to_big(n) == data)
        assert bool(big_to_little(data) == n)

    assert get_counters() == CacheCounters(cache_hit_counter=6, cache_miss_counter=4, cache_load_counter=0, cache_expired_counter=0)
