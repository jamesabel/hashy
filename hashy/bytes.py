"""Conventional md5/sha256/sha512 hashes for in-memory ``bytes`` objects."""

import hashlib

from ._hash_core import hash_bytes


def get_bytes_md5(b: bytes) -> str:
    """Return the md5 hex digest of ``b``."""
    return hash_bytes(b, hashlib.md5)


def get_bytes_sha256(b: bytes) -> str:
    """Return the sha256 hex digest of ``b``."""
    return hash_bytes(b, hashlib.sha256)


def get_bytes_sha512(b: bytes) -> str:
    """Return the sha512 hex digest of ``b``."""
    return hash_bytes(b, hashlib.sha512)
