"""Database connection management.

This module owns the concrete connector used in the app.
Swapped to PostgreSQL exclusively as per project requirements.
"""

from __future__ import annotations

from database.components import PostgresConnector
from database.postgres import DEFAULT_PG_DSN

_global_connector: object | None = None


def _get_connector():
    """Return or create the module-level Postgres connector singleton."""
    global _global_connector  # noqa: PLW0603
    if _global_connector is None:
        _global_connector = PostgresConnector(dsn=DEFAULT_PG_DSN)
    return _global_connector


def get_connection():
    """Return a live connection via the connector singleton."""
    return _get_connector().connect()


def close_connection() -> None:
    """Close the current connection, if any. Safe to call multiple times."""
    global _global_connector  # noqa: PLW0603
    if _global_connector is not None:
        _global_connector.close()
        _global_connector = None


def reset_connection(dsn: str | None = None):
    """Close and recreate the connector, then connect. Used in tests.

    Returns the live connection so callers can initialize the schema and
    use it directly.
    """
    global _global_connector  # noqa: PLW0603
    if _global_connector is not None:
        _global_connector.close()

    # Default to local development DSN for tests
    target_dsn = dsn or DEFAULT_PG_DSN
    _global_connector = PostgresConnector(dsn=target_dsn)
    return _global_connector.connect()