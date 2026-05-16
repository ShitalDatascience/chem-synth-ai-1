import faiss
import numpy as np


class FAISSStore:
    """
    Stores molecular fingerprints and performs similarity search.
    Phase 2 core vector engine.
    """

    def __init__(self, dim: int = 2048):
        self.dim = dim
        self.index = faiss.IndexFlatL2(dim)
        self.ids = []

    def add(self, chembl_id: str, vector: list):
        vec = np.array(vector, dtype=np.float32).reshape(1, -1)
        self.index.add(vec)
        self.ids.append(chembl_id)

    def search(self, vector: list, k: int = 5):
        vec = np.array(vector, dtype=np.float32).reshape(1, -1)
        distances, indices = self.index.search(vec, k)

        results = []
        for i, idx in enumerate(indices[0]):
            if idx < len(self.ids):
                results.append({
                    "chembl_id": self.ids[idx],
                    "distance": float(distances[0][i])
                })

        return results
