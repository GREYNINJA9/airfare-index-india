"""Database connector components.

Provides a thin, replaceable connector abstraction so that the current
SQLite prototype can later be swapped for PostgreSQL (or any other
backend) by changing a single connector implementation.

All other database modules depend on these components and on the
connector's public methods, never on a specific backend's connection
object directly.
"""

from __future__ import annotations

import sqlite3
from typing import Protocol, runtime_checkable

#: Path to the SQLite database file used by the prototype.
DEFAULT_SQLITE_PATH = "data/airfare_index.db"


@runtime_checkable
class DBConnector(Protocol):
    """Minimal connector contract used by schema and repository code.

    A connector owns a connection and exposes:

        connect()      → returns a backend connection object
        init_schema()  → ensures the schema exists
        close()        → releases resources
    """

    def connect(self): ...

    def init_schema(self) -> None: ...

    def close(self) -> None: ...


class SQLiteConnector:
    """SQLite-backed connector for the development prototype.

    The connection is opened lazily and cached. ``check_same_thread=False``
    is required so FastAPI worker threads can reuse the connection.
    """

    def __init__(self, path: str = DEFAULT_SQLITE_PATH) -> None:
        self._path = path
        self._conn: sqlite3.Connection | None = None

    @property
    def path(self) -> str:
        return self._path

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def init_schema(self) -> None:
        from database.schema import init_schema

        init_schema(self.connect())

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


def get_connector() -> DBConnector:
    """Return the active connector for this environment.

    Swapping the database backend later is a matter of changing this
    function — everything else stays the same.
    """
    return SQLiteConnector()
