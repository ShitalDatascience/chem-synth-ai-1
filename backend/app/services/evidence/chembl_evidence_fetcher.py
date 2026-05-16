import logging

from app.db.pg import pg_conn
from app.db.sql_loader import _load_sql
from app.services.chembl_service import ChemblService

logger = logging.getLogger(__name__)


class ChemblEvidenceFetcher:

    @staticmethod
    def fetch_by_chembl_id(chembl_id: str, limit: int = 100):

        sql = _load_sql("fetch_evidence_by_chembl_id.sql")
        mol_row = ChemblService().get_by_chembl_id(chembl_id)
        if not mol_row or mol_row.get("molregno") is None:
            logger.warning("ChemblEvidenceFetcher: no molregno for chembl_id=%s", chembl_id)
            return []
        params = {
            "molregno": int(mol_row["molregno"]),
            "limit": limit,
        }

        with pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()

        if not rows:
            return []

        evidence = []

        for r in rows:
            # psycopg may return dict or tuple depending config
            if isinstance(r, dict):
                evidence.append({
                    "activity_id": r.get("activity_id"),
                    "assay_id": r.get("assay_id"),
                    "target_chembl_id": r.get("target_chembl_id"),
                    "target_name": r.get("target_pref_name"),
                    "standard_type": r.get("standard_type"),
                    "standard_value": r.get("standard_value"),
                    "standard_units": r.get("standard_units"),
                    "pchembl_value": r.get("pchembl_value"),
                    "confidence": r.get("confidence_score"),
                })
            else:
                evidence.append({
                    "activity_id": r[0],
                    "assay_id": r[1],
                    "target_chembl_id": r[2],
                    "target_name": r[3],
                    "standard_type": r[4],
                    "standard_value": r[5],
                    "standard_units": r[6],
                    "pchembl_value": r[7],
                    "confidence": r[8],
                })

        return evidence