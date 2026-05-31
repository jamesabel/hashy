"""
Shared hashing primitives used by the string, bytes and file hash helpers.

Every conventional hashy hash (string, bytes, file) reduces to the same three
steps: create a hashlib hash object for the chosen algorithm, feed it the input
bytes, and return the lower-case hex digest. These helpers capture that shared
logic so each public ``get_<thing>_<algorithm>`` function is a one-line wrapper
that only has to specify *what* bytes to hash and *which* algorithm to use.
"""

from typing import Callable, BinaryIO

# Number of bytes read per chunk when streaming a file. Hashing a file in fixed
# size chunks keeps memory use constant regardless of how large the file is.
FILE_CHUNK_SIZE = 4096


def hexdigest_lower(hash_object) -> str:
    """
    Return the lower-case hex digest of a populated hashlib hash object.

    :param hash_object: a hashlib hash object that has already been ``update``-d
    :return: the lower-case hexadecimal digest
    """
    return hash_object.hexdigest().lower()


def hash_bytes(data: bytes, hash_function: Callable) -> str:
    """
    Hash an in-memory bytes object.

    :param data: the bytes to hash
    :param hash_function: a hashlib constructor, e.g. ``hashlib.sha256``
    :return: the lower-case hex digest
    """
    hash_object = hash_function()
    hash_object.update(data)
    return hexdigest_lower(hash_object)


def hash_stream(stream: BinaryIO, hash_function: Callable, chunk_size: int = FILE_CHUNK_SIZE) -> str:
    """
    Hash a binary stream, reading it in fixed-size chunks so memory use stays constant.

    :param stream: a binary, readable file-like object
    :param hash_function: a hashlib constructor, e.g. ``hashlib.sha256``
    :param chunk_size: number of bytes to read per iteration
    :return: the lower-case hex digest
    """
    hash_object = hash_function()
    while chunk := stream.read(chunk_size):
        hash_object.update(chunk)
    return hexdigest_lower(hash_object)
