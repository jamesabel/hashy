from typing import Callable, Any, Union, Dict
from functools import wraps
from pathlib import Path
from datetime import timedelta
from logging import getLogger
import time
import sqlite3

from platformdirs import user_cache_dir
from sqlitedict import SqliteDict

from . import __application_name__, __author__, get_dls_sha512

log = getLogger(__name__)


class CacheMetadata:
    """
    Metadata for a cache entry, including read and write timestamps.
    """

    def __init__(self):
        now = time.time()  # if both are None, use one value for both
        self.read_timestamp = now
        self.write_timestamp = now


# Global counters, handy for testing
class CacheCounters:
    """
    Cache counters for cache hits, misses, expired entries, and evictions.
    """

    def __init__(self, cache_memory_hit_counter=0, cache_hit_counter=0, cache_miss_counter=0, cache_expired_counter=0, cache_eviction_counter=0):
        self.cache_memory_hit_counter = cache_memory_hit_counter
        self.cache_hit_counter = cache_hit_counter
        self.cache_miss_counter = cache_miss_counter
        self.cache_expired_counter = cache_expired_counter
        self.cache_eviction_counter = cache_eviction_counter

    def __repr__(self):
        values = [
            f"cache_memory_hit_counter={self.cache_memory_hit_counter}",
            f"cache_hit_counter={self.cache_hit_counter}",
            f"cache_miss_counter={self.cache_miss_counter}",
            f"cache_expired_counter={self.cache_expired_counter}",
            f"cache_eviction_counter={self.cache_eviction_counter}",
        ]
        return ",".join(values)

    def __eq__(self, other):
        return (
            self.cache_memory_hit_counter == other.cache_memory_hit_counter
            and self.cache_hit_counter == other.cache_hit_counter
            and self.cache_miss_counter == other.cache_miss_counter
            and self.cache_expired_counter == other.cache_expired_counter
            and self.cache_eviction_counter == other.cache_eviction_counter
        )

    def clear(self):
        self.cache_memory_hit_counter = 0
        self.cache_hit_counter = 0
        self.cache_miss_counter = 0
        self.cache_expired_counter = 0
        self.cache_eviction_counter = 0


_cache_counters = CacheCounters()


def get_cache_dir() -> Path:
    """
    Get the cache directory for this application.
    :return: Path to the cache directory
    """
    cache_dir = Path(user_cache_dir(__application_name__, __author__))
    return cache_dir


def cachy(
    cache_life: Union[timedelta, None] = None, cache_dir: Path = get_cache_dir(), cache_none: bool = False, in_memory: bool = False, max_cache_size: int | Callable | None = None
) -> Callable:
    """
    Decorator to persistently cache the results of a function call, with a cache life.
    :param cache_life: Cache life.
    :param cache_dir: Cache directory.
    :param cache_none: Cache None results (default is to not cache None results).
    :param in_memory: If True, use an in-memory cache (default is to use a file-based cache).
    :param max_cache_size: Maximum size of the cache as an int, or a callable that returns max cache size, or None (default is None, which means no limit)
    """

    def decorator(func: Callable) -> Callable:

        function_name = func.__name__
        in_memory_cache: Dict[str, Any] = {}

        # Create a cache file path based on the function name
        cache_file_path = Path(cache_dir, f"{function_name}_cache.sqlite")

        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:

            key = get_dls_sha512([get_dls_sha512(list(args)), get_dls_sha512(kwargs)])

            try:
                cache_file_path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                log.info(f'Error creating cache directory: "{e}"')

            metadata_table_name = f"{function_name}_metadata"

            # If an entry has expired, delete it from the cache.
            # Keep the metadata in a separate table so that when we update the metadata, we don't have to write the payload (since we're using SqliteDict, we have to write the entire row)
            with SqliteDict(cache_file_path, metadata_table_name) as metadata_db:
                key_in_metadata_db = key in metadata_db  # do once for performance
                if key_in_metadata_db:
                    try:
                        row_metadata = metadata_db[key]
                    except (KeyError, TypeError):
                        # can happen if the cache is an old format
                        row_metadata = CacheMetadata()
                    write_ts = row_metadata.write_timestamp
                else:
                    write_ts = 0.0  # force a cache miss
                if cache_life is not None and time.time() - write_ts >= cache_life.total_seconds():
                    # entry has expired
                    if key_in_metadata_db:
                        _cache_counters.cache_expired_counter += 1
                        del metadata_db[key]
                        metadata_db.commit()
                    with SqliteDict(cache_file_path, function_name) as db:
                        if key in db:
                            del db[key]
                            db.commit()
                elif key_in_metadata_db:
                    # update read time
                    row_metadata.read_timestamp = time.time()
                    metadata_db[key] = row_metadata
                    metadata_db.commit()

            # use in-memory cache, if enabled
            result = None
            if in_memory and key in in_memory_cache:
                _cache_counters.cache_memory_hit_counter += 1
                _cache_counters.cache_hit_counter += 1
                result = in_memory_cache[key]

            cache_write = False
            cache_hit = False
            if result is None:
                # use file-based cache
                with SqliteDict(cache_file_path, function_name) as db:
                    if key in db:
                        cache_hit = True
                        _cache_counters.cache_hit_counter += 1
                        result = db[key]
                    else:
                        _cache_counters.cache_miss_counter += 1
                        result = func(*args, **kwargs)
                        if result is not None or cache_none:
                            db[key] = result
                            try:
                                db.commit()
                            except sqlite3.OperationalError:
                                log.info(f'Commit failed for "{function_name}", probably because "{cache_file_path}" is locked. This is expected if multiple processes are using the cache.')
                        if in_memory:
                            in_memory_cache[key] = result
                        cache_write = True

            # update write timestamp
            if cache_write:
                with SqliteDict(cache_file_path, metadata_table_name) as metadata_db:
                    metadata_db[key] = CacheMetadata()
                    try:
                        metadata_db.commit()
                    except sqlite3.OperationalError:
                        log.info(f'Commit failed for "{function_name}", probably because "{cache_file_path}" is locked. This is expected if multiple processes are using the cache.')
            elif cache_hit:
                # update read timestamp
                with SqliteDict(cache_file_path, metadata_table_name) as metadata_db:
                    if (row_metadata := metadata_db.get(key)) is None:
                        log.info(f"Cache hit, but no metadata found for {key}. This is unexpected.")
                    else:
                        row_metadata.read_timestamp = time.time()
                        metadata_db[key] = row_metadata
                        metadata_db.commit()

            # LRU cache
            if isinstance(max_cache_size, Callable):
                # if max_cache_size is a callable, call it to get the value to use
                _max_cache_size = max_cache_size()
            else:
                _max_cache_size = max_cache_size
            eviction_attempt_count = 0  # to avoid infinite loop if we have a problem accessing the cache file
            eviction_attempt_limit = 10
            while _max_cache_size is not None and cache_file_path.stat().st_size > _max_cache_size and eviction_attempt_count < eviction_attempt_limit:
                # remove the least recently used entry
                with SqliteDict(cache_file_path, metadata_table_name) as metadata_db:
                    oldest_key = None
                    oldest_read_timestamp = None
                    for k, ts in metadata_db.items():
                        if oldest_read_timestamp is None or ts.read_timestamp < oldest_read_timestamp:
                            oldest_key = k
                            oldest_read_timestamp = ts.read_timestamp
                    if oldest_key is not None:
                        del metadata_db[oldest_key]
                        metadata_db.commit()
                        with SqliteDict(cache_file_path, function_name) as db:
                            if oldest_key in db:
                                del db[oldest_key]
                                db.commit()
                                _cache_counters.cache_eviction_counter += 1

                # shrink the database file (this does not happen automatically)
                try:
                    with sqlite3.connect(cache_file_path) as conn:
                        conn.execute("VACUUM")  # shrinks freelist back into the file
                        conn.commit()
                except sqlite3.OperationalError:
                    log.info(f'VACUUM failed for "{function_name}", probably because "{cache_file_path}" is locked. This is expected if multiple processes are using the cache.')

                eviction_attempt_count += 1
            if eviction_attempt_count >= eviction_attempt_limit:
                log.info(f'Eviction attempt limit reached ({eviction_attempt_limit=}) for "{function_name}" in "{cache_file_path}"')

            return result

        return wrapper

    return decorator


def get_counters() -> CacheCounters:
    return _cache_counters


def clear_counters():
    _cache_counters.clear()
