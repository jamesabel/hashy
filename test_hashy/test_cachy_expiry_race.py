"""
Regression tests for cross-process races in cachy's expiry / LRU-touch path.

The primary tests are deterministic: they use a mapping that behaves exactly as the
metadata table looks to a process that *lost* a race (another process deleted or wrote
the key between this process's check and its act). A real multiprocess hammer is
timing-dependent, so it is only a cheap smoke test at the end.
"""

import time
from concurrent.futures import ProcessPoolExecutor
from datetime import timedelta
from pathlib import Path
import shutil

from hashy import cachy
from hashy.cache import _CachyCache, CacheMetadata, clear_counters, get_counters

from .cache_directory import get_cache_directory


class _FakeMetadataDB(dict):
    """Minimal stand-in for the sqlitedict metadata table (context-manager + commit)."""

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _LostDeleteRaceDB(_FakeMetadataDB):
    """The key looks present, but another process deletes it before our delete runs (sqlitedict raises KeyError)."""

    def __delitem__(self, key):
        raise KeyError(key)


class _LostWriteRaceDB(_FakeMetadataDB):
    """The key is absent on the first membership test, but another process writes it before any later test."""

    def __init__(self):
        super().__init__()
        self.contains_calls = 0
        self.writes = 0

    def __contains__(self, key):
        self.contains_calls += 1
        return self.contains_calls > 1  # absent the first time, present afterwards

    def __setitem__(self, key, value):
        self.writes += 1
        super().__setitem__(key, value)


def _make_cache(name: str, **kwargs) -> _CachyCache:
    def func(x):
        return x + 1

    func.__name__ = name
    cache_dir = Path(get_cache_directory(), "expiry_race")
    cache_dir.mkdir(parents=True, exist_ok=True)
    Path(cache_dir, f"{name}_cache.sqlite").unlink(missing_ok=True)
    defaults = dict(cache_life=timedelta(seconds=0), cache_none=False, in_memory=True, max_cache_size=None)
    defaults.update(kwargs)
    return _CachyCache(func, cache_dir, **defaults)


def test_expire_entry_tolerates_concurrent_delete():
    """Losing the expiry race (key already deleted by another process) must not raise, and must not count as an expiry."""
    clear_counters()
    cache = _make_cache("expire_race_func")
    key = "somekey"
    cache.in_memory_cache[key] = b"stale"

    metadata_db = _LostDeleteRaceDB({key: CacheMetadata()})
    cache._expire_entry(metadata_db, key)  # must not raise

    assert get_counters().cache_expired_counter == 0  # the other process did the expiring
    assert key not in cache.in_memory_cache  # the stale in-memory copy is still dropped


def test_expire_entry_counts_own_delete():
    """When this process's delete actually runs, the expiry is counted exactly once."""
    clear_counters()
    cache = _make_cache("expire_own_func")
    key = "somekey"

    metadata_db = _FakeMetadataDB({key: CacheMetadata()})
    cache._expire_entry(metadata_db, key)

    assert key not in metadata_db
    assert get_counters().cache_expired_counter == 1


def test_expire_and_touch_tolerates_concurrent_write():
    """A key written by another process after our absent-check must not be LRU-touched (previously dereferenced None)."""
    cache = _make_cache("touch_race_func", cache_life=None, max_cache_size=10_000_000)
    metadata_db = _LostWriteRaceDB()

    cache._expire_and_touch_once(metadata_db, "somekey")  # must not raise

    assert metadata_db.writes == 0  # nothing to touch: we never read a row for this key


def test_expire_and_touch_does_not_resurrect_expired_entry():
    """An entry this process just expired must not be touched back into the metadata table."""
    clear_counters()
    cache = _make_cache("resurrect_race_func", cache_life=timedelta(seconds=0), max_cache_size=10_000_000)
    key = "somekey"
    metadata_db = _FakeMetadataDB({key: CacheMetadata()})
    time.sleep(0.01)  # ensure the entry is past its (zero) cache life

    cache._expire_and_touch_once(metadata_db, key)

    assert key not in metadata_db
    assert get_counters().cache_expired_counter == 1


# -- multiprocess smoke ------------------------------------------------------

_smoke_cache_dir = Path("temp", "test_cachy_expiry_race_smoke")


@cachy(cache_life=timedelta(seconds=0), cache_dir=_smoke_cache_dir)
def _always_expired(x):
    return x + 1


def _smoke_worker(start_time: float) -> int:
    """Wait for the common start time, then hammer an always-expired entry; return the number of calls made."""
    while time.time() < start_time:
        pass
    calls = 0
    for _iteration in range(50):
        assert _always_expired(1) == 2
        calls += 1
    return calls


def test_cachy_expiry_multiprocess_smoke():
    """Several processes expiring the same entry concurrently must all complete without raising."""
    shutil.rmtree(_smoke_cache_dir, ignore_errors=True)
    _smoke_cache_dir.mkdir(parents=True, exist_ok=True)
    assert _always_expired(1) == 2  # create the cache file (and set WAL mode) before the workers pile onto it

    workers = 4
    with ProcessPoolExecutor(max_workers=workers) as executor:
        start_time = time.time() + 2.0  # give the workers time to spin up so they start together
        results = list(executor.map(_smoke_worker, [start_time] * workers))

    assert results == [50] * workers
