"""
Conventional md5/sha256/sha512/crc64nvme hashes for files.

Files are read and hashed in fixed-size chunks (see ``_hash_core.hash_stream``)
so that memory use stays constant regardless of file size. The resulting digests
match those from any standard tool for the same file contents.
"""

from pathlib import Path
import hashlib
from typing import Callable, Union

from ._crc64nvme import Crc64Nvme
from ._hash_core import hash_stream


def get_file_md5(file_path: Union[Path, str]) -> str:
    """Return the md5 hex digest of the file at ``file_path``."""
    return _hash_file(file_path, hashlib.md5)


def get_file_sha256(file_path: Union[Path, str]) -> str:
    """Return the sha256 hex digest of the file at ``file_path``."""
    return _hash_file(file_path, hashlib.sha256)


def get_file_sha512(file_path: Union[Path, str]) -> str:
    """Return the sha512 hex digest of the file at ``file_path``."""
    return _hash_file(file_path, hashlib.sha512)


def get_file_crc64nvme(file_path: Union[Path, str]) -> str:
    """Return the CRC-64/NVME hex digest of the file at ``file_path``."""
    return _hash_file(file_path, Crc64Nvme)


def _hash_file(file_path: Union[Path, str], hash_function: Callable) -> str:
    """Open ``file_path`` in binary mode and hash its contents with ``hash_function``."""
    with open(file_path, "rb") as f:
        return hash_stream(f, hash_function)
