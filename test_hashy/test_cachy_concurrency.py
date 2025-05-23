from pathlib import Path
from datetime import timedelta, datetime
import shutil
from threading import Thread

from psutil import cpu_count

from hashy import cachy
from hashy.cache import get_counters

test_name = "test_cachy_concurrency"

temp_dir = Path("temp", test_name)

duration = timedelta(seconds=10)


@cachy(cache_dir=temp_dir, in_memory=True)
def _function(x):
    result = x + 1
    return result


class TestThread(Thread):

    def __init__(self, x):
        super().__init__()
        self.x = x

    def run(self):
        for iteration in range(10):
            result = _function(self.x)
            assert result == self.x + 1, f"Expected {self.x + 1}, got {result}"


def test_cachy_concurrency():
    """
    Test that the cachy decorator works in a concurrent (multithreaded, multiprocessing) environment.
    """

    shutil.rmtree(temp_dir, ignore_errors=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    concurrency = 100 * cpu_count()
    print(f"{duration=},{concurrency=}")

    threads = {}

    start = datetime.now()
    count = 0

    while (datetime.now() - start) < duration:

        while len(threads) < concurrency:
            thread = TestThread(count)
            threads[count] = thread
            count += 1
            print(f"\r{datetime.now() - start} : Starting thread {count}", end="")

        # start all threads as much at the same time as possible
        for thread in threads.values():
            thread.start()

        for thread_number in list(threads):
            thread = threads[thread_number]
            print(f"\r{datetime.now() - start} : Waiting on thread {thread_number}", end="")
            thread.join()
            del threads[thread_number]

    writes_per_second = count / (datetime.now() - start).total_seconds()
    print(f"\r{datetime.now() - start},{count=},{writes_per_second=}")

    assert writes_per_second > 10  # 38 observed

    counters = get_counters()
    print(f"Cache counters: {counters}")
