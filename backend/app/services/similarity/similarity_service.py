from app.services.chembl_service import ChemblService
from app.services.rdkit_service import RDKitFingerprint
from app.services.similarity.faiss_store import FAISSStore


class SimilarityService:

    def __init__(self, chembl_service: ChemblService):
        self.chembl = chembl_service
        self.fp = RDKitFingerprint()
        self.store = FAISSStore()

    # ----------------------------------------
    # Build index (batch load molecules)
    # ----------------------------------------
    def build_index(self, chembl_ids: list[str]):
        for cid in chembl_ids:
            data = self.chembl.get_molecule_fingerprint(cid)
            if data:
                self.store.add(cid, data["fingerprint"])

        print(f"✅ FAISS index built with {len(chembl_ids)} molecules")

    # ----------------------------------------
    # Query similarity
    # ----------------------------------------
    def find_similar(self, chembl_idstr, k: int = 5):
        data = self.chembl.get_molecule_fingerprint(chembl_id)

        if not data:
            return []

        return self.store.search(data["fingerprint"], k=k)
