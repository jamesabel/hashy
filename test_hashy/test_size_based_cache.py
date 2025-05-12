from hashy import cachy
from hashy.cache import get_counters, CacheCounters, clear_counters

from .cache_directory import get_cache_directory


def test_size_based_cache():

    clear_counters()

    @cachy(cache_dir=get_cache_directory(), max_cache_size=200_000)
    def lru_func(_size: int):
        big_data = [x for x in range(_size)]
        return big_data

    # Call the function to generate the cache
    iterations = 100
    for iteration in range(iterations):
        size = iteration * 100
        lru_func(size)

    counters = get_counters()
    # eviction counter is derived empirically (running the test)
    assert counters == CacheCounters(cache_memory_hit_counter=0, cache_hit_counter=0, cache_miss_counter=iterations, cache_expired_counter=0, cache_eviction_counter=68)
