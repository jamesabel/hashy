"""
``cachy`` -- a persistent, process/thread-safe function-result cache.

The public surface is the :func:`cachy` decorator plus the :class:`CacheCounters`
helpers (:func:`get_counters` / :func:`clear_counters`). Everything else in this
module is supporting machinery:

- :class:`CachyDBDict` -- a thin ``SqliteDict`` subclass with cachy's settings.
- :func:`cachy_compress` / :func:`cachy_decompress` -- payload (de)serialization.
- :class:`CacheMetadata` -- per-entry read/write timestamps (kept in a separate
  table so timestamp updates do not rewrite the payload).
- :class:`_CachyCache` -- holds one decorated function's configuration and
  implements the read/compute/write/evict logic. One instance per decorated
  function; the returned wrapper just delegates to :meth:`_CachyCache.call`.

Each function gets its own sqlite file ``{cache_dir}/{function_name}_cache.sqlite``
containing a payload table (named after the function) and, when ``cache_life`` or
``max_cache_size`` is used, a ``{function_name}_metadata`` table.
"""

from typing import Any, Callable, Dict, Optional, Union
from functools import wraps
from pathlib import Path
from datetime import timedelta
from logging import getLogger
import inspect
import time
import sqlite3
import pickle
import lzma
import random

from platformdirs import user_cache_dir
from sqlitedict import SqliteDict

from . import __application_name__, __author__, get_dls_sha512

log = getLogger(__name__)

# Sentinel returned by the in-memory read to mean "not found" -- distinct from a
# legitimately cached ``None`` value, which must be treated as a hit.
_MISS = object()


class CacheReadError(Exception):
    """Cache entry could not be decompressed/unpickled; treat as a miss."""


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

USE_COMPRESSION = True
JOURNAL_MODE = "WAL"  # WAL maximizes throughput and concurrency without sacrificing durability


class CachyDBDict(SqliteDict):
    """
    Set SqliteDict parameters best for cachy. Also add typing.
    """

    def __init__(self, cache_file_path: Path, table_name: str):
        super().__init__(cache_file_path, table_name, journal_mode=JOURNAL_MODE)


def cachy_compress(data: Any) -> bytes:
    """
    Serialize and (optionally) compress a value for storage, using pickle + lzma.

    :param data: the value to store
    :return: the compressed payload bytes (or the value unchanged if compression is disabled)
    """
    if USE_COMPRESSION:
        p = pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)
        out = lzma.compress(p)
        if (compression_ratio := len(p) / len(out)) > 1.0:
            log.info(f"Compressed {len(p)} bytes to {len(out)} bytes, compression ratio: {compression_ratio:.2f}")
    else:
        out = data
    return out


def cachy_decompress(data: bytes) -> Any:
    """
    Reverse :func:`cachy_compress`: decompress and unpickle a stored payload.

    :param data: the payload bytes read from the cache
    :return: the original value
    :raises CacheReadError: if the payload cannot be decompressed/unpickled (corruption or transient OOM)
    """
    if not USE_COMPRESSION:
        return data
    try:
        return pickle.loads(lzma.decompress(data))
    except (MemoryError, lzma.LZMAError, EOFError, pickle.UnpicklingError) as e:
        raise CacheReadError(f"unreadable cache entry ({len(data)} bytes): {e}") from e


def get_cache_dir() -> Path:
    """
    Get the cache directory for this application.
    :return: Path to the cache directory
    """
    cache_dir = Path(user_cache_dir(__application_name__, __author__))
    return cache_dir


class _CachyCache:
    """
    Holds one decorated function's cache configuration and implements the
    read / compute / write / evict logic.

    A single instance is created per decorated function (at decoration time);
    the wrapper returned by :func:`cachy` simply forwards each call to
    :meth:`call`. Methods are intentionally small and single-purpose so the
    overall flow in :meth:`call` reads as a high-level outline.
    """

    # Bound the metadata read/expire retry loop so a persistently locked db can
    # never hang the caller (lock contention is expected across processes).
    METADATA_RETRY_LIMIT = 100
    # Bound the LRU eviction loop so a problem accessing the file cannot spin forever.
    EVICTION_ATTEMPT_LIMIT = 10

    def __init__(
        self,
        func: Callable,
        cache_dir: Path,
        cache_life: Union[timedelta, Callable[[], Optional[timedelta]], None],
        cache_none: bool,
        in_memory: bool,
        max_cache_size: Union[int, Callable, None],
    ):
        self.func = func
        self.function_name = func.__name__
        # Used to resolve default argument values when building the cache key, so a
        # call relying on a default keys the same as one passing that value explicitly.
        try:
            self.signature: Optional[inspect.Signature] = inspect.signature(func)
        except (ValueError, TypeError):
            # Some callables (e.g. certain builtins) expose no signature; fall back to
            # keying on the explicitly-passed arguments only.
            self.signature = None
        self.cache_life = cache_life
        self.cache_none = cache_none
        self.in_memory = in_memory
        self.max_cache_size = max_cache_size

        self.cache_file_path = Path(cache_dir, f"{self.function_name}_cache.sqlite")
        self.payload_table = self.function_name
        self.metadata_table = f"{self.function_name}_metadata"
        # Stores the same compressed payload bytes as the file cache, for fast reads.
        self.in_memory_cache: Dict[str, bytes] = {}

    # -- public entry point ------------------------------------------------

    def call(self, args: tuple, kwargs: dict) -> Any:
        """Return the cached result for ``(args, kwargs)``, computing and caching it on a miss."""
        key = self._key(args, kwargs)
        self._ensure_cache_dir()

        # Expire a stale entry and/or refresh its LRU read time before reading.
        if self._uses_metadata:
            self._expire_and_touch(key)

        result = self._read_memory(key)
        cache_write = False
        if result is _MISS:
            result, cache_write = self._read_file_or_compute(key, args, kwargs)

        # Record the write time so future calls can expire / LRU-evict the entry.
        if cache_write and self._uses_metadata:
            self._record_write(key)

        # Keep the on-disk cache within its size budget.
        if cache_write and self.max_cache_size is not None:
            self._evict_to_size()

        return result

    # -- configuration helpers --------------------------------------------

    @property
    def _uses_metadata(self) -> bool:
        """True when a metadata table is needed (for expiry and/or LRU eviction)."""
        return self.cache_life is not None or self.max_cache_size is not None

    def _key(self, args: tuple, kwargs: dict) -> str:
        """
        Build a stable cache key from the call arguments via hashy's dict/list/set hashing.

        Default argument values are resolved from the function signature first, so a
        call that relies on a default participates in the key the same way an explicit
        value would. Without this, defaults never appear in ``args``/``kwargs`` and two
        calls with different effective defaults would collide on the same (empty) key.
        """
        args, kwargs = self._resolve_defaults(args, kwargs)
        return get_dls_sha512([get_dls_sha512(list(args)), get_dls_sha512(kwargs)])

    def _resolve_defaults(self, args: tuple, kwargs: dict) -> tuple:
        """
        Normalize ``(args, kwargs)`` by filling in the function's default values.

        Returns the bound positional/keyword arguments with defaults applied. If the
        function has no introspectable signature, or the call does not match it, the
        original ``args``/``kwargs`` are returned unchanged.
        """
        if self.signature is None:
            return args, kwargs
        try:
            bound = self.signature.bind(*args, **kwargs)
        except TypeError:
            # Arguments don't fit the signature; let the real call raise and key as-is.
            return args, kwargs
        bound.apply_defaults()
        return bound.args, bound.kwargs

    def _ensure_cache_dir(self) -> None:
        """Create the cache directory if it does not already exist."""
        try:
            self.cache_file_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            log.info(f'Error creating cache directory: "{e}"')

    def _payload_db(self) -> CachyDBDict:
        """Open the payload table (use as a context manager)."""
        return CachyDBDict(self.cache_file_path, self.payload_table)

    def _metadata_db(self) -> CachyDBDict:
        """Open the metadata table (use as a context manager)."""
        return CachyDBDict(self.cache_file_path, self.metadata_table)

    # -- sqlite resiliency helpers ----------------------------------------

    def _locked_note(self, what: str) -> str:
        """Standard log message for an operation that failed because the db is (expectedly) locked."""
        return f'{what} for "{self.function_name}", probably because "{self.cache_file_path}" is locked. This is expected if multiple processes are using the cache.'

    def _commit(self, db: CachyDBDict, what: str) -> None:
        """Commit ``db``, swallowing the OperationalError raised when the db is locked."""
        try:
            db.commit()
        except sqlite3.OperationalError:
            log.info(self._locked_note(what))

    # -- expiry + LRU read-time refresh -----------------------------------

    def _expire_and_touch(self, key: str) -> None:
        """
        Drop ``key`` if it has expired, and refresh its LRU read time.

        Runs inside a retry loop because the metadata table may be transiently
        locked by another process; lock contention is expected, not an error.
        """
        write_ok = False
        countdown = self.METADATA_RETRY_LIMIT
        while not write_ok and countdown > 0:
            try:
                with self._metadata_db() as metadata_db:
                    self._expire_and_touch_once(metadata_db, key)
                write_ok = True
            except sqlite3.OperationalError:
                log.debug(self._locked_note("Error accessing cache"))
                time.sleep((0.01 * random.random()) + 0.01)
            countdown -= 1
        if not write_ok:
            log.warning(f'Error accessing cache for "{self.function_name}", probably because "{self.cache_file_path}" is locked.')

    def _expire_and_touch_once(self, metadata_db: CachyDBDict, key: str) -> None:
        """One attempt at the expire + LRU-touch logic (see :meth:`_expire_and_touch`)."""
        if key in metadata_db:
            try:
                row_metadata = metadata_db[key]
            except (KeyError, TypeError):
                # can happen if the cache is in an old/incompatible format
                row_metadata = CacheMetadata()
            write_ts = row_metadata.write_timestamp
        else:
            row_metadata = None
            write_ts = 0.0  # force a cache miss

        cache_life = self.cache_life() if callable(self.cache_life) else self.cache_life
        expired = cache_life is not None and time.time() - write_ts >= cache_life.total_seconds()
        if expired:
            self._expire_entry(metadata_db, key)

        # Refresh the LRU read time on access (only relevant when size-bounded). Guard on the
        # row actually read above rather than re-testing membership: another process may have
        # written the key since (row_metadata would be None) or expired it (we must not touch a
        # just-expired entry back into existence).
        if self.max_cache_size is not None and row_metadata is not None and not expired:
            row_metadata.read_timestamp = time.time()
            metadata_db[key] = row_metadata
            metadata_db.commit()

    def _expire_entry(self, metadata_db: CachyDBDict, key: str) -> None:
        """
        Delete an expired entry's metadata, payload, and in-memory copy.

        Multiple processes sharing the cache file can race to expire the same entry. Losing
        that race (the key is already gone) is success, not an error, so the ``KeyError``
        sqlitedict raises when deleting a missing key is swallowed rather than letting it
        escape to the caller. Deleting first and tolerating ``KeyError`` (instead of an
        ``if key in db`` check) is what closes the check-then-act window. The expired
        counter is only incremented by the process whose delete actually ran.
        """
        try:
            del metadata_db[key]
        except KeyError:
            pass  # another process expired this entry first
        else:
            _cache_counters.cache_expired_counter += 1
            metadata_db.commit()
        with self._payload_db() as db:
            try:
                del db[key]
            except KeyError:
                pass  # another process expired this entry first
            else:
                db.commit()
        # Drop the in-memory copy too, otherwise _read_memory would serve the expired value.
        if self.in_memory:
            self.in_memory_cache.pop(key, None)

    # -- reads -------------------------------------------------------------

    def _read_memory(self, key: str) -> Any:
        """
        Read from the in-memory cache.

        :return: the cached value (which may legitimately be ``None``) on a hit,
            or :data:`_MISS` when in-memory caching is off, the key is absent, or
            the stored entry is unreadable (in which case it is discarded).
        """
        if not (self.in_memory and key in self.in_memory_cache):
            return _MISS
        try:
            result = cachy_decompress(self.in_memory_cache[key])
        except CacheReadError as e:
            log.warning(f'Discarding unreadable in-memory cache entry for "{self.function_name}": {e}')
            self.in_memory_cache.pop(key, None)
            return _MISS
        _cache_counters.cache_memory_hit_counter += 1
        _cache_counters.cache_hit_counter += 1
        return result

    def _read_file_or_compute(self, key: str, args: tuple, kwargs: dict) -> tuple:
        """
        Read from the file cache, or recompute and store on a miss.

        :return: ``(result, cache_write)`` where ``cache_write`` is True when the
            value was (re)computed and written (so the caller updates metadata / evicts).
        """
        with self._payload_db() as db:
            if key in db:
                try:
                    result = cachy_decompress(db[key])
                    _cache_counters.cache_hit_counter += 1
                    return result, False
                except CacheReadError as e:
                    # unreadable entry (transient OOM or corruption) -> drop it, treat as miss
                    log.warning(f'Discarding unreadable cache entry for "{self.function_name}": {e}')
                    self._discard_payload(db, key)

            # miss (genuine, or just-discarded bad entry) - recompute
            _cache_counters.cache_miss_counter += 1
            result = self.func(*args, **kwargs)
            self._store(db, key, result)
            return result, True

    def _discard_payload(self, db: CachyDBDict, key: str) -> None:
        """Best-effort removal of an unreadable payload entry."""
        try:
            del db[key]
            db.commit()
        except (KeyError, sqlite3.OperationalError):
            pass

    # -- writes ------------------------------------------------------------

    def _store(self, db: CachyDBDict, key: str, result: Any) -> None:
        """
        Store ``result`` in the file cache and, if enabled, the in-memory cache.

        ``None`` results are only stored when ``cache_none`` is True; this gate
        applies to both caches so the in-memory cache honors ``cache_none`` the
        same way the file cache does.
        """
        if result is None and not self.cache_none:
            return
        cached_result = cachy_compress(result)
        db[key] = cached_result
        self._commit(db, "Commit failed")
        if self.in_memory:
            self.in_memory_cache[key] = cached_result

    def _record_write(self, key: str) -> None:
        """Record the write timestamp for ``key`` (used by expiry and LRU eviction)."""
        with self._metadata_db() as metadata_db:
            metadata_db[key] = CacheMetadata()
            self._commit(metadata_db, "Commit failed")

    # -- LRU eviction ------------------------------------------------------

    def _evict_to_size(self) -> None:
        """Evict least-recently-used entries until the cache file is within ``max_cache_size`` bytes."""
        max_cache_size = self.max_cache_size
        if max_cache_size is None:
            return
        # max_cache_size may be an int or a callable that returns the limit (or None for "no limit").
        max_size = max_cache_size if isinstance(max_cache_size, int) else max_cache_size()
        if max_size is None:
            return
        attempts = 0
        while self.cache_file_path.stat().st_size > max_size and attempts < self.EVICTION_ATTEMPT_LIMIT:
            self._evict_oldest()
            self._vacuum()  # shrink the file; sqlite does not do this automatically
            attempts += 1
        if attempts >= self.EVICTION_ATTEMPT_LIMIT:
            log.info(f'Eviction attempt limit reached (eviction_attempt_limit={self.EVICTION_ATTEMPT_LIMIT}) for "{self.function_name}" in "{self.cache_file_path}"')

    def _evict_oldest(self) -> None:
        """Remove the single least-recently-read entry from the metadata, payload, and in-memory caches."""
        with self._metadata_db() as metadata_db:
            oldest_key = self._find_oldest(metadata_db)
            if oldest_key is None:
                return
            del metadata_db[oldest_key]
            metadata_db.commit()
            with self._payload_db() as db:
                try:
                    del db[oldest_key]
                    db.commit()
                except KeyError:
                    log.info(f'Key "{oldest_key}" not found in cache for "{self.function_name}". This is unexpected.')
            if self.in_memory:
                try:
                    del self.in_memory_cache[oldest_key]
                except KeyError:
                    log.info(f'Key "{oldest_key}" not found in in-memory cache for "{self.function_name}". This is unexpected.')
            _cache_counters.cache_eviction_counter += 1

    @staticmethod
    def _find_oldest(metadata_db: CachyDBDict) -> Optional[str]:
        """Return the key with the oldest read timestamp, or None if the metadata table is empty."""
        oldest_key = None
        oldest_read_timestamp = None
        for k, ts in metadata_db.items():
            if oldest_read_timestamp is None or ts.read_timestamp < oldest_read_timestamp:
                oldest_key = k
                oldest_read_timestamp = ts.read_timestamp
        return oldest_key

    def _vacuum(self) -> None:
        """VACUUM the sqlite file so freed space is returned to the filesystem."""
        try:
            with sqlite3.connect(self.cache_file_path) as conn:
                conn.execute("VACUUM")  # shrinks freelist back into the file
                conn.commit()
        except sqlite3.OperationalError:
            log.info(self._locked_note("VACUUM failed"))


def cachy(
    cache_life: Union[timedelta, Callable[[], Optional[timedelta]], None] = None,
    cache_dir: Path = get_cache_dir(),
    cache_none: bool = False,
    in_memory: bool = False,
    max_cache_size: int | Callable | None = None,
) -> Callable:
    """
    Decorator to persistently cache the results of a function call, with a cache life.
    :param cache_life: Cache life, as a timedelta or a callable returning the current timedelta (resolved live on each call) or None.
    :param cache_dir: Cache directory.
    :param cache_none: Cache None results (default is to not cache None results).
    :param in_memory: If True, use an in-memory cache for reads (default is to only use a file-based cache).
    :param max_cache_size: Maximum size of the LRU cache as an int, or a callable that returns max cache size, or None (default is None, which means no limit)
    """

    def decorator(func: Callable) -> Callable:
        cache = _CachyCache(func, cache_dir, cache_life, cache_none, in_memory, max_cache_size)

        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            return cache.call(args, kwargs)

        return wrapper

    return decorator


def get_counters() -> CacheCounters:
    return _cache_counters


def clear_counters():
    _cache_counters.clear()
