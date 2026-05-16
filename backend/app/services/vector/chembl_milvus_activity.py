from __future__ import annotations

"""Phase 2 Milvus activity-vector layer (minimal, production-clean).

Collection: chembl_molecules
Schema (STRICT, no extra fields):
- activity_id (primary key)
- target_chembl_id
- fingerprint (float vector, dim=2048)
- pchembl
- value_nm
- standard_type
"""

import logging
import os
from typing import Any, Dict, List, Optional

from app.config import get_settings
from app.services import rdkit_service

logger = logging.getLogger(__name__)

try:
    from pymilvus import DataType, MilvusClient

    _MILVUS_AVAILABLE = True
except ImportError:
    _MILVUS_AVAILABLE = False


def _require_milvus() -> None:
    if not _MILVUS_AVAILABLE:
        raise RuntimeError("pymilvus is not installed")


COLLECTION_NAME = "chembl_molecules"
FP_DIM = rdkit_service.FP_NBITS


class ChemblMilvusActivityService:
    def __init__(self) -> None:
        _require_milvus()
        self._db_path: str = get_settings().milvus_db_path
        self._client: Optional["MilvusClient"] = None  # type: ignore[type-arg]

    def _get_client(self) -> "MilvusClient":  # type: ignore[type-arg]
        if self._client is None:
            if not self._db_path.startswith("http"):
                parent = os.path.dirname(os.path.abspath(self._db_path))
                os.makedirs(parent, exist_ok=True)
            # Do NOT log success until we have executed an exception-free call.
            self._client = MilvusClient(uri=self._db_path)
        return self._client

    def verify_milvus_ready(self) -> None:
        """Strict pre-check before any Milvus operation (Milvus Lite version).

        Phase 2 uses Milvus Lite (embedded file-backed), so there is no TCP port to check.
        Readiness means:
        - the db path directory is writable (for local uri)
        - MilvusClient can be constructed
        - a trivial API call succeeds exception-free
        """
        client = self._get_client()

        if not self._db_path.startswith("http"):
            parent = os.path.dirname(os.path.abspath(self._db_path))
            if not os.path.isdir(parent):
                raise RuntimeError(f"Milvus Lite parent dir does not exist: {parent}")
            if not os.access(parent, os.W_OK):
                raise RuntimeError(f"Milvus Lite parent dir not writable: {parent}")

        # Trivial call: has_collection is safe and fast.
        _ = client.has_collection(COLLECTION_NAME)
        logger.info("Milvus Lite verified (uri=%s)", self._db_path)

    def ensure_collection(self) -> None:
        self.verify_milvus_ready()
        client = self._get_client()
        if client.has_collection(COLLECTION_NAME):
            return

        schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("activity_id", DataType.INT64, is_primary=True)
        schema.add_field("target_chembl_id", DataType.VARCHAR, max_length=32)
        schema.add_field("fingerprint", DataType.FLOAT_VECTOR, dim=FP_DIM)
        schema.add_field("pchembl", DataType.FLOAT)
        schema.add_field("value_nm", DataType.FLOAT)
        schema.add_field("standard_type", DataType.VARCHAR, max_length=16)

        index_params = client.prepare_index_params()
        index_params.add_index(
            field_name="fingerprint",
            index_type="FLAT",
            metric_type="COSINE",
        )

        client.create_collection(
            collection_name=COLLECTION_NAME,
            schema=schema,
            index_params=index_params,
        )
        logger.info("Created Milvus collection: %s", COLLECTION_NAME)

    def ingest_to_milvus(self, clean_rows: List[Dict[str, Any]]) -> int:
        """Batch upsert clean activity rows into Milvus.

        Each row must contain:
        - activity_id
        - target_chembl_id
        - smiles
        - standard_type
        - value_nm
        - pchembl
        - is_valid
        """
        self.ensure_collection()
        client = self._get_client()

        batch: List[Dict[str, Any]] = []
        for r in clean_rows:
            if not r or r.get("is_valid") is False:
                logger.debug("Skipping invalid row (is_valid==False or empty)")
                continue

            smiles = r.get("smiles") or r.get("canonical_smiles")
            if not smiles:
                logger.debug("Skipping row missing smiles (activity_id=%s)", r.get("activity_id"))
                continue

            try:
                fp_arr, _ = rdkit_service.morgan_fp(smiles)
                fp_bits = [int(round(float(x))) for x in fp_arr.tolist()]
            except Exception:
                fp_bits = None
            if fp_bits is None or len(fp_bits) != FP_DIM:
                logger.error(
                    "Fingerprint generation failed or wrong dim (activity_id=%s dim=%s)",
                    r.get("activity_id"),
                    None if fp_bits is None else len(fp_bits),
                )
                continue

            try:
                activity_id = int(r.get("activity_id"))
            except Exception:
                logger.error("Skipping row with non-int activity_id=%r", r.get("activity_id"))
                continue

            # STRICT: schema consistency — use ONLY target_chembl_id.
            target_chembl_id = r.get("target_chembl_id")
            if not target_chembl_id:
                logger.error("Skipping row missing target_chembl_id (activity_id=%s)", activity_id)
                continue

            standard_type = str(r.get("standard_type") or "")[:16]

            batch.append(
                {
                    "activity_id": activity_id,
                    "target_chembl_id": str(target_chembl_id)[:32],
                    "fingerprint": [float(x) for x in fp_bits],
                    "pchembl": float(r.get("pchembl") or 0.0),
                    "value_nm": float(r.get("value_nm") or 0.0),
                    "standard_type": standard_type,
                }
            )

        if not batch:
            logger.error("Ingestion produced 0 valid vectors — nothing to upsert")
            return 0

        res = client.upsert(collection_name=COLLECTION_NAME, data=batch)
        upserted = int(res.get("upsert_count", len(batch)))
        logger.info("Milvus upsert complete: %d rows", upserted)
        return upserted

    def search_similar(self, fingerprint: List[int], top_k: int = 10) -> List[Dict[str, Any]]:
        """Milvus similarity search over activity fingerprints."""
        self.ensure_collection()
        client = self._get_client()

        if not fingerprint or len(fingerprint) != FP_DIM:
            logger.error("search_similar called with bad fingerprint dim=%s", len(fingerprint) if fingerprint else None)
            return []

        results = client.search(
            collection_name=COLLECTION_NAME,
            data=[[float(x) for x in fingerprint]],
            limit=top_k,
            output_fields=["activity_id", "target_chembl_id", "pchembl", "value_nm"],
            search_params={"metric_type": "COSINE"},
        )

        hits = results[0] if results else []
        logger.info("Milvus search returned %d hits", len(hits))
        out: List[Dict[str, Any]] = []
        for h in hits:
            entity = h.get("entity", {}) or {}
            out.append(
                {
                    "activity_id": entity.get("activity_id"),
                    "target_chembl_id": entity.get("target_chembl_id"),
                    "score": float(h.get("distance", 0.0)),
                    "pchembl": entity.get("pchembl"),
                    "value_nm": entity.get("value_nm"),
                }
            )
        return out


# ---------------------------------------------------------------------------
# Module-level wrapper layer (required by tests)
# ---------------------------------------------------------------------------

_service = ChemblMilvusActivityService()


def verify_milvus_ready() -> bool:
    _service.verify_milvus_ready()
    return True


def ensure_collection() -> bool:
    _service.ensure_collection()
    return True


def ingest_to_milvus(clean_rows: List[Dict[str, Any]]) -> int:
    return _service.ingest_to_milvus(clean_rows)


def search_similar(fingerprint: List[int], top_k: int = 10) -> List[Dict[str, Any]]:
    return _service.search_similar(fingerprint, top_k=top_k)

