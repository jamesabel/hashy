from hashy import cachy
from hashy.cache import get_counters, clear_counters

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
    # Each of the `iterations` calls uses a distinct argument, so every call is a miss
    # and nothing is ever served from cache. These totals are deterministic.
    assert counters.cache_memory_hit_counter == 0
    assert counters.cache_hit_counter == 0
    assert counters.cache_miss_counter == iterations
    assert counters.cache_expired_counter == 0
    # The exact eviction count is environment-dependent (it is driven by the on-disk
    # sqlite file size, which varies with sqlite page size, lzma compression and VACUUM
    # behavior across platforms / Python versions), so assert that LRU eviction actually
    # happened and that it did not evict everything, rather than pinning an empirically
    # observed magic number.
    assert 0 < counters.cache_eviction_counter < iterations
