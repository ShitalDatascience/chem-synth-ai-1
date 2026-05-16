import pytest

pytest.importorskip("rdkit.Chem")

from app.agents.chem_langchain_agent import run_chem_agent


def test_phase4_pipeline():
    print("\n🚀 Running Phase 4 End-to-End Validation (FinalReport contract)...\n")

    query = "CCO predict activity"

    result = run_chem_agent(query)

    assert isinstance(result, dict)
    assert set(result.keys()) >= {
        "query",
        "molecule",
        "similar_compounds",
        "evidence_summary",
        "experiment_list",
        "predictions",
        "report_sections",
        "metadata",
    }
    assert result["metadata"] == {"model_version": "v2", "pipeline": "chem-rag-v2"}

    print("✔ FinalReport schema keys OK")

    mol = result.get("molecule") or {}
    assert mol.get("mw") is not None
    mw_val = float(mol["mw"])
    assert 40.0 < mw_val < 55.0

    logp_val = mol.get("logp") if mol.get("logp") is not None else mol.get("alogp")
    assert logp_val is not None
    assert -1.5 < float(logp_val) < 0.5

    print("✔ PhysChem OK")

    assert isinstance(result["predictions"], list)
    assert isinstance(result["similar_compounds"], list)
    assert isinstance(result["experiment_list"], list)
    assert isinstance(result["evidence_summary"], dict)
    assert isinstance(result["report_sections"], dict)

    if result["similar_compounds"]:
        assert result["similar_compounds"][0].get("tanimoto", 0) >= 0.2

    print("✔ Similarity OK")

    ev = result["evidence_summary"]
    if mol.get("chembl_id"):
        assert int(ev.get("total_activities", 0) or 0) > 0
        assert isinstance(ev.get("target_clusters", []), list)

    print("✔ Evidence / clusters OK")

    rs = result["report_sections"]
    exec_s = str(rs.get("executive_summary", "") or "")
    assert len(exec_s) > 10

    print("✔ Report sections OK")

    print("\n🎯 Phase 4 FULLY VALIDATED ✔\n")


if __name__ == "__main__":
    test_phase4_pipeline()
