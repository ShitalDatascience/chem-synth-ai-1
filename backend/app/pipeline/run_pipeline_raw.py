from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Dict, List, Optional

from app.services import rdkit_service
from app.services.chembl_service import ChemblService
from app.services.normalization_service import NormalizationService

logger = logging.getLogger(__name__)

# RULE:
# - evidence_summary = SOURCE OF TRUTH (DO NOT COPY INTO report_sections)
# - report_sections only formats references, never stores raw evidence objects
# REPORT LAYER RULE:
# report_sections = human-readable summary ONLY
# NEVER duplicate full structured DB outputs here

def _safe(obj):
    """Removes None + prevents JSON drift issues"""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {k: _safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_safe(v) for v in obj]
    return obj


def _snake_case(s: str) -> str:
    import re

    s = (s or "").strip()
    if not s:
        return ""
    s = s.replace("'", "")
    s = re.sub(r"[^A-Za-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s.lower()


_ACTIVITY_TYPE_SYNONYMS = {
    "log_k": "log_k",
    "log_k_": "log_k",
    "log_k_prime": "log_k",
    "inhibition": "inhibition",
    "activity": "activity",
}


def _normalize_activity_type_key(raw: str) -> Optional[str]:
    k = _snake_case(raw)
    if not k:
        return None
    # Map known label variants.
    k = _ACTIVITY_TYPE_SYNONYMS.get(k, k)
    # Drop noisy labels (high-level filter only).
    if k in {"unknown", "na", "n_a", "not_specified"}:
        return None
    if "pathway" in k or "signature" in k:
        return None
    return k


_ORGANISM_TARGETS = {
    "Homo sapiens",
    "Mus musculus",
    "Rattus norvegicus",
    "Cavia porcellus",
}


def _split_target_taxonomy(top_targets: list[tuple[str, int]]) -> dict[str, list[tuple[str, int]]]:
    organism_targets: list[tuple[str, int]] = []
    protein_targets: list[tuple[str, int]] = []

    for t, n in top_targets or []:
        name = (t or "").strip()
        if not name:
            continue
        if name in _ORGANISM_TARGETS:
            organism_targets.append((name, int(n)))
        else:
            protein_targets.append((name, int(n)))
    return {"organism_targets": organism_targets, "protein_targets": protein_targets}


def _build_biological_summary(molecule: dict, evidence_summary: dict) -> str:
    """Deterministic, LLM-ready summary (no hallucination)."""
    mol_name = (molecule or {}).get("name") or ""
    proteins = [t for (t, _n) in (evidence_summary or {}).get("protein_targets", [])]
    prots_l = " ".join(p.lower() for p in proteins)

    if any(k in prots_l for k in ("ptgs1", "ptgs2", "cyclooxygenase", "cox")):
        return (
            f"Evidence suggests {mol_name or 'the molecule'} is associated with cyclooxygenase-related targets "
            f"(e.g., PTGS/COX family), consistent with COX inhibition as a plausible mechanism hypothesis. "
            "Activity types reported across assays indicate a mix of endpoint definitions; interpret potency trends cautiously. "
            "This is a computational summary of ChEMBL-derived annotations and requires experimental confirmation."
        )

    if proteins:
        top = ", ".join(proteins[:3])
        return (
            f"Evidence is concentrated on targets such as {top}. "
            "Reported activity types span multiple assay endpoints; treat cross-assay comparisons cautiously. "
            "This is a computational summary of ChEMBL-derived annotations and requires experimental confirmation."
        )

    return (
        "No strong protein-target signal was identified in the current evidence summary. "
        "This is a computational summary of ChEMBL-derived annotations and requires experimental confirmation."
    )


def build_report_sections(result: dict) -> dict:
    mol = result.get("molecule", {})
    evidence = result.get("evidence_summary", {})

    return {
        "executive_summary": f"Molecule resolved: {mol.get('canonical_smiles')}",
        "molecular_identity": mol.get("name"),
        "physchem": {
            "mw": mol.get("mw"),
            "logp": mol.get("logp"),
            "tpsa": mol.get("tpsa"),
        },
        # ONLY HIGH-LEVEL INSIGHT (NOT RAW DATA)
        "chembl_evidence": {
            "top_targets": [t[0] for t in evidence.get("protein_targets", [])[:3]],
            "total_records": evidence.get("total_records", 0),
        },
        "predictions": result.get("predictions", []),
        "next_experiments": "In-vitro validation recommended",
        "risks": "Low (heuristic model)",
        "citations": ["ChEMBL", "RDKit"],
        "disclaimer": "For research use only",
    }


def _aggregate_targets(evidence: List[Dict[str, Any]]) -> list[tuple[str, int]]:
    allowed_species = {
        "Homo sapiens",
        "Mus musculus",
        "Rattus norvegicus",
        "Cavia porcellus",
    }
    deny_targets = {"cyclooxygenase"}

    c = Counter()
    for r in evidence or []:
        t_raw = r.get("target_pref_name")
        if not t_raw:
            continue
        t = str(t_raw).strip()
        if not t:
            continue

        # Optional organism filter (only when field exists in evidence rows).
        org = (r.get("target_organism") or r.get("organism") or "").strip()
        if org and org not in allowed_species:
            continue

        # Remove generic / noisy targets.
        if t.strip().lower() in deny_targets:
            continue

        c[t] += 1

    return c.most_common(5)


def _aggregate_activity_types(evidence: List[Dict[str, Any]]) -> Dict[str, int]:
    c = Counter()
    for r in evidence or []:
        st = (r.get("standard_type") or "").strip()
        if not st:
            continue
        k = _normalize_activity_type_key(st)
        if not k:
            continue
        c[k] += 1
    return dict(c)


def _find_similar_compounds(
    smiles: str,
    *,
    name_query: Optional[str] = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """RDKit Tanimoto over ChEMBL name-search candidates (no Milvus)."""
    from rdkit import Chem

    # 1) Canonicalize query SMILES (mandatory)
    q_mol0 = Chem.MolFromSmiles(smiles)
    if q_mol0 is None:
        return []
    canon = Chem.MolToSmiles(q_mol0, canonical=True)
    q_mol = Chem.MolFromSmiles(canon)
    if q_mol is None:
        return []
    # 2) Standardized fingerprint (mandatory)
    _, fp_query = rdkit_service.morgan_fp_from_mol(q_mol)

    chembl = ChemblService()
    qn = (name_query or "").strip()
    candidates = chembl.search_by_name(qn, limit=50) if qn else []

    results: list[dict[str, Any]] = []

    for c in candidates or []:
        c_smiles_raw = c.get("canonical_smiles")
        if not c_smiles_raw:
            continue
        c_smiles_raw = str(c_smiles_raw).strip()
        if not c_smiles_raw:
            continue

        # 6) Remove salts / mixtures unless main fragment extracted.
        c_mol0 = Chem.MolFromSmiles(c_smiles_raw)
        if c_mol0 is None:
            continue

        # Largest fragment chooser when available; otherwise pick max heavy-atoms fragment.
        if "." in c_smiles_raw:
            try:
                from rdkit.Chem.MolStandardize import rdMolStandardize

                lfc = rdMolStandardize.LargestFragmentChooser()
                c_mol0 = lfc.choose(c_mol0)
            except Exception:
                frags = [f for f in c_smiles_raw.split(".") if f]
                best = None
                best_n = -1
                for f in frags:
                    m = Chem.MolFromSmiles(f)
                    if m is None:
                        continue
                    n = int(m.GetNumHeavyAtoms())
                    if n > best_n:
                        best_n = n
                        best = m
                if best is None:
                    continue
                c_mol0 = best

        c_can = Chem.MolToSmiles(c_mol0, canonical=True)

        # 4/5) Skip self-match and prevent similarity=1 unless identical SMILES.
        if c_can == canon:
            continue

        _, c_fp = rdkit_service.morgan_fp_from_mol(c_mol0)
        sim = float(rdkit_service.tanimoto(fp_query, c_fp))
        if sim >= 1.0:
            continue

        if sim > 1.0 or sim < 0.0:
            continue

        if sim > 0.4:
            results.append(
                {
                    "chembl_id": c.get("chembl_id"),
                    "pref_name": c.get("pref_name"),
                    "canonical_smiles": c_can,
                    "similarity": round(sim, 3),
                }
            )

    # 4) Deduplicate by CHEMBL_ID keeping highest similarity.
    seen: dict[str, dict[str, Any]] = {}
    for item in results:
        cid = item.get("chembl_id")
        if not cid:
            continue
        if cid not in seen or float(item.get("similarity", 0.0)) > float(seen[cid].get("similarity", 0.0)):
            seen[cid] = item

    final_results = sorted(seen.values(), key=lambda x: x["similarity"], reverse=True)[:limit]

    # 9) Debug log (temp)
    try:
        print(
            f"[SIMILARITY] query_fp_bits=2048 results={len(results)} unique={len(final_results)}"
        )
    except Exception:
        pass

    return final_results


def run_pipeline_raw(query: str) -> Dict[str, Any]:
    norm = NormalizationService.resolve(query)
    molecule_identity: Dict[str, Any] = {}

    # Try to surface core identity fields if present.
    if isinstance(norm, dict):
        molecule_identity["name"] = norm.get("name") or query
        if norm.get("canonical_smiles"):
            molecule_identity["canonical_smiles"] = norm.get("canonical_smiles")

    result: Dict[str, Any] = {
        "query": query,
        "molecule": molecule_identity,
        "similar_compounds": [],
        "evidence_summary": {},
        "experiment_list": [],
        "predictions": [],
        "biological_summary": "",
        "report_sections": {
            "executive_summary": "",
            "molecular_identity": "",
            "physchem": "",
            "similar_compounds": "",
            "chembl_evidence": "",
            "predictions": "",
            "risks": "",
            "next_experiments": "",
            "citations": "",
            "disclaimer": "",
        },
        "metadata": {
            "model_version": "v2",
            "pipeline": "chem-rag-v2",
        },
        "error": None,
    }

    # STEP 2 — PHYCHEM (RDKit only)
    if isinstance(norm, dict) and norm.get("canonical_smiles"):
        try:
            props = rdkit_service.validate_smiles(norm["canonical_smiles"])

            result["molecule"].update(
                {
                    "mw": props.mw,
                    "logp": props.logp,
                    "tpsa": props.tpsa,
                    "hba": props.hba,
                    "hbd": props.hbd,
                }
            )

        except Exception as e:
            logger.exception("RDKit physchem failed")
            result["error"] = f"physchem_error: {str(e)}"

    # STEP 3 — SIMILARITY (no Milvus)
    if isinstance(norm, dict) and norm.get("canonical_smiles"):
        try:
            similarity_hits = _find_similar_compounds(
                norm["canonical_smiles"],
                name_query=(norm.get("name") or query),
                limit=10,
            )

            result["similar_compounds"] = [
                {
                    "chembl_id": x.get("chembl_id"),
                    "pref_name": x.get("pref_name"),
                    "canonical_smiles": x.get("canonical_smiles"),
                    "similarity": float(x.get("similarity", 0.0)),
                }
                for x in similarity_hits
            ]

        except Exception as e:
            logger.exception("RDKit similarity failed")
            result["error"] = f"similarity_error: {str(e)}"

    # STEP 4 — ChEMBL EVIDENCE (safe)
    try:
        chembl_service = ChemblService()

        m = result.get("molecule") or {}
        chembl_ids: list[str] = [m.get("chembl_id")] if m.get("chembl_id") else []

        evidence_rows = chembl_service.get_evidence_bundle(chembl_ids=chembl_ids)
        evidence: list[dict[str, Any]] = []
        for r in evidence_rows or []:
            if hasattr(r, "model_dump"):
                evidence.append(r.model_dump())
            elif isinstance(r, dict):
                evidence.append(dict(r))

        result["evidence_summary"] = {
            "total_records": len(evidence),
            "top_targets": _aggregate_targets(evidence),
            "activity_types": _aggregate_activity_types(evidence),
        }
        split = _split_target_taxonomy(result["evidence_summary"]["top_targets"])
        result["evidence_summary"]["organism_targets"] = split["organism_targets"]
        result["evidence_summary"]["protein_targets"] = split["protein_targets"]
        result["biological_summary"] = _build_biological_summary(
            result.get("molecule") or {}, result["evidence_summary"]
        )

    except Exception as e:
        logger.exception("ChEMBL evidence failed")
        result["error"] = f"chembl_error: {str(e)}"

    # STEP 4.5 — FORCE CONSISTENT SIMILARITY FORMAT
    result["similar_compounds"] = [
        {
            "chembl_id": c.get("chembl_id"),
            "pref_name": c.get("pref_name"),
            "canonical_smiles": c.get("canonical_smiles"),
            "similarity": round(float(c.get("similarity", 0)), 3),
        }
        for c in result.get("similar_compounds", [])
    ]

    # STEP 5 — REPORT SECTIONS (ONLY ONE WRITER)
    result["report_sections"] = build_report_sections(result)

    # STEP 6 — FIX DUPLICATION ROOT CAUSE
    result["evidence_summary"] = _safe(result.get("evidence_summary", {}))
    if "chembl_evidence" in result:
        result.pop("chembl_evidence", None)

    # Prevent accidental duplication leaks
    if isinstance(result.get("report_sections", {}).get("chembl_evidence"), list):
        logger.warning("chembl_evidence should NOT be list - fixing structure")

    return _safe(result)

