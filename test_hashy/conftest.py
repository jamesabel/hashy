import shutil

from dotenv import load_dotenv, find_dotenv

import pytest

from .test_cachy import get_cache_directory

load_dotenv(find_dotenv())


@pytest.fixture(scope="session", autouse=True)
def delete_cache_directory():
    shutil.rmtree(get_cache_directory(), ignore_errors=True)
