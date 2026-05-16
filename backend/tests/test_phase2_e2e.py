from rdkit import Chem

from app.services import rdkit_service
from app.services.chembl.activity_cleaner import ActivityCleaner
from app.services.vector.chembl_milvus_activity import (
    ensure_collection,
    ingest_to_milvus,
    search_similar,
    verify_milvus_ready
)

# -------------------------
# STEP 1: Sanity check RDKit
# -------------------------
def test_rdkit():
    smiles = "CCO"
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None, "Invalid SMILES"

    arr, _ = rdkit_service.morgan_fp(smiles)
    fp_list = [int(round(float(x))) for x in arr.tolist()]
    assert len(fp_list) == rdkit_service.FP_NBITS, "Fingerprint dimension mismatch"
    assert sum(fp_list) > 0, "Empty fingerprint"

    print("✔ RDKit fingerprint OK")


# -------------------------
# STEP 2: Cleaner validation
# -------------------------
def test_cleaner():
    sample = {
        "activity_id": 1,
        "target_chembl_id": "CHEMBL123",
        "standard_type": "IC50",
        "standard_value": 10,
        "standard_units": "nM",
        "pchembl_value": None,
        "smiles": "CCO"
    }

    cleaned = ActivityCleaner.clean_row(sample)

    assert cleaned["is_valid"] is True
    assert cleaned["value_nm"] == 10.0
    assert cleaned["target_chembl_id"] == "CHEMBL123"

    print("✔ Cleaner OK")


# -------------------------
# STEP 3: Milvus Lite readiness
# -------------------------
def test_milvus_ready():
    ok = verify_milvus_ready()
    assert ok is True, "Milvus Lite not ready"
    print("✔ Milvus Lite ready")


# -------------------------
# STEP 4: Ingestion test
# -------------------------
def test_ingestion():
    sample_rows = [
        {
            "activity_id": 1,
            "target_chembl_id": "CHEMBL123",
            "standard_type": "IC50",
            "standard_value": 10,
            "standard_units": "nM",
            "pchembl_value": None,
            "smiles": "CCO",
            "is_valid": True
        }
    ]

    ensure_collection()
    ingest_to_milvus(sample_rows)

    print("✔ Ingestion OK")


# -------------------------
# STEP 5: Similarity search test
# -------------------------
def test_search():
    smiles = "CCO"
    arr, _ = rdkit_service.morgan_fp(smiles)
    query_vector = [int(round(float(x))) for x in arr.tolist()]

    results = search_similar(query_vector, top_k=3)

    assert results is not None
    assert len(results) > 0

    print("✔ Similarity search OK")
    print("Top hit:", results[0])


# -------------------------
# RUN ALL TESTS
# -------------------------
if __name__ == "__main__":
    print("\n🚀 Running Phase 2 End-to-End Validation...\n")

    test_rdkit()
    test_cleaner()
    test_milvus_ready()
    test_ingestion()
    test_search()

    print("\n🎯 Phase 2 FULLY VALIDATED ✔")