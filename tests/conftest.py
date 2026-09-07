"""Shared pytest fixtures.

All tests run against the live PostgreSQL ``airfare_index`` database
(connection string from ``DATABASE_URL`` or the local default). Per-test
isolation is achieved by truncating the data tables before each test.
"""

from __future__ import annotations

import pytest

from database.connection import close_connection, reset_connection
from database.schema import init_schema, truncate_tables


def _fresh_postgres_connection():
    """Return a live PostgreSQL connection with the schema ready and tables empty."""
    conn = reset_connection()
    init_schema(conn)
    truncate_tables(conn)
    return conn


@pytest.fixture()
def db():
    """Function-scoped fixture: live PostgreSQL connection, tables truncated."""
    conn = _fresh_postgres_connection()
    try:
        yield conn
    finally:
        close_connection()