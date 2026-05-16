from typing import List
from app.services.chembl_service import ChemblService
from app.services.rdkit_service import RDKitFingerprint
from app.services.similarity.milvus_store import MilvusStore


class MilvusIngestionService:
    """
    Phase 2.2: Full ChEMBL ingestion pipeline
    """

    def __init__(self, chembl_service: ChemblService):
        self.chembl = chembl_service
        self.fp = RDKitFingerprint()
        self.store = MilvusStore()

    def fetch_molecules(self, limit: int = 1000) -> List[dict]:
        """
        Fetch molecules with SMILES from DB
        """
        query = """
            SELECT md.chembl_id, cs.canonical_smiles
            FROM molecule_dictionary md
            JOIN compound_structures cs
                ON md.molregno = cs.molregno
            LIMIT %s
        """

        with self.chembl.conn.cursor() as cur:
            cur.execute(query, (limit,))
            return cur.fetchall()

    def ingest(self, limit: int = 1000):
        """
        Main ingestion pipeline
        """
        molecules = self.fetch_molecules(limit)

        count = 0

        for mol in molecules:
            chembl_id = mol["chembl_id"]
            smiles = mol["canonical_smiles"]

            if not smiles:
                continue

            fp_vector = self.fp.generate(smiles)

            if fp_vector is None:
                continue

            self.store.add(chembl_id, fp_vector)
            count += 1

        print(f"✅ Ingestion complete: {count} molecules indexed")
        return count
