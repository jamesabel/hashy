from pathlib import Path
from datetime import timedelta
import time
from multiprocessing import Process, Queue

from hashy import cachy

test_name = "test_cachy_default_arguments"

temp_dir = Path("temp", test_name)

cache_life = timedelta(minutes=10)

# should never cache since time.time() will always be different
@cachy(cache_life, temp_dir)
def get_time(t: float = time.time()) -> float:
    return t

class CacheClass(Process):

    def __init__(self):
        Process.__init__(self)
        self.queue = Queue()

    def run(self):
        self.queue.put(get_time())

    def get(self):
        return self.queue.get()


def test_cachy_default_arguments():
    """
    Default argument values must participate in the cache key.

    ``get_time`` has a default ``t=time.time()`` that is evaluated once per module
    import. Each spawned process re-imports the module and therefore freezes a
    *different* default. Because the default is never passed explicitly, it does not
    appear in ``*args``/``**kwargs``; cachy must resolve it from the function
    signature, otherwise every process would collide on the same (empty-argument) key
    and read back the first process's cached value.

    So each process should return its own distinct default value.
    """

    values = []
    iterations = 10
    for count in range(iterations):
        c = CacheClass()
        c.start()
        c.join()
        values.append(c.get())
        time.sleep(0.001)
    assert len(values) == iterations
    # No two processes collided on a shared cache entry: every value is distinct.
    assert len(set(values)) == iterations
