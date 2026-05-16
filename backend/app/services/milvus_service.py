from __future__ import annotations

"""Milvus Lite service — collection management, upsert, and similarity search.

Uses the MilvusClient high-level API (embedded Milvus Lite, no server, no Docker).

IMPORTANT: we deliberately do NOT import pymilvus.orm.connections / utility /
Collection / CollectionSchema / FieldSchema.  Those ORM modules initialize at
import time by reading the env-var MILVUS_URI and raise ConnectionConfigException
when that value is a local file path instead of an HTTP URL.  MilvusClient is
the correct API for Milvus Lite and does not trigger that code path.
"""
import logging
import os
from typing import Any, Optional

import numpy as np

from app.config import get_settings
from app.services import rdkit_service

logger = logging.getLogger(__name__)

try:
    from pymilvus import MilvusClient, DataType
    _MILVUS_AVAILABLE = True
except ImportError:
    _MILVUS_AVAILABLE = False
    logger.warning("pymilvus not installed — milvus_service will raise at call time")


def _require_milvus() -> None:
    if not _MILVUS_AVAILABLE:
        raise RuntimeError(
            "pymilvus is not installed. Run: pip install pymilvus"
        )


_settings = get_settings()
COLLECTION_NAME = _settings.milvus_collection
_FP_DIM = rdkit_service.FP_NBITS


class SimilarityHit:
    def __init__(
        self,
        chembl_id: str,
        milvus_score: float,
        smiles: Optional[str] = None,
        inchi_key: Optional[str] = None,
        tanimoto: Optional[float] = None,
    ) -> None:
        self.chembl_id = chembl_id
        self.milvus_score = milvus_score
        self.smiles = smiles
        self.inchi_key = inchi_key
        self.tanimoto = tanimoto


class MilvusService:

    def __init__(self) -> None:
        _require_milvus()
        self._db_path: str = get_settings().milvus_db_path
        self._client: Optional["MilvusClient"] = None

    def _get_client(self) -> "MilvusClient":
        if self._client is None:
            if not self._db_path.startswith("http"):
                parent = os.path.dirname(os.path.abspath(self._db_path))
                os.makedirs(parent, exist_ok=True)
            self._client = MilvusClient(uri=self._db_path)
            logger.info("Milvus client opened: %s", self._db_path)
        return self._client

    # ------------------------------------------------------------------
    # COLLECTION
    # ------------------------------------------------------------------

    def ensure_collection(self) -> None:
        _require_milvus()
        client = self._get_client()

        if client.has_collection(COLLECTION_NAME):
            return

        schema = client.create_schema(auto_id=False, enable_dynamic_field=False)

        schema.add_field("chembl_id", DataType.VARCHAR, max_length=64, is_primary=True)
        schema.add_field("molregno", DataType.INT64)
        schema.add_field("standard_inchi_key", DataType.VARCHAR, max_length=64)
        schema.add_field("smiles_canonical", DataType.VARCHAR, max_length=1024)
        schema.add_field("pref_name", DataType.VARCHAR, max_length=256)
        schema.add_field("mw_freebase", DataType.FLOAT)
        schema.add_field("alogp", DataType.FLOAT)
        schema.add_field("psa", DataType.FLOAT)
        schema.add_field("hba", DataType.INT32)
        schema.add_field("hbd", DataType.INT32)
        schema.add_field("rtb", DataType.INT32)
        schema.add_field("fp", DataType.FLOAT_VECTOR, dim=_FP_DIM)

        index_params = client.prepare_index_params()
        index_params.add_index(
            field_name="fp",
            index_type="FLAT",
            metric_type="COSINE",
        )

        client.create_collection(
            collection_name=COLLECTION_NAME,
            schema=schema,
            index_params=index_params,
        )

        logger.info("Created Milvus collection: %s", COLLECTION_NAME)

    def drop_collection(self) -> bool:
        _require_milvus()
        client = self._get_client()

        if not client.has_collection(COLLECTION_NAME):
            return False

        client.drop_collection(collection_name=COLLECTION_NAME)
        logger.warning("Dropped collection: %s", COLLECTION_NAME)
        return True

    # ------------------------------------------------------------------
    # INSERT
    # ------------------------------------------------------------------

    def upsert_vectors(self, batch: list[dict[str, Any]]) -> int:
        _require_milvus()
        self.ensure_collection()
        client = self._get_client()

        cleaned = []

        for row in batch:
            fp = row.get("fp")
            if fp is None:
                continue

            if isinstance(fp, np.ndarray):
                fp = fp.astype(np.float32).ravel().tolist()

            fp = [float(x) for x in fp]

            if len(fp) != _FP_DIM:
                continue

            cleaned.append({
                "chembl_id": str(row.get("chembl_id", "")),
                "molregno": int(row.get("molregno") or 0),
                "standard_inchi_key": row.get("standard_inchi_key") or "",
                "smiles_canonical": row.get("smiles_canonical") or "",
                "pref_name": row.get("pref_name") or "",
                "mw_freebase": float(row.get("mw_freebase") or 0),
                "alogp": float(row.get("alogp") or 0),
                "psa": float(row.get("psa") or 0),
                "hba": int(row.get("hba") or 0),
                "hbd": int(row.get("hbd") or 0),
                "rtb": int(row.get("rtb") or 0),
                "fp": fp,
            })

        if not cleaned:
            return 0

        res = client.upsert(collection_name=COLLECTION_NAME, data=cleaned)
        return res.get("upsert_count", len(cleaned))

    # ------------------------------------------------------------------
    # SEARCH
    # ------------------------------------------------------------------

    def _coerce_fp_vector(self, fp_vector: Any) -> list[float]:
        arr = np.asarray(fp_vector, dtype=np.float32).ravel()

        if arr.size != _FP_DIM:
            raise ValueError(f"Expected {_FP_DIM}, got {arr.size}")

        return arr.tolist()

    def search(self, fp_vector: Any, top_k: int = 200) -> list[SimilarityHit]:
        _require_milvus()
        self.ensure_collection()
        client = self._get_client()

        fp_vector = self._coerce_fp_vector(fp_vector)

        results = client.search(
            collection_name=COLLECTION_NAME,
            data=[fp_vector],
            limit=top_k,
            output_fields=["chembl_id", "smiles_canonical", "standard_inchi_key"],
            search_params={"metric_type": "COSINE"},
        )

        raw = results[0] if results else []
        logger.info("Milvus hits: %s", len(raw))

        hits = []
        for hit in raw:
            entity = hit.get("entity", {})
            hits.append(
                SimilarityHit(
                    chembl_id=entity.get("chembl_id", ""),
                    milvus_score=float(hit.get("distance", 0.0)),
                    smiles=entity.get("smiles_canonical"),
                    inchi_key=entity.get("standard_inchi_key"),
                )
            )

        return hits

    def search_with_rdkit_rerank(
        self,
        query_smiles: str,
        *,
        top_k_coarse: int = 200,
    ) -> list[SimilarityHit]:

        if not query_smiles:
            return []

        # ✅ FIX 1 — canonicalize query
        canon_query = rdkit_service.canonicalize_smiles(query_smiles)

        fp_arr, query_bv = rdkit_service.morgan_fp(canon_query)
        fp_list = self._coerce_fp_vector(fp_arr)

        coarse = self.search(fp_list, top_k=top_k_coarse)

        reranked = []

        for h in coarse:
            smi = h.smiles
            if not smi:
                continue

            try:
                # ✅ FIX 2 — canonicalize candidate
                canon_cand = rdkit_service.canonicalize_smiles(smi)
                _, cand_bv = rdkit_service.morgan_fp(canon_cand)

                h.tanimoto = float(
                    rdkit_service.tanimoto(query_bv, cand_bv)
                )
                reranked.append(h)

            except Exception:
                continue

        reranked.sort(key=lambda x: x.tanimoto or 0.0, reverse=True)
        reranked = reranked[:10]  # hard limit top 10

        logger.info("Top Tanimoto: %s", reranked[0].tanimoto if reranked else None)

        return reranked

    # ------------------------------------------------------------------
    # HEALTH
    # ------------------------------------------------------------------

    def get_collection_stats(self) -> dict:
        client = self._get_client()

        if not client.has_collection(COLLECTION_NAME):
            return {"exists": False, "count": 0}

        stats = client.get_collection_stats(COLLECTION_NAME)

        return {
            "exists": True,
            "count": int(stats.get("row_count", 0)),
        }
