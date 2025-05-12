from pathlib import Path
import os


def get_cache_directory() -> Path:
    cache_directory = Path(os.environ.get("RUNNER_TEMP", "temp"))  # for GitHub actions
    return cache_directory
