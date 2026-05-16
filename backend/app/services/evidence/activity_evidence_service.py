from __future__ import annotations

"""Phase 2 evidence retrieval by activity_id (minimal).

- Fetches original record from Postgres (no over-engineering).
- Returns assay + target context if available.
"""

from typing import Any, Dict, Optional

from app.db.pg import pg_conn
from app.db.sql_loader import _load_sql
from app.services.chembl.activity_cleaner import ActivityCleaner


_EVIDENCE_CACHE: dict[int, dict[str, Any]] = {}


def get_evidence(activity_id: str) -> Optional[Dict[str, Any]]:
    try:
        aid = int(activity_id)
    except Exception:
        return None

    if aid in _EVIDENCE_CACHE:
        return _EVIDENCE_CACHE[aid]

    sql = _load_sql("get_evidence_by_activity_id.sql")
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"activity_id": aid})
            row = cur.fetchone()

    if not row:
        return None

    # row_factory=dict_row => dict
    cleaned = ActivityCleaner.clean_row(row)

    out: dict[str, Any] = {
        "activity_id": row.get("activity_id"),
        "assay": {
            "assay_id": row.get("assay_id"),
            "assay_chembl_id": row.get("assay_chembl_id"),
            "assay_type": row.get("assay_type"),
            "confidence_score": row.get("confidence_score"),
            "description": row.get("assay_description"),
        },
        "target": {
            "target_chembl_id": row.get("target_chembl_id"),
            "target_name": row.get("target_pref_name"),
            "target_type": row.get("target_type"),
            "organism": row.get("target_organism"),
        },
        "standard_type": (cleaned or {}).get("standard_type") or row.get("standard_type"),
        "value_nm": (cleaned or {}).get("value_nm"),
        "pchembl": (cleaned or {}).get("pchembl"),
    }

    _EVIDENCE_CACHE[aid] = out
    return out

