"""Phase-0 smoke tests: the package imports, is versioned, and ships its type marker."""

from importlib.resources import files

import rememberstack


def test_package_imports_and_has_version() -> None:
    assert isinstance(rememberstack.__version__, str)
    assert rememberstack.__version__ != ""


def test_package_ships_py_typed_marker() -> None:
    assert files("rememberstack").joinpath("py.typed").is_file()
