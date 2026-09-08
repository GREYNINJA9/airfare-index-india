"""PostgreSQL database connector.

Drop-in replacement for SQLiteConnector that satisfies the same
DBConnector protocol. The connection wrapper re-maps the sqlite3 API
surface used in repository.py (``?`` placeholders, ``INSERT OR IGNORE``,
``row_factory``, ``executescript``, ``lastrowid``, ``rowcount``)
so existing callers work unchanged.
"""

from __future__ import annotations

import os
import re

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# Load DATABASE_URL etc. from the project .env file when present.
load_dotenv()

# Local development default (matches .env.example and docker compose defaults).
DEFAULT_PG_DSN = "postgresql://postgres:postgres@localhost:5432/airfare_index"


class _PgCursor:
    """Thin cursor wrapper that exposes ``lastrowid`` and ``rowcount``."""

    def __init__(self, pg_cursor):
        self._cur = pg_cursor
        self.lastrowid: int = 0
        self.rowcount: int = 0

    def fetchone(self):
        row = self._cur.fetchone()
        return row

    def fetchall(self):
        return self._cur.fetchall()

    def __iter__(self):
        return iter(self._cur)


class PostgresConnectionWrapper:
    """Wraps a psycopg2 connection to behave like ``sqlite3.Connection``.

    Key adaptations:
    * ``?`` → ``%s`` placeholders
    * ``INSERT OR IGNORE`` → ``INSERT … ON CONFLICT DO NOTHING``
    * ``dict``-like row access via ``RealDictCursor``
    * ``executescript`` for multi-statement DDL
    """

    def __init__(self, pg_conn):
        self.pg_conn = pg_conn

    # ---- SQL translation helpers ----

    @staticmethod
    def _rewrite_sql(sql: str) -> str:
        """Translate SQLite dialect to PostgreSQL."""
        # Parameter placeholders
        out = sql.replace("?", "%s")
        # INSERT OR IGNORE → ON CONFLICT DO NOTHING
        out = re.sub(
            r"INSERT\s+OR\s+IGNORE\s+INTO",
            "INSERT INTO",
            out,
            flags=re.IGNORECASE,
        )
        return out

    @staticmethod
    def _needs_on_conflict(sql: str) -> bool:
        return bool(re.search(r"INSERT\s+OR\s+IGNORE", sql, re.IGNORECASE))

    # ---- public API matching sqlite3.Connection ----

    def execute(self, sql: str, params: tuple = ()):
        needs_conflict = self._needs_on_conflict(sql)
        pg_sql = self._rewrite_sql(sql)

        if needs_conflict:
            # Detect target table to choose the right conflict target.
            if "fares" in pg_sql.lower():
                pg_sql = pg_sql.rstrip().rstrip(";")
                pg_sql += " ON CONFLICT (raw_offer_id) DO NOTHING"
            elif "index_results" in pg_sql.lower():
                pg_sql = pg_sql.rstrip().rstrip(";")
                pg_sql += " ON CONFLICT (base_period, current_period) DO NOTHING"

        cur = self.pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(pg_sql, params)

        wrapper = _PgCursor(cur)
        wrapper.rowcount = cur.rowcount if cur.rowcount >= 0 else 0

        if needs_conflict and wrapper.rowcount > 0:
            # Fetch the id of the just-inserted row.
            try:
                cur2 = self.pg_conn.cursor()
                cur2.execute("SELECT lastval()")
                wrapper.lastrowid = cur2.fetchone()[0]
            except Exception:
                wrapper.lastrowid = 0
        return wrapper

    def executescript(self, sql: str):
        """Execute multiple DDL statements (used by init_schema fallback)."""
        cur = self.pg_conn.cursor()
        cur.execute(sql)
        self.pg_conn.commit()

    def commit(self):
        self.pg_conn.commit()

    def close(self):
        self.pg_conn.close()


class PostgresConnector:
    """PostgreSQL-backed connector implementing the DBConnector protocol."""

    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = dsn or os.environ.get("DATABASE_URL", DEFAULT_PG_DSN)
        self._conn: PostgresConnectionWrapper | None = None

    @property
    def path(self) -> str:
        return self._dsn

    def connect(self) -> PostgresConnectionWrapper:
        if self._conn is None or self._conn.pg_conn.closed:
            pg = psycopg2.connect(self._dsn)
            pg.autocommit = True
            self._conn = PostgresConnectionWrapper(pg)
        return self._conn

    def init_schema(self) -> None:
        from database.schema import init_postgres_schema

        init_postgres_schema(self.connect())

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
