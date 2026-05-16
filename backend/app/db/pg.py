from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator, Optional

import psycopg
from psycopg.rows import dict_row


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name)
    return v if v not in (None, "") else default


def get_pg_dsn() -> str:
    """
    DSN is resolved in this order:
    - DATABASE_URL
    - PG* variables (with defaults from the plan)
    """
    direct = _env("DATABASE_URL")
    if direct:
        return direct

    dbname = _env("PGDATABASE", _env("DB_NAME", "chembl_db"))
    user = _env("PGUSER", _env("DB_USER", "shitalkale"))
    password = _env("PGPASSWORD", _env("DB_PASSWORD", ""))
    host = _env("PGHOST", _env("DB_HOST", "localhost"))
    port = _env("PGPORT", _env("DB_PORT", "5432"))

    parts = [f"dbname={dbname}", f"user={user}", f"host={host}", f"port={port}"]
    if password:
        parts.append(f"password={password}")
    return " ".join(parts)


@contextmanager
def pg_conn() -> Iterator[psycopg.Connection]:
    statement_timeout_ms = int(_env("PG_STATEMENT_TIMEOUT_MS", "30000") or "30000")

    with psycopg.connect(get_pg_dsn(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(f"SET statement_timeout = {statement_timeout_ms};")
        yield conn

