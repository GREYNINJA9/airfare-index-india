"""SQLite database connection (prototype layer).

This module owns the concrete connector used in Day 3. Swapping to
PostgreSQL later is a matter of changing this module's implementation;
all consumers (repository, tests) depend on :class:`SQLiteConnector`
via the :class:`components.DBConnector` protocol, so they will not
need to change.
"""

from __future__ import annotations

from database.components import SQLiteConnector

_global_connector: SQLiteConnector | None = None


def _get_connector() -> SQLiteConnector:
    """Return or create the module-level SQLite connector singleton."""
    global _global_connector  # noqa: PLW0603
    if _global_connector is None:
        _global_connector = SQLiteConnector()
    return _global_connector


def get_connection():
    """Return a live ``sqlite3.Connection`` via the connector singleton."""
    return _get_connector().connect()


def close_connection() -> None:
    """Close the current connection, if any. Safe to call multiple times."""
    global _global_connector  # noqa: PLW0603
    if _global_connector is not None:
        _global_connector.close()
        _global_connector = None


def reset_connection(path: str | None = None):
    """Close and recreate the connector, then connect. Used in tests.

    Returns the live connection so callers can initialize the schema and
    use it directly.
    """
    global _global_connector  # noqa: PLW0603
    if _global_connector is not None:
        _global_connector.close()
    _global_connector = SQLiteConnector(path=path or "data/airfare_index.db")
    return _global_connector.connect()
