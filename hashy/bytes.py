from typing import Callable
import hashlib


def _get_bytes_hash(b: bytes, hash_function: Callable) -> str:
    hash_object = hash_function()
    hash_object.update(b)
    hash_str = hash_object.hexdigest().lower()
    return hash_str


def get_bytes_md5(b: bytes) -> str:
    return _get_bytes_hash(b, hashlib.md5)


def get_bytes_sha256(b: bytes) -> str:
    return _get_bytes_hash(b, hashlib.sha256)


def get_bytes_sha512(b: bytes) -> str:
    return _get_bytes_hash(b, hashlib.sha512)
