"""Database connector components.

Provides the primary PostgresConnector interface used throughout the app.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from database.postgres import DEFAULT_PG_DSN, PostgresConnectionWrapper, PostgresConnector


@runtime_checkable
class DBConnector(Protocol):
    """Minimal connector contract used by schema and repository code."""

    def connect(self) -> PostgresConnectionWrapper: ...

    def init_schema(self) -> None: ...

    def close(self) -> None: ...


def get_connector() -> PostgresConnector:
    """Return the active PostgreSQL connector."""
    return PostgresConnector()


__all__ = ["DBConnector", "PostgresConnector", "DEFAULT_PG_DSN", "get_connector"]