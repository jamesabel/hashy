# hashy

Another hash library, but with a twist. It provides a simple interface to generate hashes for strings, files, dicts, 
lists and sets. It also provides a decorator to cache the results of a function to disk and (optionally) memory.

## Installation

```
pip install hashy
```

## Introduction

hashy provides an md5, sha256 or sha512 for string, file, dict, list and set.

String and file hashes are conventional and can be compared to other implementations. For example,
you can go to an online hash calculator for "a" and get the same hash as hashy generates.

Hashes for complex data types like dict, list and set are specific to hashy.

Supports multithreading and multiprocessing, via the `sqlitedict` library. While the `sqlite` database itself is not 
thread-safe/process-safe, the `sqlitedict` library provides a thread-safe/process-safe interface.

## cachy

`hashy` also provides `cachy`, a decorator that can be used to persistently cache the results of a function to 
disk and (optionally) memory. It is similar to `@functools.cache`, except:

- Persistent (saved to local disk in a sqlite database)
  - Optionally can be saved to a user-specified directory, otherwise it's the usual cache directory for the OS
- Optional user-specified cache life.
- Doesn't require arguments be frozen and/or pickle-able. Uses hashy to create a hash of the arguments.


# Example

```

from hashy import get_string_sha256, cachy

print(get_string_sha256("a"))  # prints ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb

@cachy()
def func(a):
    return a + a

print(func(2))  # prints 4

```
