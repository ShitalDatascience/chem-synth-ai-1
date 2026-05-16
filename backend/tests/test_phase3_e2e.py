from app.services import rdkit_service
from app.services.chembl.activity_cleaner import ActivityCleaner
from app.services.vector.chembl_milvus_activity import (
    ensure_collection,
    ingest_to_milvus,
    search_similar,
)

from app.services.deepchem.deepchem_predictor import DeepChemPredictor


# -----------------------------
# STEP 1: DeepChem standalone test
# -----------------------------
def test_deepchem_predictor():
    smiles = "CCO"

    result = DeepChemPredictor.predict(smiles)

    assert "smiles" in result
    assert "predicted_activity" in result
    assert isinstance(result["predicted_activity"], float)

    print("✔ DeepChem predictor OK")
    print(result)


# -----------------------------
# STEP 2: Full pipeline test (Phase 2 + Phase 3)
# -----------------------------
def test_full_pipeline():
    sample_row = {
        "activity_id": 1,
        "target_chembl_id": "CHEMBL123",
        "standard_type": "IC50",
        "standard_value": 10,
        "standard_units": "nM",
        "pchembl_value": None,
        "smiles": "CCO",
        "is_valid": True,
    }

    # -------------------------
    # CLEANING (Phase 2)
    # -------------------------
    cleaned = ActivityCleaner.clean_row(sample_row)

    assert cleaned["target_chembl_id"] == "CHEMBL123"

    # -------------------------
    # INGESTION (Phase 2)
    # -------------------------
    ensure_collection()
    ingest_to_milvus([sample_row])

    # -------------------------
    # SEARCH (Phase 2)
    # -------------------------
    arr, _ = rdkit_service.morgan_fp("CCO")
    fp = [int(round(float(x))) for x in arr.tolist()]
    results = search_similar(fp, top_k=3)

    assert len(results) > 0

    # -------------------------
    # DEEPCHEM INTEGRATION (Phase 3)
    # -------------------------
    dc_result = DeepChemPredictor.predict("CCO")

    assert "predicted_activity" in dc_result

    # Attach Phase 3 output to result (simulated integration check)
    results[0]["deepchem_score"] = dc_result["predicted_activity"]

    print("✔ Full pipeline (Phase 2 + Phase 3) OK")
    print("Top result:", results[0])


# -----------------------------
# RUN ALL TESTS
# -----------------------------
if __name__ == "__main__":
    print("\n🚀 Running Phase 3 End-to-End Validation...\n")

    test_deepchem_predictor()
    test_full_pipeline()

    print("\n🎯 Phase 3 FULLY VALIDATED ✔")

