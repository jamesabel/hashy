import pickle
from typing import Callable, Any, Dict
from functools import wraps
from pathlib import Path
from datetime import datetime, timedelta
import os

from appdirs import user_cache_dir

from . import __application_name__, __author__, get_dls_sha512


def get_cache_dir() -> Path:
    """
    Get the cache directory for this application.
    Can be patched to change the cache directory.
    :return: Path to the cache directory
    """
    cache_dir = Path(user_cache_dir(__application_name__, __author__))
    return cache_dir


def cachy(cache_life: timedelta, cache_dir: Path = get_cache_dir()) -> Callable:
    def decorator(func: Callable) -> Callable:
        cache: Dict[str, Any] = {}

        # Ensure the cache directory exists
        cache_directory = Path(cache_dir)
        cache_directory.mkdir(parents=True, exist_ok=True)

        # Create a cache file path based on the function name
        cache_file_path = cache_directory / f"{func.__name__}_cache.pkl"

        if cache_file_path.exists():
            cache_file_mtime = datetime.fromtimestamp(os.path.getmtime(cache_file_path))
            if datetime.now() - cache_file_mtime >= cache_life:
                try:
                    cache_file_path.unlink(missing_ok=True)
                except OSError:
                    ...

        # Load existing cache if file exists
        if cache_file_path.exists():
            with open(cache_file_path, "rb") as cache_file_reader:
                try:
                    cache = pickle.load(cache_file_reader)
                except (EOFError, pickle.UnpicklingError):
                    cache_file_path.unlink(missing_ok=True)  # corrupt or old version - delete it
                    cache = {}

        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            key = get_dls_sha512([get_dls_sha512(list(args)), get_dls_sha512(kwargs)])
            if key not in cache:
                result = func(*args, **kwargs)
                cache[key] = result
                with open(cache_file_path, "wb") as cache_file_writer:
                    pickle.dump(cache, cache_file_writer)
            return cache[key]

        return wrapper

    return decorator
