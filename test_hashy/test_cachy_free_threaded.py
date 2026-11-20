"""
Thread-safety of cachy's in-process shared state (the counters and the in-memory cache), which matters most on
free-threaded Python, where threads really do run this code in parallel.

All tests and helpers in this file are AI-generated (Claude Code).
"""

import shutil
import sys
import sysconfig
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from hashy import cachy
from hashy.cache import clear_counters, get_counters

from .cache_directory import get_cache_directory

_cache_dir = Path(get_cache_directory(), "free_threaded")

_THREADS = 8
_CALLS_PER_THREAD = 5000
_DISTINCT_ARGUMENTS = 4


@cachy(cache_dir=_cache_dir, in_memory=True)
def _free_threaded_func(x: int) -> int:
    return x + 1


def _call_many(thread_number: int) -> None:
    for call_number in range(_CALLS_PER_THREAD):
        argument = (thread_number + call_number) % _DISTINCT_ARGUMENTS
        assert _free_threaded_func(argument) == argument + 1


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
def test_counters_exact_under_threads():
    """Every call is counted exactly once as a hit or a miss, however many threads are counting at once."""
    shutil.rmtree(_cache_dir, ignore_errors=True)
    for argument in range(_DISTINCT_ARGUMENTS):
        _free_threaded_func(argument)  # warm the cache, so the threads below only take the short in-memory path
    clear_counters()

    switch_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)  # on a GIL build, switch threads often enough to expose a non-atomic update
    try:
        with ThreadPoolExecutor(max_workers=_THREADS) as executor:
            list(executor.map(_call_many, range(_THREADS)))
    finally:
        sys.setswitchinterval(switch_interval)

    counters = get_counters()
    total_calls = _THREADS * _CALLS_PER_THREAD
    assert counters.cache_miss_counter == 0
    assert counters.cache_hit_counter == total_calls
    assert counters.cache_memory_hit_counter == total_calls


# AI-GENERATED TEST (Claude Code) - delete this line to make this test human-owned.
@pytest.mark.skipif(not sysconfig.get_config_var("Py_GIL_DISABLED"), reason="needs a free-threaded Python build")
def test_gil_stays_disabled():
    """Importing and using hashy on a free-threaded build leaves the GIL off, with gilguard watching the imports."""
    assert "gilguard" in sys.modules  # installed by the top-level conftest.py
    assert _free_threaded_func(1) == 2
    assert not sys._is_gil_enabled()
