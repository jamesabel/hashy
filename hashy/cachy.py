import pickle
from typing import Callable, Any, Dict
from functools import wraps
from pathlib import Path
from datetime import datetime, timedelta
import os

from appdirs import user_cache_dir

from . import __application_name__, __author__, get_dls_sha512


# Global counters, handy for testing
class CacheCounters:
    def __init__(self, cache_hit_counter=0, cache_miss_counter=0, cache_load_counter=0, cache_expired_counter=0):
        self.cache_hit_counter = cache_hit_counter
        self.cache_miss_counter = cache_miss_counter
        self.cache_load_counter = cache_load_counter
        self.cache_expired_counter = cache_expired_counter

    def __repr__(self):
        values = [
            f"cache_hit_counter={self.cache_hit_counter}",
            f"cache_miss_counter={self.cache_miss_counter}",
            f"cache_load_counter={self.cache_load_counter}",
            f"cache_expired_counter={self.cache_expired_counter}",
        ]
        return ",".join(values)

    def __eq__(self, other):
        return (
            self.cache_hit_counter == other.cache_hit_counter
            and self.cache_miss_counter == other.cache_miss_counter
            and self.cache_load_counter == other.cache_load_counter
            and self.cache_expired_counter == other.cache_expired_counter
        )

    def clear(self):
        self.cache_hit_counter = 0
        self.cache_miss_counter = 0
        self.cache_load_counter = 0
        self.cache_expired_counter = 0


_cache_counters = CacheCounters()


def get_cache_dir() -> Path:
    """
    Get the cache directory for this application.
    :return: Path to the cache directory
    """
    cache_dir = Path(user_cache_dir(__application_name__, __author__))
    return cache_dir


def cachy(cache_life: timedelta, cache_dir: Path = get_cache_dir()) -> Callable:
    """
    Decorator to persistently cache the results of a function call, with a cache life.
    :param cache_life: cache life
    :param cache_dir: cache directory
    """

    def decorator(func: Callable) -> Callable:
        cache: Dict[str, Any] = {}

        # Create a cache file path based on the function name
        cache_file_path = Path(cache_dir, f"{func.__name__}_cache.pkl")

        def load_cache(_cache: dict[str, Any]):
            global _cache_counters

            # Delete the cache file if it has expired
            if cache_file_path.exists():
                cache_file_mtime = datetime.fromtimestamp(os.path.getmtime(cache_file_path))
                if datetime.now() - cache_file_mtime >= cache_life:
                    _cache_counters.cache_expired_counter += 1
                    try:
                        cache_file_path.unlink(missing_ok=True)
                    except OSError:
                        ...
                    _cache.clear()

            # If we haven't already, load existing cache if file exists
            if len(_cache) == 0 and cache_file_path.exists():
                with open(cache_file_path, "rb") as cache_file_reader:
                    try:
                        # cache is pass by reference (don't create a new dict - clear and update the existing one)
                        _cache.clear()
                        _cache.update(pickle.load(cache_file_reader))
                        _cache_counters.cache_load_counter += 1
                    except (EOFError, pickle.UnpicklingError):
                        cache_file_path.unlink(missing_ok=True)  # corrupt or old version - delete it

        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            global _cache_counters
            load_cache(cache)
            key = get_dls_sha512([get_dls_sha512(list(args)), get_dls_sha512(kwargs)])
            if key in cache:
                _cache_counters.cache_hit_counter += 1
            else:
                _cache_counters.cache_miss_counter += 1
                result = func(*args, **kwargs)
                cache[key] = result
                cache_dir.mkdir(parents=True, exist_ok=True)
                with open(cache_file_path, "wb") as cache_file_writer:
                    pickle.dump(cache, cache_file_writer)
            return cache[key]

        return wrapper

    return decorator


def get_counters() -> CacheCounters:
    return _cache_counters


def clear_counters():
    global _cache_counters
    _cache_counters.clear()
