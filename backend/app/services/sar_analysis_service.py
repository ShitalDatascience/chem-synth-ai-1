"""SAR-style aggregation over a list of ligand activity rows.

Inputs are the rows returned by ``ChemblService.fetch_compounds_by_target``,
which include ``canonical_smiles`` and pre-computed physchem descriptors
from ``public.compound_properties`` (alogp, psa, hba, hbd, mw_freebase, …).

Outputs:
* :func:`compute_scaffold_clusters`  — Murcko scaffold groupings (RDKit)
* :func:`compute_physchem_trends`    — count / mean / median for each descriptor
"""

from __future__ import annotations

import logging
import statistics
from collections import defaultdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Scaffold clustering
# ---------------------------------------------------------------------------

def _murcko_scaffold(smiles: str) -> Optional[str]:
    """Return the canonical SMILES of the Bemis-Murcko scaffold or None."""
    try:
        from rdkit import Chem
        from rdkit.Chem.Scaffolds import MurckoScaffold

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        scaf = MurckoScaffold.GetScaffoldForMol(mol)
        if scaf is None or scaf.GetNumAtoms() == 0:
            return None
        return Chem.MolToSmiles(scaf, canonical=True)
    except Exception as exc:
        logger.debug("[SAR] Murcko failure for %r: %s", smiles, exc)
        return None


def compute_scaffold_clusters(
    rows: List[Dict[str, Any]],
    *,
    top_n: int = 8,
    min_members: int = 2,
) -> List[Dict[str, Any]]:
    """Group activity rows by Murcko scaffold.

    Each cluster contains:
    * ``scaffold``   — canonical scaffold SMILES (``""`` for acyclic / no-ring molecules)
    * ``size``       — number of distinct compounds in the cluster
    * ``examples``   — up to 5 representative ChEMBL IDs
    * ``median_pchembl`` — potency aggregate across cluster members
    * ``median_alogp``  — lipophilicity aggregate
    """
    grouped: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"chembl_ids": set(), "pchembl": [], "alogp": []}
    )

    for r in rows:
        smi = r.get("canonical_smiles")
        if not smi:
            continue
        scaf = _murcko_scaffold(smi) or ""
        bucket = grouped[scaf]
        cid = r.get("chembl_id")
        if cid:
            bucket["chembl_ids"].add(str(cid))
        if r.get("pchembl_value") is not None:
            try:
                bucket["pchembl"].append(float(r["pchembl_value"]))
            except (TypeError, ValueError):
                pass
        if r.get("alogp") is not None:
            try:
                bucket["alogp"].append(float(r["alogp"]))
            except (TypeError, ValueError):
                pass

    clusters: List[Dict[str, Any]] = []
    for scaf, b in grouped.items():
        size = len(b["chembl_ids"])
        if size < min_members:
            continue
        examples = sorted(b["chembl_ids"])[:5]
        clusters.append({
            "scaffold": scaf,
            "size": size,
            "examples": examples,
            "median_pchembl": round(statistics.median(b["pchembl"]), 2) if b["pchembl"] else None,
            "median_alogp": round(statistics.median(b["alogp"]), 2) if b["alogp"] else None,
        })

    clusters.sort(key=lambda c: c["size"], reverse=True)
    return clusters[:top_n]


# ---------------------------------------------------------------------------
# Physicochemical trend aggregation
# ---------------------------------------------------------------------------

_DESCRIPTOR_FIELDS = (
    ("mw_freebase", "Molecular weight",     "g/mol"),
    ("alogp",       "AlogP (lipophilicity)", ""),
    ("psa",         "Polar surface area",   "Å²"),
    ("hba",         "H-bond acceptors",     ""),
    ("hbd",         "H-bond donors",        ""),
    ("aromatic_rings", "Aromatic rings",    ""),
    ("qed_weighted", "QED (drug-likeness)", ""),
)


def _safe_floats(values: List[Any]) -> List[float]:
    out: List[float] = []
    for v in values:
        if v is None:
            continue
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            continue
    return out


def compute_physchem_trends(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Aggregate ChEMBL physchem descriptors across the ligand set.

    Returns a list of ``{descriptor, label, unit, n, mean, median, min, max}``
    rows — one per descriptor that has at least 1 numeric value.
    """
    # Deduplicate by chembl_id so the same molecule isn't counted twice
    # (the activity table can have many rows per compound).
    unique_by_id: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        cid = r.get("chembl_id")
        if cid and cid not in unique_by_id:
            unique_by_id[cid] = r

    unique_rows = list(unique_by_id.values())

    out: List[Dict[str, Any]] = []
    for field, label, unit in _DESCRIPTOR_FIELDS:
        vals = _safe_floats([r.get(field) for r in unique_rows])
        if not vals:
            continue
        out.append({
            "descriptor": field,
            "label": label,
            "unit": unit,
            "n": len(vals),
            "mean": round(statistics.mean(vals), 3),
            "median": round(statistics.median(vals), 3),
            "min": round(min(vals), 3),
            "max": round(max(vals), 3),
        })
    return out
