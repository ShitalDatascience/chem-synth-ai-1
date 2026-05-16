from functools import lru_cache
import hashlib
import json

class SimpleCache:
    """
    Lightweight in-memory cache for RAG pipeline
    """

    @staticmethod
    def make_key(data: dict) -> str:
        encoded = json.dumps(data, sort_keys=True).encode()
        return hashlib.md5(encoded).hexdigest()

    @staticmethod
    @lru_cache(maxsize=256)
    def get_cached_result(key: str):
        return None  # placeholder for future DB/redis upgrade
