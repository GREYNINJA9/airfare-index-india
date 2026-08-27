import sys


def test_python_version() -> None:
    """Ensure Python version is >= 3.10."""
    assert sys.version_info >= (3, 10), "Python 3.10+ required"


def test_module_imports() -> None:
    """Ensure foundation dependencies can be imported cleanly."""
    import fastapi
    import playwright
    import pydantic

    assert fastapi.__version__ is not None
    assert pydantic.__version__ is not None
    assert playwright is not None
