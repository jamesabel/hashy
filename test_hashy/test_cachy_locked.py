"""
Tests for cachy's behaviour when the cache file is locked by another writer, and for the
msqlite-backed table views that replaced sqlitedict.

Before this backend, a store that waited more than sqlitedict's 5 s connection timeout was
dropped with an INFO log and the caller never knew; the next call recomputed. Now the store
waits (msqlite retries with backoff up to LOCK_TIMEOUT_S) and, if it still cannot land, the
failure is a WARNING plus a counter.

All tests, fixtures and private helpers in this module are AI-authored (Claude Code); the
per-test ownership marker appears above each test.
"""

import logging
import pickle
import shutil
import sqlite3
import threading
import time
from datetime import timedelta
from pathlib import Path

import pytest

import hashy.cache as cache_mod
from hashy import cachy
from hashy.cache import CACHE_FORMAT_VERSION, CacheMetadata, CachyDBDict, CachyMetadataDBDict, clear_counters, get_counters

from .cache_directory import get_cache_directory


def _fresh_cache_dir(name: str) -> Path:
    cache_dir = Path(get_cache_directory(), "locked", name)
    shutil.rmtree(cache_dir, ignore_errors=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


class _WriteLockHolder:
    """Holds the sqlite write lock on a cache file from a separate connection, in a thread, for ``hold_s`` seconds."""

    def __init__(self, cache_file_path: Path, hold_s: float):
        self.cache_file_path = cache_file_path
        self.hold_s = hold_s
        self.locked = threading.Event()
        self.thread = threading.Thread(target=self._hold, daemon=True)

    def _hold(self) -> None:
        conn = sqlite3.connect(self.cache_file_path, isolation_level=None)
        try:
            conn.execute("BEGIN IMMEDIATE")  # the write lock: readers proceed under WAL, writers wait
            self.locked.set()
            time.sleep(self.hold_s)
            conn.execute("COMMIT")
        finally:
            conn.close()

    def __enter__(self) -> "_WriteLockHolder":
        self.thread.start()
        assert self.locked.wait(timeout=10.0), "lock holder did not acquire the write lock"
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.thread.join(timeout=30.0)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_store_waits_for_write_lock():
    """A store that meets another writer's lock waits for it instead of being dropped."""
    cache_dir = _fresh_cache_dir("wait")
    calls = []

    @cachy(cache_dir=cache_dir)
    def locked_wait_func(x):
        calls.append(x)
        return x * 2

    assert locked_wait_func(1) == 2  # creates the file and its table before the lock is taken
    clear_counters()

    hold_s = 1.0
    start = time.monotonic()
    with _WriteLockHolder(Path(cache_dir, "locked_wait_func_cache.sqlite"), hold_s):
        assert locked_wait_func(2) == 4  # returns only once the store has landed
    assert time.monotonic() - start >= hold_s * 0.9  # it really did wait out the lock

    assert get_counters().cache_store_failed_counter == 0
    assert locked_wait_func(2) == 4
    assert calls == [1, 2]  # served from the file cache, not recomputed
    assert get_counters().cache_hit_counter == 1


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_store_gives_up_at_lock_timeout(monkeypatch, caplog):
    """A store that cannot land within LOCK_TIMEOUT_S is reported (warning + counter) and the caller still gets its result."""
    monkeypatch.setattr(cache_mod, "LOCK_TIMEOUT_S", 0.5)
    cache_dir = _fresh_cache_dir("timeout")
    calls = []

    @cachy(cache_dir=cache_dir)
    def locked_timeout_func(x):
        calls.append(x)
        return x * 2

    assert locked_timeout_func(1) == 2  # creates the file and its table before the lock is taken
    clear_counters()

    with _WriteLockHolder(Path(cache_dir, "locked_timeout_func_cache.sqlite"), hold_s=2.0):
        with caplog.at_level(logging.WARNING, logger="hashy.cache"):
            assert locked_timeout_func(2) == 4  # the result is returned even though it could not be cached

    assert get_counters().cache_store_failed_counter == 1
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING and "Result not cached" in record.getMessage()]
    assert len(warnings) == 1
    assert "locked_timeout_func" in warnings[0].getMessage()

    # The lock is gone now; the entry never landed, so this is an honest miss and recompute.
    assert locked_timeout_func(2) == 4
    assert calls == [1, 2, 2]
    assert get_counters().cache_miss_counter == 2


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_dbdict_mapping_semantics():
    """The table views behave as mappings; a missing key raises KeyError on read and on delete (the race handling relies on it)."""
    cache_dir = _fresh_cache_dir("mapping")
    cache_file_path = Path(cache_dir, "mapping_cache.sqlite")

    with CachyDBDict(cache_file_path, "payload") as db:
        assert "k" not in db
        with pytest.raises(KeyError):
            db["k"]
        with pytest.raises(KeyError):
            del db["k"]
        db["k"] = b"v"
        assert "k" in db
        assert db["k"] == b"v"
        assert db.keys() == ["k"]
        assert db.items() == [("k", b"v")]
        db["k"] = b"w"  # replace
        assert db["k"] == b"w"
        db.commit()  # kept for API compatibility; every write above was already committed
        del db["k"]
        assert "k" not in db

    with CachyMetadataDBDict(cache_file_path, "payload_metadata") as metadata_db:
        metadata = CacheMetadata()
        metadata.read_timestamp = 1.5
        metadata.write_timestamp = 2.5
        metadata_db["k"] = metadata
        stored = metadata_db["k"]
        assert (stored.read_timestamp, stored.write_timestamp) == (1.5, 2.5)
        assert [(k, (v.read_timestamp, v.write_timestamp)) for k, v in metadata_db.items()] == [("k", (1.5, 2.5))]

    with sqlite3.connect(cache_file_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == CACHE_FORMAT_VERSION
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    conn.close()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_legacy_sqlitedict_file_is_reset():
    """A cache file written by hashy < 0.15 (sqlitedict layout, pickled values, no user_version) is dropped and recreated."""
    cache_dir = _fresh_cache_dir("legacy")
    cache_file_path = Path(cache_dir, "legacy_func_cache.sqlite")
    with sqlite3.connect(cache_file_path) as conn:
        conn.execute('CREATE TABLE "legacy_func" (key TEXT PRIMARY KEY, value BLOB)')
        conn.execute('CREATE TABLE "legacy_func_metadata" (key TEXT PRIMARY KEY, value BLOB)')
        conn.execute('INSERT INTO "legacy_func" VALUES (?, ?)', ("old_key", pickle.dumps(b"old payload")))
        conn.execute('INSERT INTO "legacy_func_metadata" VALUES (?, ?)', ("old_key", pickle.dumps(CacheMetadata())))
    conn.close()
    calls = []

    @cachy(cache_life=timedelta(days=1), cache_dir=cache_dir)
    def legacy_func(x):
        calls.append(x)
        return x + 1

    assert legacy_func(1) == 2
    assert legacy_func(1) == 2
    assert calls == [1]

    with sqlite3.connect(cache_file_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == CACHE_FORMAT_VERSION
        assert conn.execute('SELECT count(*) FROM "legacy_func"').fetchone()[0] == 1  # only the new entry; the pickled one is gone
        metadata_columns = [row[1] for row in conn.execute('PRAGMA table_info("legacy_func_metadata")').fetchall()]
        assert metadata_columns == ["key", "read_timestamp", "write_timestamp"]
    conn.close()


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_cache_file_deleted_between_calls():
    """Deleting the cache file while the process runs (e.g. a user clearing the cache) is recovered from on the next call."""
    cache_dir = _fresh_cache_dir("deleted")
    calls = []

    @cachy(cache_life=timedelta(days=1), cache_dir=cache_dir, max_cache_size=10_000_000)
    def deleted_file_func(x):
        calls.append(x)
        return x + 1

    assert deleted_file_func(1) == 2
    for suffix in ("", "-wal", "-shm"):
        Path(cache_dir, f"deleted_file_func_cache.sqlite{suffix}").unlink(missing_ok=True)

    assert deleted_file_func(1) == 2  # recreated the tables and recomputed
    assert deleted_file_func(1) == 2  # and the recomputed value was cached
    assert calls == [1, 1]
