import os

from setuptools import setup

from hashy.__version__ import __version__, __title__, __author__, __author_email__, __url__, __download_url__, __description__

readme_file_path = os.path.join("readme.md")

with open(readme_file_path, encoding="utf-8") as f:
    long_description = "\n" + f.read()

setup(
    name=__title__,
    description=__description__,
    long_description=long_description,
    long_description_content_type="text/markdown",
    version=__version__,
    author=__author__,
    author_email=__author_email__,
    license="MIT License",
    url=__url__,
    download_url=__download_url__,
    keywords=["hash"],
    packages=[__title__],
    package_data={__title__: [readme_file_path, "py.typed"]},
    install_requires=["platformdirs", "sqlitedict"],
    classifiers=[],
)
