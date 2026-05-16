"""Legacy connection helper — thin wrapper around pg_conn() for backwards compat.

New code should import pg_conn directly from app.db.pg.
"""
from __future__ import annotations

from app.db.pg import pg_conn, get_pg_dsn  # noqa: F401


def get_db():
    """Kept for legacy callers. Returns a raw psycopg connection (psycopg3)."""
    import psycopg
    from psycopg.rows import dict_row

    dsn = get_pg_dsn()
    return psycopg.connect(dsn, row_factory=dict_row)
