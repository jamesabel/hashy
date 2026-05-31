"""
Conventional md5/sha256/sha512 hashes for strings.

The string is UTF-8 encoded before hashing, so these digests match those from
any standard tool (e.g. an online hash calculator) for the same text.
"""

import hashlib

from ._hash_core import hash_bytes


def get_string_md5(s: str) -> str:
    """Return the md5 hex digest of ``s`` (UTF-8 encoded)."""
    return hash_bytes(s.encode(), hashlib.md5)


def get_string_sha256(s: str) -> str:
    """Return the sha256 hex digest of ``s`` (UTF-8 encoded)."""
    return hash_bytes(s.encode(), hashlib.sha256)


def get_string_sha512(s: str) -> str:
    """Return the sha512 hex digest of ``s`` (UTF-8 encoded)."""
    return hash_bytes(s.encode(), hashlib.sha512)
