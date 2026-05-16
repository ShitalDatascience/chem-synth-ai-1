from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, ConfigDict, Field

from app.db.sql_loader import _load_sql

if TYPE_CHECKING:
    from app.schemas.molecule import MoleculeIdentity

logger = logging.getLogger(__name__)


class EvidenceFilters(BaseModel):
    model_config = ConfigDict(extra="ignore")

    target_keywords: List[str] = Field(default_factory=list)
    assay_types: List[str] = Field(default_factory=list)
    organisms: List[str] = Field(default_factory=list)
    min_confidence_score: Optional[int] = None
    endpoint_types: List[str] = Field(default_factory=list)
    max_rows: int = 500


class EvidenceRow(BaseModel):
    model_config = ConfigDict(extra="allow")

    activity_id: Optional[int] = None
    chembl_id: Optional[str] = None
    assay_id: Optional[int] = None
    target_chembl_id: Optional[str] = None
    target_pref_name: Optional[str] = None
    standard_type: Optional[str] = None
    standard_value: Optional[float] = None
    standard_units: Optional[str] = None
    pchembl_value: Optional[float] = None
    confidence_score: Optional[int] = None


class _CandMolecule:
    __slots__ = ("chembl_id", "pref_name", "canonical_smiles", "standard_inchi_key")

    def __init__(self, d: Dict[str, Any]) -> None:
        self.chembl_id = d.get("chembl_id")
        self.pref_name = d.get("pref_name")
        self.canonical_smiles = d.get("canonical_smiles")
        self.standard_inchi_key = d.get("standard_inchi_key")


class _Cand:
    __slots__ = ("molecule", "match_type", "confidence")

    def __init__(self, d: Dict[str, Any]) -> None:
        self.molecule = _CandMolecule(d)
        self.match_type = d.get("match_type") or "unknown"
        self.confidence = 1.0


class ChemblService:
    """ChEMBL access: legacy psycopg2 (explicit config) or pooled psycopg (no config)."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}
        self._legacy = bool(self.config.get("host"))
        self.conn = None
        # Lazy import: avoids importing rdkit/numpy unless fingerprint paths are used.
        self.fingerprint_engine = None
        self.vector_cache: List[Dict[str, Any]] = []

    def connect(self) -> None:
        if not self._legacy:
            return
        self.conn = psycopg2.connect(
            host=self.config["host"],
            database=self.config["database"],
            user=self.config["user"],
            password=self.config.get("password") or "",
        )
        logger.info("ChemblService legacy connection established")

    def _execute_fetchall(self, sql: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        if self._legacy:
            if not self.conn:
                raise RuntimeError("Legacy ChemblService: call connect() first")
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params)
                return [dict(r) for r in cur.fetchall()]
        from app.db.pg import pg_conn

        with pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return list(cur.fetchall())

    def _execute_fetchone(self, sql: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        rows = self._execute_fetchall(sql, params)
        return rows[0] if rows else None

    # ------------------------------------------------------------------
    # Orchestrator + API helpers
    # ------------------------------------------------------------------

    def get_by_chembl_id(self, chembl_id: str) -> Optional[Dict[str, Any]]:
        sql = _load_sql("get_molecule_by_chembl_id.sql")
        return self._execute_fetchone(sql, {"chembl_id": chembl_id.upper()})

    def get_molecule_by_pref_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Exact case-insensitive match on ``molecule_dictionary.pref_name``."""
        sql = _load_sql("get_molecule_by_pref_name.sql")
        return self._execute_fetchone(sql, {"name": (name or "").strip()})

    def get_molecule_by_inchi_key(self, inchi_key: str) -> Optional[Dict[str, Any]]:
        sql = _load_sql("get_molecule_by_inchi_key.sql")
        return self._execute_fetchone(sql, {"inchi_key": inchi_key})

    def get_molecule_by_canonical_smiles(self, smiles: str) -> Optional[Dict[str, Any]]:
        sql = _load_sql("get_molecule_by_canonical_smiles.sql")
        return self._execute_fetchone(sql, {"smiles": smiles})

    def get_molecules_bulk(self, chembl_ids: List[str]) -> List[Dict[str, Any]]:
        if not chembl_ids:
            return []
        sql = _load_sql("get_molecules_bulk.sql")
        return self._execute_fetchall(sql, {"chembl_ids": [c.upper() for c in chembl_ids]})

    def fetch_evidence_by_chembl_id(
        self, chembl_id: str, limit: int = 500, molregno: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        sql = _load_sql("fetch_evidence_by_chembl_id.sql")
        mr = molregno
        if mr is None:
            m = self.get_by_chembl_id(chembl_id)
            if not m or m.get("molregno") is None:
                logger.warning("fetch_evidence_by_chembl_id: missing molregno for chembl_id=%s", chembl_id)
                return []
            mr = int(m["molregno"])
        else:
            mr = int(mr)
        rows = self._execute_fetchall(sql, {"molregno": mr, "limit": limit})
        logger.info(
            "[EVIDENCE DETAIL] molregno=%s chembl_id=%s fetched_rows=%s",
            mr,
            (chembl_id or "").upper(),
            len(rows),
        )
        return rows

    def fetch_evidence_bundle_aggregates(self, molregno: int) -> Dict[str, Any]:
        """Aggregated evidence from get_evidence_bundle.sql (DB is source of truth)."""
        sql = _load_sql("get_evidence_bundle.sql")
        mr = int(molregno)
        logger.info("[EVIDENCE BUNDLE SQL] molregno=%s", mr)
        row = self._execute_fetchone(sql, {"molregno": mr})
        empty: Dict[str, Any] = {"total_activities": 0, "top_targets": [], "activity_types": {}}
        if not row:
            logger.warning("[EVIDENCE BUNDLE SQL] empty result for molregno=%s", mr)
            return empty
        bundle = row.get("evidence_bundle")
        if bundle is None and len(row) == 1:
            bundle = next(iter(row.values()))
        if bundle is None:
            logger.warning("[EVIDENCE BUNDLE SQL] no evidence_bundle column for molregno=%s keys=%s", mr, list(row))
            return empty
        if isinstance(bundle, str):
            bundle = json.loads(bundle)
        if not isinstance(bundle, dict):
            logger.warning("[EVIDENCE BUNDLE SQL] unexpected bundle type for molregno=%s: %s", mr, type(bundle))
            return empty
        tt = bundle.get("top_targets")
        at = bundle.get("activity_types")
        logger.info(
            "[EVIDENCE BUNDLE SQL] molregno=%s total_activities=%s top_targets_size=%s activity_types_size=%s",
            mr,
            bundle.get("total_activities"),
            len(tt) if isinstance(tt, list) else tt,
            len(at) if isinstance(at, dict) else at,
        )
        return bundle

    def stream_smiles_for_ingestion(
        self, last_molregno: int = 0, batch_size: int = 1000
    ) -> List[Dict[str, Any]]:
        sql = _load_sql("get_smiles_for_ingestion.sql")
        return self._execute_fetchall(
            sql, {"last_molregno": last_molregno, "batch_size": batch_size}
        )

    def resolve_molecule_with_synonyms(self, name: str) -> List[Dict[str, Any]]:
        """Return ChEMBL hits for ``name`` ranked by match strength.

        Order: exact ``pref_name`` (1.00) → exact ``molecule_synonyms`` (0.95)
        → fuzzy ``pref_name LIKE %name%`` (0.70).  Each row carries
        ``confidence`` and ``match_type``.
        """
        clean = (name or "").strip()
        if not clean:
            return []
        sql = _load_sql("resolve_molecule_with_synonyms.sql")
        params = {"name": clean, "name_like": f"%{clean}%"}
        rows = self._execute_fetchall(sql, params)
        # Stable sort by confidence desc (UNION ALL doesn't preserve order)
        rows.sort(key=lambda r: float(r.get("confidence") or 0.0), reverse=True)
        # Dedupe by chembl_id keeping first (highest-confidence) occurrence
        seen: set[str] = set()
        unique: List[Dict[str, Any]] = []
        for r in rows:
            cid = r.get("chembl_id")
            if not cid or cid in seen:
                continue
            seen.add(cid)
            unique.append(r)
        logger.info("[SYNONYM RESOLVE] %r → %d unique hits", clean, len(unique))
        return unique

    def fetch_compounds_by_target(
        self,
        name: str,
        *,
        endpoints: Optional[List[str]] = None,
        value_max_nm: Optional[float] = None,
        value_min_nm: Optional[float] = None,
        organism: Optional[str] = None,
        exclude_cell_based: bool = False,
        standard_units_allowed: Optional[List[str]] = None,
        assay_types_allowlist: Optional[List[str]] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Return ranked activity rows for compounds active on ``name``.

        ``name`` can be a target ``pref_name`` substring (e.g. ``"JAK2"``) or
        a ``CHEMBL`` target ID.  Results are filtered by endpoint type, nM
        value range and organism, then ordered by potency (pChEMBL desc, then
        standard_value asc).
        """
        sql = _load_sql("fetch_compounds_by_target.sql")
        clean_name = (name or "").strip()
        units = standard_units_allowed or ["nM"]
        allow = assay_types_allowlist or []
        params = {
            "name": clean_name,
            "name_like": f"%{clean_name}%",
            "endpoints": endpoints or ["IC50", "Ki", "Kd", "EC50"],
            "value_max_nm": value_max_nm,
            "value_min_nm": value_min_nm,
            "organism": organism,
            "exclude_cell_based": bool(exclude_cell_based),
            "has_assay_allowlist": bool(allow),
            "assay_types_allowlist": allow,
            "standard_units_allowed": units,
            "limit": int(limit),
        }
        logger.info("[TARGET LOOKUP] params=%s", params)
        rows = self._execute_fetchall(sql, params)
        logger.info("[TARGET LOOKUP] rows=%d for name=%r", len(rows), name)
        return rows

    def search_by_name(self, name: str, limit: int = 10) -> List[Dict[str, Any]]:
        sql = _load_sql("resolve_molecule_by_name.sql")
        params = {
            "name": name,
            "name_like": f"%{name}%",
            "limit": limit,
        }
        logger.info(f"[ChEMBL SEARCH] SQL params: {params}")
        rows = self._execute_fetchall(sql, params)
        if rows:
            top = rows[0]
            logger.info(
                "Resolved query %r to %s | %s",
                name,
                top.get("chembl_id"),
                top.get("pref_name"),
            )
        return rows

    def search_molecule_by_name(self, name: Optional[str], limit: int = 10) -> List[Dict[str, Any]]:
        """Alias for :meth:`search_by_name` (debug / legacy call sites)."""
        if not (name or "").strip():
            return []
        return self.search_by_name(str(name).strip(), limit=limit)

    def resolve_molecule_by_name(self, text: str, limit: int = 5) -> List[_Cand]:
        rows = self.search_by_name(text, limit=limit)
        out: List[_Cand] = []
        for r in rows:
            cid = r.get("chembl_id")
            full = self.get_by_chembl_id(cid) if cid else None
            merged = {**r, **(full or {})}
            out.append(_Cand(merged))
        return out

    def get_evidence_bundle(
        self, chembl_ids: List[str], filters: Optional[EvidenceFilters] = None
    ) -> List[EvidenceRow]:
        filt = filters or EvidenceFilters()
        rows: List[Dict[str, Any]] = []
        for cid in chembl_ids:
            rows.extend(self.fetch_evidence_by_chembl_id(cid, limit=filt.max_rows))
        if filt.min_confidence_score is not None:
            rows = [
                r
                for r in rows
                if (r.get("confidence_score") or 0) >= filt.min_confidence_score
            ]
        if filt.endpoint_types:
            allowed = {x.upper() for x in filt.endpoint_types}
            rows = [r for r in rows if (r.get("standard_type") or "").upper() in allowed]
        rows = rows[: filt.max_rows]
        return [EvidenceRow.model_validate(dict(r)) for r in rows]

    def get_molecule_identity_by_chembl_id(self, chembl_id: str) -> Optional["MoleculeIdentity"]:
        from app.schemas.molecule import MoleculeIdentity

        row = self.get_by_chembl_id(chembl_id)
        if not row:
            return None
        mw = row.get("mw_freebase")
        if mw is None and row.get("canonical_smiles"):
            try:
                from app.services import rdkit_service

                mw = rdkit_service.validate_smiles(row["canonical_smiles"]).mw
            except Exception:
                mw = None
        return MoleculeIdentity(
            chembl_id=str(row["chembl_id"]),
            pref_name=row.get("pref_name"),
            canonical_smiles=row.get("canonical_smiles"),
            inchi_key=row.get("standard_inchi_key"),
            molecular_weight=float(mw) if mw is not None else None,
        )

    def get_molecule_identity_by_inchi_key(self, inchi_key: str) -> Optional["MoleculeIdentity"]:
        from app.schemas.molecule import MoleculeIdentity

        row = self.get_molecule_by_inchi_key(inchi_key)
        if not row:
            return None
        mw = row.get("mw_freebase")
        return MoleculeIdentity(
            chembl_id=str(row["chembl_id"]),
            pref_name=row.get("pref_name"),
            canonical_smiles=row.get("canonical_smiles"),
            inchi_key=row.get("standard_inchi_key"),
            molecular_weight=float(mw) if mw is not None else None,
        )

    def get_activities_by_mol(self, chembl_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        return self.fetch_evidence_by_chembl_id(chembl_id, limit=limit)

    def get_molecule_summary(self, chembl_id: str, limit: int = 50) -> Dict[str, Any]:
        mol = self.get_by_chembl_id(chembl_id)
        ev = self.fetch_evidence_by_chembl_id(chembl_id, limit=limit)
        return {"molecule": mol, "evidence_count": len(ev), "sample": ev[:5]}

    # ------------------------------------------------------------------
    # Legacy-only vector helpers (psycopg2 connection)
    # ------------------------------------------------------------------

    def get_molecule_fingerprint(self, chembl_id: str) -> Optional[Dict[str, Any]]:
        if not self._legacy or not self.conn:
            logger.warning("get_molecule_fingerprint requires legacy connected ChemblService")
            return None
        try:
            if self.fingerprint_engine is None:
                from app.services.rdkit_service import RDKitFingerprint

                self.fingerprint_engine = RDKitFingerprint()
            cursor = self.conn.cursor(cursor_factory=RealDictCursor)
            query = """
                SELECT md.chembl_id, cs.canonical_smiles
                FROM molecule_dictionary md
                JOIN compound_structures cs ON md.molregno = cs.molregno
                WHERE md.chembl_id = %s
            """
            cursor.execute(query, (chembl_id,))
            row = cursor.fetchone()
            if not row:
                return None
            smiles = row["canonical_smiles"]
            fingerprint = self.fingerprint_engine.generate(smiles)
            return {"chembl_id": row["chembl_id"], "smiles": smiles, "fingerprint": fingerprint}
        except Exception as exc:
            logger.error("Fingerprint generation failed: %s", exc)
            return None

    def build_vector_index(self, limit: int = 100) -> List[Dict[str, Any]]:
        if not self._legacy or not self.conn:
            return []
        try:
            if self.fingerprint_engine is None:
                from app.services.rdkit_service import RDKitFingerprint

                self.fingerprint_engine = RDKitFingerprint()
            cursor = self.conn.cursor()
            query = """
                SELECT md.chembl_id, cs.canonical_smiles
                FROM molecule_dictionary md
                JOIN compound_structures cs ON md.molregno = cs.molregno
                LIMIT %s
            """
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
            dataset: List[Dict[str, Any]] = []
            for chembl_id, smiles in rows:
                if not smiles:
                    continue
                fp = self.fingerprint_engine.generate(smiles)
                dataset.append({"chembl_id": chembl_id, "smiles": smiles, "embedding": fp})
            self.vector_cache = dataset
            return dataset
        except Exception as exc:
            logger.error("Vector index build failed: %s", exc)
            return []
