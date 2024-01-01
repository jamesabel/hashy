# hashy

Another hash library.

hashy provides an md5, sha256 or sha512 for string, file, dict, list and set.

String and file hashes are conventional and can be compared to other implementations. For example
you can go to an online hash calculator for "a" and get the same hash as hashy generates.

Hashes for complex data types like dict, list and set are specific to hashy.

## cachy

`hashy` also provides `cachy`, a decorator that can be used to persistently cache the results of a function to 
disk. It is similar to `@functools.cache`, except:

- Persistent (saved to local disk)
  - Optionally can be saved to a user-specified directory, otherwise it's the usual cache directory for the OS
- User-specified cache life.
- Doesn't require arguments be frozen and/or pickle-able. Uses hashy to create a hash of the arguments.


# Example

```

from hashy import get_string_sha256

print(get_string_sha256("a"))

# prints
# ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb

```
