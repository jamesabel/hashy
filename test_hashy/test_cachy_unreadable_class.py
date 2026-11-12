"""
A cached value whose class can no longer be rebuilt (moved, removed or reshaped since it was stored) is a miss.

Each test writes a small module to a temporary directory, caches an instance of a class from it, then changes or
removes that module so the stored pickle can no longer be turned back into a value.

All tests in this file are AI-authored (Claude Code); the private helpers below are covered by this note.
"""

import importlib
import logging
import sys
from pathlib import Path
from types import ModuleType

import pytest

from hashy import cachy
from hashy.cache import CacheReadError, cachy_compress, cachy_decompress, clear_counters, get_counters

from .cache_directory import get_cache_directory

DATACLASS_SOURCE = "from dataclasses import dataclass\n\n\n@dataclass\nclass Point:\n    x: int\n    y: int\n"


def _import_source(monkeypatch: pytest.MonkeyPatch, directory: Path, module_name: str, source: str) -> ModuleType:
    """Write ``source`` as ``module_name`` in ``directory`` and import it fresh (replacing any earlier version)."""
    monkeypatch.setattr(sys, "dont_write_bytecode", True)  # a rewritten source must never be shadowed by a stale .pyc
    monkeypatch.syspath_prepend(str(directory))
    monkeypatch.delitem(sys.modules, module_name, raising=False)  # also removes the module again at teardown
    Path(directory, f"{module_name}.py").write_text(source)
    importlib.invalidate_caches()
    return importlib.import_module(module_name)


def _remove_module(monkeypatch: pytest.MonkeyPatch, directory: Path, module_name: str) -> None:
    """Make ``module_name`` unimportable, as if the application had deleted or moved it."""
    Path(directory, f"{module_name}.py").unlink()
    monkeypatch.delitem(sys.modules, module_name, raising=False)
    importlib.invalidate_caches()


def _delete_cache_file(function_name: str) -> Path:
    """Remove a function's cache file (and sqlite side files) so counter values are deterministic."""
    cache_dir = get_cache_directory()
    for suffix in ("", "-wal", "-shm"):
        Path(cache_dir, f"{function_name}_cache.sqlite{suffix}").unlink(missing_ok=True)
    return cache_dir


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_cachy_decompress_module_gone(tmp_path, monkeypatch):
    module = _import_source(monkeypatch, tmp_path, "cachy_unit_old_place", DATACLASS_SOURCE)
    payload = cachy_compress(module.Point(1, 2))
    assert cachy_decompress(payload) == module.Point(1, 2)

    _remove_module(monkeypatch, tmp_path, "cachy_unit_old_place")

    with pytest.raises(CacheReadError, match="ModuleNotFoundError"):
        cachy_decompress(payload)


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_cachy_decompress_non_bytes_payload():
    # A payload that is not bytes at all (e.g. stored with compression off) is unreadable too, and reporting it must not itself fail.
    with pytest.raises(CacheReadError, match="TypeError"):
        cachy_decompress(123)  # type: ignore[arg-type]


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_cachy_moved_class_is_recomputed_and_replaced(tmp_path, monkeypatch, caplog):
    cache_dir = _delete_cache_file("moved_class_func")
    old_module = _import_source(monkeypatch, tmp_path, "cachy_moved_old_place", DATACLASS_SOURCE)
    point_class = {"current": old_module.Point}
    calls = []

    @cachy(cache_dir=cache_dir)
    def moved_class_func(key):
        calls.append(key)
        return point_class["current"](1, 2)

    clear_counters()
    assert moved_class_func("a") == old_module.Point(1, 2)  # miss -> stored as cachy_moved_old_place.Point
    assert moved_class_func("a") == old_module.Point(1, 2)  # hit
    assert len(calls) == 1
    assert get_counters().cache_hit_counter == 1

    # The application moves the class to another module.
    _remove_module(monkeypatch, tmp_path, "cachy_moved_old_place")
    new_module = _import_source(monkeypatch, tmp_path, "cachy_moved_new_place", DATACLASS_SOURCE)
    point_class["current"] = new_module.Point

    clear_counters()
    with caplog.at_level(logging.WARNING, logger="hashy.cache"):
        assert moved_class_func("a") == new_module.Point(1, 2)  # unreadable entry -> recomputed, not raised
    assert len(calls) == 2
    assert get_counters().cache_miss_counter == 1
    assert get_counters().cache_hit_counter == 0
    warnings = [record.getMessage() for record in caplog.records if record.levelno == logging.WARNING]
    assert any("moved_class_func" in message and "ModuleNotFoundError" in message for message in warnings)

    # The unreadable entry was replaced by the recomputed one, so the next call is a hit.
    assert moved_class_func("a") == new_module.Point(1, 2)
    assert len(calls) == 2
    assert get_counters().cache_hit_counter == 1


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_cachy_removed_name_is_recomputed(tmp_path, monkeypatch, caplog):
    cache_dir = _delete_cache_file("removed_name_func")
    module = _import_source(monkeypatch, tmp_path, "cachy_removed_name_place", DATACLASS_SOURCE)
    results = {"current": module.Point(1, 2)}
    calls = []

    @cachy(cache_dir=cache_dir)
    def removed_name_func(key):
        calls.append(key)
        return results["current"]

    assert removed_name_func("a") == module.Point(1, 2)

    # The module is still importable but no longer defines the class.
    _import_source(monkeypatch, tmp_path, "cachy_removed_name_place", "OTHER = 1\n")
    results["current"] = (1, 2)

    clear_counters()
    with caplog.at_level(logging.WARNING, logger="hashy.cache"):
        assert removed_name_func("a") == (1, 2)
    assert len(calls) == 2
    assert get_counters().cache_miss_counter == 1
    assert any("removed_name_func" in record.getMessage() and "AttributeError" in record.getMessage() for record in caplog.records)

    assert removed_name_func("a") == (1, 2)  # replaced entry -> hit
    assert len(calls) == 2
    assert get_counters().cache_hit_counter == 1


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_cachy_removed_enum_member_is_recomputed(tmp_path, monkeypatch, caplog):
    cache_dir = _delete_cache_file("removed_enum_member_func")
    module = _import_source(monkeypatch, tmp_path, "cachy_enum_place", "from enum import Enum\n\n\nclass Color(Enum):\n    RED = 1\n    GREEN = 2\n")
    results = {"current": module.Color.GREEN}
    calls = []

    @cachy(cache_dir=cache_dir)
    def removed_enum_member_func(key):
        calls.append(key)
        return results["current"]

    assert removed_enum_member_func("a") is module.Color.GREEN

    # Same class at the same path, but the stored member no longer exists: rebuilding it raises ValueError.
    module = _import_source(monkeypatch, tmp_path, "cachy_enum_place", "from enum import Enum\n\n\nclass Color(Enum):\n    RED = 1\n")
    results["current"] = module.Color.RED

    clear_counters()
    with caplog.at_level(logging.WARNING, logger="hashy.cache"):
        assert removed_enum_member_func("a") is module.Color.RED
    assert len(calls) == 2
    assert get_counters().cache_miss_counter == 1
    assert any("removed_enum_member_func" in record.getMessage() and "ValueError" in record.getMessage() for record in caplog.records)

    assert removed_enum_member_func("a") is module.Color.RED  # replaced entry -> hit
    assert len(calls) == 2
    assert get_counters().cache_hit_counter == 1


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_cachy_namedtuple_field_added_is_recomputed(tmp_path, monkeypatch, caplog):
    cache_dir = _delete_cache_file("namedtuple_field_func")
    module = _import_source(monkeypatch, tmp_path, "cachy_namedtuple_place", "from typing import NamedTuple\n\n\nclass Pair(NamedTuple):\n    x: int\n    y: int\n")
    results = {"current": module.Pair(1, 2)}
    calls = []

    @cachy(cache_dir=cache_dir)
    def namedtuple_field_func(key):
        calls.append(key)
        return results["current"]

    assert namedtuple_field_func("a") == module.Pair(1, 2)

    # Same class at the same path with a new required field: rebuilding the stored two-field value raises TypeError.
    module = _import_source(monkeypatch, tmp_path, "cachy_namedtuple_place", "from typing import NamedTuple\n\n\nclass Pair(NamedTuple):\n    x: int\n    y: int\n    z: int\n")
    results["current"] = module.Pair(1, 2, 3)

    clear_counters()
    with caplog.at_level(logging.WARNING, logger="hashy.cache"):
        assert namedtuple_field_func("a") == module.Pair(1, 2, 3)
    assert len(calls) == 2
    assert get_counters().cache_miss_counter == 1
    assert any("namedtuple_field_func" in record.getMessage() and "TypeError" in record.getMessage() for record in caplog.records)

    assert namedtuple_field_func("a") == module.Pair(1, 2, 3)  # replaced entry -> hit
    assert len(calls) == 2
    assert get_counters().cache_hit_counter == 1
