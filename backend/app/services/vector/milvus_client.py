"""Thin shim — delegates to app.services.milvus_service which uses MilvusClient.

The old ORM-based connect_milvus() / create_collection() API required a
running Milvus server and caused import-time crashes (pymilvus reads the
MILVUS_URI env var in orm.connections and rejects file paths as invalid URIs).

All callers should use MilvusService from app.services.milvus_service instead.
This file is kept for backward compatibility and re-exports MilvusService.
"""
from app.services.milvus_service import MilvusService  # noqa: F401

__all__ = ["MilvusService"]
