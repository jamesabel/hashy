from typing import Callable, Any, Union, Dict
from functools import wraps
from pathlib import Path
from datetime import timedelta
import json
from logging import getLogger
import time

from platformdirs import user_cache_dir
from sqlitedict import SqliteDict

from . import __application_name__, __author__, get_dls_sha512

log = getLogger(__name__)


# Global counters, handy for testing
class CacheCounters:
    def __init__(self, cache_memory_hit_counter=0, cache_hit_counter=0, cache_miss_counter=0, cache_expired_counter=0):
        self.cache_memory_hit_counter = cache_memory_hit_counter
        self.cache_hit_counter = cache_hit_counter
        self.cache_miss_counter = cache_miss_counter
        self.cache_expired_counter = cache_expired_counter

    def __repr__(self):
        values = [
            f"cache_memory_hit_counter={self.cache_memory_hit_counter}",
            f"cache_hit_counter={self.cache_hit_counter}",
            f"cache_miss_counter={self.cache_miss_counter}",
            f"cache_expired_counter={self.cache_expired_counter}",
        ]
        return ",".join(values)

    def __eq__(self, other):
        return (
            self.cache_memory_hit_counter == other.cache_memory_hit_counter
            and self.cache_hit_counter == other.cache_hit_counter
            and self.cache_miss_counter == other.cache_miss_counter
            and self.cache_expired_counter == other.cache_expired_counter
        )

    def clear(self):
        self.cache_memory_hit_counter = 0
        self.cache_hit_counter = 0
        self.cache_miss_counter = 0
        self.cache_expired_counter = 0


_cache_counters = CacheCounters()


def get_cache_dir() -> Path:
    """
    Get the cache directory for this application.
    :return: Path to the cache directory
    """
    cache_dir = Path(user_cache_dir(__application_name__, __author__))
    return cache_dir


def cachy(cache_life: Union[timedelta, None] = None, cache_dir: Path = get_cache_dir(), cache_none: bool = False, in_memory: bool = False) -> Callable:
    """
    Decorator to persistently cache the results of a function call, with a cache life.
    :param cache_life: cache life
    :param cache_dir: cache directory
    :param cache_none: cache None results (default is to not cache None results)
    :param in_memory: if True, use an in-memory cache (default is to use a file-based cache)
    """

    def decorator(func: Callable) -> Callable:

        function_name = func.__name__
        in_memory_cache: Dict[str, Any] = {}

        # Create a cache file path based on the function name
        cache_file_path = Path(cache_dir, f"{function_name}_cache.sqlite")

        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:

            key = get_dls_sha512([get_dls_sha512(list(args)), get_dls_sha512(kwargs)])

            cache_file_path.parent.mkdir(parents=True, exist_ok=True)

            modified_table_name = f"{function_name}_mtime"

            # If entry has expired, delete it from the cache. Note that if there is no cache life (infinite), we avoid this operation completely.
            if cache_life is not None:
                with SqliteDict(cache_file_path, modified_table_name, encode=json.dumps, decode=json.loads) as ts_db:
                    if key in ts_db and time.time() - ts_db[key] >= cache_life.total_seconds():
                        _cache_counters.cache_expired_counter += 1
                        del ts_db[key]
                        ts_db.commit()
                        with SqliteDict(cache_file_path, function_name) as db:
                            if key in db:
                                del db[key]
                                db.commit()

            # use in-memory cache, if enabled
            result = None
            if in_memory and key in in_memory_cache:
                _cache_counters.cache_memory_hit_counter += 1
                _cache_counters.cache_hit_counter += 1
                result = in_memory_cache[key]

            if result is None:
                with SqliteDict(cache_file_path, function_name) as db:
                    if key in db:
                        _cache_counters.cache_hit_counter += 1
                        result = db[key]
                    else:
                        _cache_counters.cache_miss_counter += 1
                        result = func(*args, **kwargs)
                        if result is not None or cache_none:
                            db[key] = result
                            db.commit()
                        if in_memory:
                            in_memory_cache[key] = result

            # update timestamp
            if cache_life is not None:
                with SqliteDict(cache_file_path, modified_table_name, encode=json.dumps, decode=json.loads) as ts_db:
                    ts_db[key] = time.time()
                    ts_db.commit()

            return result

        return wrapper

    return decorator


def get_counters() -> CacheCounters:
    return _cache_counters


def clear_counters():
    _cache_counters.clear()
