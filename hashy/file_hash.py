from pathlib import Path
import hashlib


def get_file_md5(file_path: (Path, str)) -> str:
    return _get_file_hash(file_path, hashlib.md5)


def get_file_sha256(file_path: (Path, str)) -> str:
    return _get_file_hash(file_path, hashlib.sha256)


def get_file_sha512(file_path: (Path, str)) -> str:
    return _get_file_hash(file_path, hashlib.sha512)


def _get_file_hash(file_path: (Path, str), hash_function) -> str:
    hash_object = hash_function()

    bucket_size = 4096  # for speed
    with open(file_path, "rb") as f:
        val = f.read(bucket_size)
        while len(val) > 0:
            hash_object.update(val)
            val = f.read(bucket_size)

        hash_str = hash_object.hexdigest().lower()

    return hash_str
