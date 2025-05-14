import time
from datetime import timedelta

from hashy.cache import cachy, get_counters, clear_counters

from .cache_directory import get_cache_directory

number_of_test_values = 10
outer_iterations = 100
number_of_hits = number_of_test_values * outer_iterations

def _check_counters():
    counters = get_counters()
    assert counters.cache_hit_counter == number_of_hits
    assert counters.cache_memory_hit_counter == number_of_hits
    assert counters.cache_miss_counter == number_of_test_values
    print(f"{counters=}")

def test_cachy_memory_performance_infinite_cache_life():
    """
    Test the performance of cachy with in_memory=True and no cache_life (infinite). This will be the fastest read time.
    :return:
    """

    # in_memory=True with no cache_life (infinite) is fastest
    @cachy(cache_dir=get_cache_directory(), in_memory=True)
    def memory_performance_function_infinite(x: int) -> int:
        return x + 1

    clear_counters()

    # warm the cache
    for i in range(number_of_test_values):
        memory_performance_function_infinite(i)
    start_time  = time.time()

    for outer in range(outer_iterations):
        # read the cache
        for i in range(number_of_test_values):
            v = memory_performance_function_infinite(i)
            assert v == i + 1, f"Expected {i + 1}, got {v}"
    end_time = time.time()
    duration = end_time - start_time

    _check_counters()

    read_time = duration / (number_of_test_values * outer_iterations)
    print(f"infinite cache life: {duration=:.2f},{read_time=:f}")
    assert read_time < 0.002, f"Read time {read_time} is too high"  # 0.000438 seen


def test_cachy_memory_performance_finite_cache_life():
    """
    Test the performance of cachy with in_memory=True and cache_life=timedelta(hours=1). This will be slower than infinite cache life.
    :return:
    """

    # in_memory=True with cache life
    @cachy(cache_life=timedelta(hours=1), cache_dir=get_cache_directory(), in_memory=True)
    def memory_performance_function_finite(x: int) -> int:
        return x + 1

    clear_counters()

    # warm the cache
    for i in range(number_of_test_values):
        memory_performance_function_finite(i)
    start_time  = time.time()

    for outer in range(outer_iterations):
        # read the cache
        for i in range(number_of_test_values):
            v = memory_performance_function_finite(i)
            assert v == i + 1, f"Expected {i + 1}, got {v}"
    end_time = time.time()
    duration = end_time - start_time

    counters = get_counters()

    assert counters.cache_hit_counter == number_of_hits
    assert counters.cache_memory_hit_counter == number_of_hits
    assert counters.cache_miss_counter == number_of_test_values
    print(f"{counters=}")

    read_time = duration / (number_of_test_values * outer_iterations)
    print(f"non-infinite cache life: {duration=:.2f},{read_time=:f}")
    assert read_time < 0.02, f"Read time {read_time} is too high"  # 0.006736 seen