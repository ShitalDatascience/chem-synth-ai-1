class MilvusStore:
    """
    Phase 2.1: Placeholder Milvus interface
    (No installation required yet)
    """

    def __init__(self):
        self.vectors = []

    def add(self, chembl_id: str, vector: list):
        self.vectors.append({
            "chembl_id": chembl_id,
            "vector": vector
        })

    def search(self, vector: list, k: int = 5):
        # TEMP fallback until Milvus is enabled
        import numpy as np

        def cosine(a, b):
            a = np.array(a)
            b = np.array(b)
            return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

        results = []
        for item in self.vectors:
            sim = cosine(vector, item["vector"])
            results.append({
                "chembl_id": item["chembl_id"],
                "score": float(sim)
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:k]
