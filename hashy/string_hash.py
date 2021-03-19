from typing import Callable
import hashlib


def _get_string_hash(s: str, hash_function: Callable) -> str:
    hash_object = hash_function()
    hash_object.update(s.encode())
    hash_str = hash_object.hexdigest().lower()
    return hash_str


def get_string_md5(s: str) -> str:
    return _get_string_hash(s, hashlib.md5)


def get_string_sha256(s: str) -> str:
    return _get_string_hash(s, hashlib.sha256)


def get_string_sha512(s: str) -> str:
    return _get_string_hash(s, hashlib.sha512)
