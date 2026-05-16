from __future__ import annotations

import os
from functools import lru_cache


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default) or default


class Settings:
    # Postgres / ChEMBL
    db_name: str = _env("DB_NAME", "chembl_db")
    db_user: str = _env("DB_USER", "shitalkale")
    db_password: str = _env("DB_PASSWORD", "")
    db_host: str = _env("DB_HOST", "localhost")
    db_port: int = int(_env("DB_PORT", "5432"))
    pg_statement_timeout_ms: int = int(_env("PG_STATEMENT_TIMEOUT_MS", "30000"))

    # Milvus Lite (embedded local, no server, no Docker).
    # Variable is named MILVUS_DB_PATH (not MILVUS_URI) to avoid pymilvus
    # reading it at import time and rejecting a file path as an invalid URI.
    milvus_db_path: str = _env("MILVUS_DB_PATH", "./data/milvus_lite.db")
    # After changing fingerprint normalization, either run build_milvus_index --rebuild
    # or bump MILVUS_COLLECTION (e.g. chembl_morgan_2048_v2) so old embeddings are not mixed.
    milvus_collection: str = _env("MILVUS_COLLECTION", "chembl_morgan_2048")
    milvus_top_k_candidates: int = int(_env("MILVUS_TOP_K", "200"))
    milvus_min_tanimoto: float = float(_env("MILVUS_MIN_TANIMOTO", "0.2"))
    milvus_final_top_k: int = int(_env("MILVUS_FINAL_TOP_K", "100"))

    # ChemLLM / Ollama
    ollama_base_url: str = _env("OLLAMA_BASE_URL", "http://localhost:11434")
    chemllm_model: str = _env("CHEMLLM_MODEL", "chemllm:latest")
    chemllm_temperature: float = float(_env("CHEMLLM_TEMPERATURE", "0.2"))

    # DeepChem
    deepchem_cache_dir: str = _env("DEEPCHEM_CACHE_DIR", "./data/deepchem_cache")

    # Evidence cache
    evidence_cache_ttl_s: int = int(_env("EVIDENCE_CACHE_TTL_S", "3600"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
