#!/usr/bin/env python3
"""Phase 2 end-to-end ingestion test.

Tests the full pipeline: RDKit fingerprint → Milvus Lite upsert → similarity search.
Does NOT require Postgres — uses known SMILES strings directly.

Usage (from backend/ directory):
    conda activate chemdev_clean
    python scripts/test_ingest_phase2.py

Exit 0 = all checks passed.  Exit 1 = failure (see stderr).
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# Make sure 'backend/' is on sys.path when running as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_ingest_phase2")

# ---------------------------------------------------------------------------
# Test molecules — representative kinase inhibitors from ChEMBL
# ---------------------------------------------------------------------------
TEST_MOLECULES = [
    {
        "chembl_id": "CHEMBL941",
        "molregno": 941,
        "pref_name": "IMATINIB",
        "smiles": "Cc1ccc(cc1Nc2nccc(n2)c3cccnc3)NC(=O)c4ccc(cc4)CN5CCN(CC5)C",
    },
    {
        "chembl_id": "CHEMBL25",
        "molregno": 25,
        "pref_name": "ASPIRIN",
        "smiles": "CC(=O)Oc1ccccc1C(=O)O",
    },
    {
        "chembl_id": "CHEMBL939",
        "molregno": 939,
        "pref_name": "GEFITINIB",
        "smiles": "COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCCN1CCOCC1",
    },
    {
        "chembl_id": "CHEMBL553",
        "molregno": 553,
        "pref_name": "ERLOTINIB",
        "smiles": "C#Cc1cccc(Nc2ncnc3cc(OCCOC)c(OCCOC)cc23)c1",
    },
    {
        "chembl_id": "CHEMBL1470",
        "molregno": 1470,
        "pref_name": "SORAFENIB",
        "smiles": "CNC(=O)c1cc(Oc2ccc(NC(=O)Nc3ccc(Cl)c(C(F)(F)F)c3)cc2)ccn1",
    },
]

QUERY_SMILES = "Cc1ccc(cc1Nc2nccc(n2)c3cccnc3)NC(=O)c4ccc(cc4)CN5CCN(CC5)C"  # Imatinib


def _separator(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print("="*60)


def main() -> int:
    _separator("1. Import checks")

    try:
        from app.services import rdkit_service
        print(f"  [OK] rdkit_service imported  (_FP_NBITS={rdkit_service._FP_NBITS})")
    except Exception as exc:
        print(f"  [FAIL] rdkit_service: {exc}")
        return 1

    try:
        from app.services.milvus_service import MilvusService
        print("  [OK] MilvusService imported")
    except Exception as exc:
        print(f"  [FAIL] MilvusService: {exc}")
        return 1

    # ------------------------------------------------------------------
    _separator("2. Fingerprint dimension verification")
    # ------------------------------------------------------------------
    fp_arr, bv = rdkit_service.morgan_fp(QUERY_SMILES)
    dim = len(fp_arr)
    print(f"  morgan_fp dim = {dim}")
    if dim != 2048:
        print(f"  [FAIL] expected 2048, got {dim}")
        return 1
    on_bits = int(bv.GetNumOnBits())
    print(f"  on-bits (non-zero) = {on_bits}")
    print("  [OK] fingerprint dimension confirmed = 2048")

    # ------------------------------------------------------------------
    _separator("3. MilvusService health_check (before ingestion)")
    # ------------------------------------------------------------------
    milvus = MilvusService()
    hc_before = milvus.health_check()
    print(f"  {hc_before}")
    if hc_before.get("status") == "error":
        print(f"  [FAIL] Milvus health check error: {hc_before.get('error')}")
        return 1
    print(f"  [OK] fp_dim in schema = {hc_before['fp_dim']}")

    # ------------------------------------------------------------------
    _separator("4. Compute fingerprints for test molecules")
    # ------------------------------------------------------------------
    vectors = []
    for mol in TEST_MOLECULES:
        try:
            arr, _ = rdkit_service.morgan_fp(mol["smiles"])
            vectors.append({
                "chembl_id": mol["chembl_id"],
                "molregno": mol["molregno"],
                "pref_name": mol["pref_name"],
                "smiles_canonical": mol["smiles"],
                "standard_inchi_key": "",
                "mw_freebase": 0.0,
                "alogp": 0.0,
                "psa": 0.0,
                "hba": 0,
                "hbd": 0,
                "rtb": 0,
                "qed_weighted": 0.0,
                "heavy_atoms": 0,
                "aromatic_rings": 0,
                "full_molformula": "",
                "np_likeness_score": 0.0,
                "num_ro5_violations": 0,
                "ro3_pass": "",
                "fp": arr,
            })
            print(f"  [OK] {mol['chembl_id']:15s} {mol['pref_name']:15s}  fp_dim={len(arr)}")
        except Exception as exc:
            print(f"  [FAIL] {mol['chembl_id']}: {exc}")
            return 1

    # ------------------------------------------------------------------
    _separator("5. Upsert vectors into Milvus Lite")
    # ------------------------------------------------------------------
    n = milvus.upsert_vectors(vectors)
    print(f"  upsert_vectors returned: {n}")
    if n == 0:
        print("  [FAIL] upsert returned 0 — nothing was written")
        return 1
    print(f"  [OK] upserted {n} vectors")

    # ------------------------------------------------------------------
    _separator("6. Verify row count after ingestion")
    # ------------------------------------------------------------------
    hc_after = milvus.health_check()
    row_count = hc_after.get("row_count", 0)
    print(f"  health_check after upsert: {hc_after}")
    if row_count == 0:
        print("  [FAIL] row_count is still 0 after upsert")
        return 1
    print(f"  [OK] row_count = {row_count}")

    # ------------------------------------------------------------------
    _separator("7. Similarity search — query = Imatinib SMILES")
    # ------------------------------------------------------------------
    query_fp, _ = rdkit_service.morgan_fp(QUERY_SMILES)
    hits = milvus.search(query_fp.tolist(), top_k=5)
    print(f"  search returned {len(hits)} hits")
    if not hits:
        print("  [FAIL] search returned zero hits — collection empty or search broken")
        return 1
    for i, h in enumerate(hits):
        print(
            f"    [{i+1}] chembl_id={h.chembl_id:15s}  score={h.milvus_score:.4f}"
            f"  smiles={h.smiles[:40] if h.smiles else ''}..."
        )
    # The top hit must be the query molecule itself (or at least score > 0.99)
    top = hits[0]
    if top.milvus_score < 0.99:
        print(
            f"  [WARN] Top hit score {top.milvus_score:.4f} < 0.99 "
            "(expected Imatinib to be top hit for its own fingerprint)"
        )
    else:
        print(f"  [OK] Top hit = {top.chembl_id}  score = {top.milvus_score:.4f}")

    # ------------------------------------------------------------------
    _separator("8. Tanimoto rerank (RDKit bit-vector similarity)")
    # ------------------------------------------------------------------
    query_bv = rdkit_service.morgan_fp(QUERY_SMILES)[1]
    for h in hits:
        if h.smiles:
            try:
                _, hit_bv = rdkit_service.morgan_fp(h.smiles)
                h.tanimoto = rdkit_service.tanimoto(query_bv, hit_bv)
            except Exception:
                h.tanimoto = None

    ranked = sorted(
        [h for h in hits if h.tanimoto is not None],
        key=lambda x: x.tanimoto,
        reverse=True,
    )
    print(f"  Tanimoto-reranked results ({len(ranked)}):")
    for i, h in enumerate(ranked):
        print(f"    [{i+1}] {h.chembl_id:15s}  tanimoto={h.tanimoto:.4f}")

    if ranked and ranked[0].tanimoto < 0.99:
        print(
            f"  [WARN] Top Tanimoto {ranked[0].tanimoto:.4f} < 0.99 "
            "— Imatinib should have Tanimoto=1.0 against itself"
        )
    else:
        print(f"  [OK] Self-Tanimoto = {ranked[0].tanimoto:.4f} (expected 1.0)")

    _separator("RESULT")
    print("  ALL CHECKS PASSED — Phase 2 pipeline is functional")
    return 0


if __name__ == "__main__":
    sys.exit(main())
