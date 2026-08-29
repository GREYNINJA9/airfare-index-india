"""Database package.

Provides a replaceable connector abstraction, schema initialization,
and repository helpers for fare observations.

The connector lives in :mod:`database.components` and is used via
:mod:`database.connection`. The schema is in :mod:`database.schema`.
Persistence helpers are in :mod:`database.repository`.

Swapping SQLite → PostgreSQL later is a single-connector change; the
rest of the package depends on the connector protocol only.
"""

from database.components import DBConnector, SQLiteConnector, get_connector
from database.connection import close_connection, get_connection, reset_connection

__all__ = [
    "DBConnector",
    "SQLiteConnector",
    "close_connection",
    "get_connection",
    "get_connector",
    "reset_connection",
]
