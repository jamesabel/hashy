"""
Loaded by pytest before anything under test_hashy, so that on free-threaded Python gilguard is watching before hashy
and its dependencies are imported: an import that re-enables the GIL then fails the run instead of passing silently.

gilguard raises on a standard (GIL) build, so it is only imported on a free-threaded one.
"""

import sysconfig

if sysconfig.get_config_var("Py_GIL_DISABLED"):
    import gilguard  # noqa: F401  # imported for its effect: it installs the import guard
