from pathlib import Path
from datetime import timedelta, datetime
import shutil
from multiprocessing import Process
from queue import Queue

from psutil import cpu_count

from hashy import cachy

test_name = "test_cachy_concurrency"

temp_dir = Path("temp", test_name)

duration = timedelta(seconds=30)


@cachy(cache_dir=temp_dir, in_memory=True)
def _function(x):
    result = x + 1
    return result


def test_cachy_concurrency():
    """
    Test that the cachy decorator works in a concurrent (multithreaded, multiprocessing) environment.
    """

    shutil.rmtree(temp_dir, ignore_errors=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    concurrency = cpu_count()
    print(f"{duration=},{concurrency=}")

    processes = {}

    start = datetime.now()
    count = 0

    while (datetime.now() - start) < duration:
        while len(processes) < concurrency:
            queue = Queue()
            process = Process(target=_function, args=(count,))
            processes[count] = process
            count += 1
            print(f"\r{datetime.now() - start} : Starting process {count}", end="")

        # start all processes as much at the same time as possible
        for process in processes.values():
            process.start()

        for process_number in list(processes):
            process = processes[process_number]
            print(f"\r{datetime.now() - start} : Waiting on process {process_number}", end="")
            process.join()
            del processes[process_number]

    writes_per_second = count / (datetime.now() - start).total_seconds()
    print(f"\r{datetime.now() - start},{count=},{writes_per_second=}")

    assert writes_per_second > 5  # 9.7 observed
