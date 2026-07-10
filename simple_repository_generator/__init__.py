"""
Documentation for the simple_repository_generator package

"""
# Import the version from the generated _version.py file. __version__ is part
# of the public API, and we therefore ignore the "unused" (F401) lint warning.
from ._api import DumpResult, dump_static
from ._version import __version__  # noqa: F401  # pylint: disable=import-error

__all__ = ["DumpResult", "dump_static", "__version__"]
