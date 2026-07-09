"""Phase-0 smoke tests: the package imports, is versioned, and ships its type marker."""

from importlib.resources import files

import ultimate_memory


def test_package_imports_and_has_version() -> None:
    assert isinstance(ultimate_memory.__version__, str)
    assert ultimate_memory.__version__ != ""


def test_package_ships_py_typed_marker() -> None:
    assert files("ultimate_memory").joinpath("py.typed").is_file()
