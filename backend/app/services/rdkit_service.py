from __future__ import annotations

"""RDKit service: canonicalization, fingerprints, similarity, depiction.

**SINGLE SOURCE OF TRUTH** for Morgan fingerprints (radius=2, fpSize=2048) and
RDKit Tanimoto. All Milvus ingestion, similarity search, ChEMBL helpers, and
agents must delegate here — Morgan bits come only from
``rdFingerprintGenerator.GetMorganGenerator`` in this module.

Milestone 2 — all chemistry is gated by try/import so the server starts even if
rdkit is not yet installed (returns a clear RuntimeError at call time).
"""

import io
import logging
import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from pydantic import BaseModel

logger = logging.getLogger(__name__)

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, Descriptors, Draw, rdMolDescriptors
    from rdkit.Chem.rdchem import Mol
    from rdkit.DataStructs import ExplicitBitVect
    from rdkit.DataStructs import TanimotoSimilarity as _tanimoto_fn

    _RDKIT_AVAILABLE = True
except ImportError:
    _RDKIT_AVAILABLE = False
    logger.warning("rdkit not installed — rdkit_service will raise at call time")


def _require_rdkit() -> None:
    if not _RDKIT_AVAILABLE:
        raise RuntimeError(
            "rdkit is not installed. Use the project chemistry conda env, e.g. "
            "`conda activate chemdev_clean`, then verify with "
            "`python -c \"from rdkit import Chem; Chem.MolFromSmiles('CCO')\"`. "
            "Alternatively: uv add rdkit-pypi (or rdkit)."
        )


# ---------------------------------------------------------------------------
# Return types
# ---------------------------------------------------------------------------

class ValidatedMolecule(BaseModel):
    smiles_input: str
    canonical_smiles: str
    inchi: Optional[str] = None
    inchi_key: Optional[str] = None
    mw: Optional[float] = None
    logp: Optional[float] = None
    hba: Optional[int] = None
    hbd: Optional[int] = None
    tpsa: Optional[float] = None
    rotatable_bonds: Optional[int] = None
    heavy_atom_count: Optional[int] = None


class MorganFPResult(BaseModel):
    canonical_smiles: str
    fp_float_list: list[float]   # length 2048, values {0.0, 1.0}
    fp_bits_hex: str             # hex-encoded bit string for compact storage


# ---------------------------------------------------------------------------
# Core functions — Morgan kernel (GetMorganGenerator only)
# ---------------------------------------------------------------------------

FP_RADIUS = 2
FP_NBITS = 2048
_FP_RADIUS = FP_RADIUS
_FP_NBITS = FP_NBITS

_morgan_gen = None


def _get_morgan_generator() -> Any:
    """Lazy singleton: ``GetMorganGenerator(radius=2, fpSize=2048)`` (Plan.md)."""
    global _morgan_gen
    _require_rdkit()
    if _morgan_gen is None:
        from rdkit.Chem.rdFingerprintGenerator import GetMorganGenerator

        _morgan_gen = GetMorganGenerator(radius=FP_RADIUS, fpSize=FP_NBITS)
        logger.info("Morgan FP active: radius=2, nBits=2048 (SINGLE SOURCE)")
    return _morgan_gen


def canonicalize_smiles(smiles: str) -> str:
    """Canonical SMILES only: ``MolFromSmiles`` → ``MolToSmiles(..., canonical=True)``.

    No tautomer enumeration, no MolStandardize pipeline, no salt stripping (per project draft).
    """
    _require_rdkit()
    raw = (smiles or "").strip()
    if not raw:
        raise ValueError("Empty SMILES")
    mol = Chem.MolFromSmiles(raw)
    if mol is None:
        raise ValueError(f"Invalid SMILES: {smiles!r}")
    out = Chem.MolToSmiles(mol, canonical=True)
    if not out:
        raise ValueError(f"Canonicalization produced empty SMILES from input {smiles!r}")
    return out


def normalize_for_fingerprint(smiles: str) -> str:
    """Backward-compatible alias for :func:`canonicalize_smiles` (fingerprint string alignment)."""
    return canonicalize_smiles(smiles)


def validate_smiles(smiles: str) -> ValidatedMolecule:
    """Parse and validate; physchem matches the **fingerprint-normalized** parent structure."""
    _require_rdkit()
    canonical = normalize_for_fingerprint(smiles)
    mol: Optional[Mol] = Chem.MolFromSmiles(canonical)
    if mol is None:
        raise ValueError(f"Invalid normalized SMILES: {canonical!r}")

    inchi = Chem.MolToInchi(mol)
    inchi_key = Chem.InchiToInchiKey(inchi) if inchi else None

    return ValidatedMolecule(
        smiles_input=smiles,
        canonical_smiles=canonical,
        inchi=inchi,
        inchi_key=inchi_key,
        mw=round(Descriptors.MolWt(mol), 4),
        logp=round(Descriptors.MolLogP(mol), 4),
        hba=rdMolDescriptors.CalcNumHBA(mol),
        hbd=rdMolDescriptors.CalcNumHBD(mol),
        tpsa=round(Descriptors.TPSA(mol), 4),
        rotatable_bonds=rdMolDescriptors.CalcNumRotatableBonds(mol),
        heavy_atom_count=mol.GetNumHeavyAtoms(),
    )


def canonicalize(smiles: str) -> str:
    """Same as :func:`canonicalize_smiles`."""
    return canonicalize_smiles(smiles)


def morgan_fp_from_mol(mol: Mol) -> Tuple[np.ndarray, Any]:
    """
    SINGLE SOURCE OF TRUTH: Morgan fingerprint = radius=2, fpSize=2048 via ``GetMorganGenerator``.
    """
    _require_rdkit()
    gen = _get_morgan_generator()
    fp = gen.GetFingerprint(mol)
    lst = fp.ToList()
    if len(lst) != FP_NBITS:
        raise ValueError(f"Expected fingerprint length {FP_NBITS}, got {len(lst)}")
    arr = np.asarray(lst, dtype=np.float32)
    assert arr.shape == (FP_NBITS,) and len(arr) == FP_NBITS
    return arr, fp


def morgan_fp(smiles: str) -> Tuple[np.ndarray, Any]:
    """
    Morgan fingerprint: **radius = FP_RADIUS**, **fpSize = FP_NBITS**, after :func:`canonicalize_smiles`.

    Returns:
        fp_array: np.ndarray shape (2048,) float32 in ``{0.0, 1.0}`` for Milvus.
        fp: RDKit fingerprint vector (``ExplicitBitVect``-compatible) for :func:`compute_tanimoto`.
    """
    _require_rdkit()
    canon = canonicalize_smiles(smiles)
    mol = Chem.MolFromSmiles(canon)
    if mol is None:
        raise ValueError(f"Invalid SMILES after canonicalize: {canon!r}")
    arr, fp = morgan_fp_from_mol(mol)
    assert arr.shape == (FP_NBITS,) and len(arr) == FP_NBITS
    return arr, fp


def generate_fingerprint(smiles: str) -> Optional[list[int]]:
    """Morgan bit vector as ``list[int]`` of 0/1 (length FP_NBITS); invalid SMILES → ``None``."""
    try:
        arr, _ = morgan_fp(smiles)
        return [int(round(float(x))) for x in arr.tolist()]
    except Exception:
        return None


class RDKitFingerprint:
    """Legacy class API; all methods delegate to :func:`morgan_fp` / normalization."""

    def __init__(self, radius: int = FP_RADIUS, n_bits: int = FP_NBITS) -> None:
        if radius != FP_RADIUS or n_bits != FP_NBITS:
            raise ValueError(
                f"Only Morgan(radius={FP_RADIUS}, nBits={FP_NBITS}) is supported; got radius={radius}, n_bits={n_bits}"
            )

    @staticmethod
    def smiles_to_mol(smiles: str) -> Any:
        if not smiles:
            return None
        try:
            norm = canonicalize_smiles(smiles)
            return Chem.MolFromSmiles(norm)
        except Exception:
            return None

    def mol_to_fingerprint(self, mol: Any) -> Optional[np.ndarray]:
        if mol is None:
            return None
        try:
            arr, _ = morgan_fp_from_mol(mol)
            return arr
        except Exception:
            return None

    def generate(self, smiles: str) -> Optional[list[int]]:
        return generate_fingerprint(smiles)


def _logp_from_predictions(predictions: List[Dict[str, Any]]) -> Optional[float]:
    for p in predictions or []:
        if not isinstance(p, dict):
            continue
        task = (p.get("task") or "").lower().replace(" ", "_")
        if any(k in task for k in ("logp", "log_p", "partition", "lipophil")):
            v = p.get("value")
            if isinstance(v, (int, float)) and not math.isnan(float(v)):
                return float(v)
    return None


def apply_response_physchem(
    mol: Dict[str, Any],
    smiles: str,
    predictions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Populate ``mw_freebase`` and a **single** ``alogp`` for JSON/report (priority: RDKit > ChEMBL > ML).

    Molecular weight always uses ``Descriptors.MolWt`` on the resolved RDKit mol when parsing succeeds.
    """
    _require_rdkit()
    out = dict(mol)
    raw = (smiles or "").strip()
    chembl_lp = out.get("alogp")
    ml_lp = _logp_from_predictions(predictions)

    rdkit_m: Optional[Mol] = None
    if raw:
        try:
            norm = canonicalize_smiles(raw)
            rdkit_m = Chem.MolFromSmiles(norm)
        except Exception:
            rdkit_m = None
        if rdkit_m is None:
            try:
                rdkit_m = Chem.MolFromSmiles(raw)
            except Exception:
                rdkit_m = None

    if rdkit_m is not None:
        mw_val = round(float(Descriptors.MolWt(rdkit_m)), 4)
        logp_val = round(float(Descriptors.MolLogP(rdkit_m)), 4)
        # Single physchem source when SMILES parses: RDKit only (never mix with ChEMBL in same row).
        out["mw"] = mw_val
        out["mw_freebase"] = mw_val
        out["logp"] = logp_val
        out["alogp"] = logp_val
        out["psa"] = round(float(Descriptors.TPSA(rdkit_m)), 4)
        out["hba"] = int(rdMolDescriptors.CalcNumHBA(rdkit_m))
        out["hbd"] = int(rdMolDescriptors.CalcNumHBD(rdkit_m))
        out["rtb"] = int(rdMolDescriptors.CalcNumRotatableBonds(rdkit_m))
        out["heavy_atoms"] = int(rdkit_m.GetNumHeavyAtoms())
        can = Chem.MolToSmiles(rdkit_m, canonical=True)
        if can and not (out.get("canonical_smiles") or "").strip():
            out["canonical_smiles"] = can
        return out

    chosen: Optional[float] = None
    if chembl_lp is not None:
        try:
            c = float(chembl_lp)
            if math.isfinite(c):
                chosen = round(c, 4)
        except (TypeError, ValueError):
            pass
    if chosen is None and ml_lp is not None:
        chosen = round(ml_lp, 4)
    out["alogp"] = chosen
    out["logp"] = chosen
    return out


def fp_parity_report(query_smiles: str, milvus_stored_smiles: str) -> dict[str, object]:
    """Debug: compare canonical forms / InChIKeys for query vs Milvus-stored SMILES."""
    _require_rdkit()
    qn = canonicalize_smiles(query_smiles)
    sn = canonicalize_smiles(milvus_stored_smiles) if milvus_stored_smiles else ""
    mq = Chem.MolFromSmiles(qn)
    ms = Chem.MolFromSmiles(sn) if sn else None
    ik_q = Chem.MolToInchiKey(mq) if mq else ""
    ik_s = Chem.MolToInchiKey(ms) if ms else ""
    return {
        "query_input": query_smiles,
        "query_normalized": qn,
        "milvus_stored_raw": milvus_stored_smiles,
        "milvus_stored_normalized": sn,
        "normalized_smiles_match": qn == sn,
        "inchikey_query": ik_q,
        "inchikey_stored": ik_s,
        "inchikey_match": bool(ik_q and ik_s and ik_q == ik_s),
    }


def tanimoto(a: "ExplicitBitVect", b: "ExplicitBitVect") -> float:
    """Compute RDKit Tanimoto similarity between two ExplicitBitVects."""
    _require_rdkit()
    return float(_tanimoto_fn(a, b))


def compute_tanimoto(fp1: Any, fp2: Any) -> float:
    """Tanimoto ONLY via RDKit: two ``ExplicitBitVect`` or two same-shaped float/bit ``np.ndarray``."""
    _require_rdkit()
    if isinstance(fp1, np.ndarray) and isinstance(fp2, np.ndarray):
        return float(tanimoto_from_arrays(fp1, fp2))
    return tanimoto(fp1, fp2)


def tanimoto_from_arrays(a: np.ndarray, b: np.ndarray) -> float:
    """Compute Tanimoto from float32 bit arrays (used when bitvects are unavailable)."""
    _require_rdkit()
    a_bool = a.astype(bool)
    b_bool = b.astype(bool)
    intersection = int((a_bool & b_bool).sum())
    union = int((a_bool | b_bool).sum())
    return intersection / union if union > 0 else 0.0


def bitvect_from_array(arr: np.ndarray) -> "ExplicitBitVect":
    """Reconstruct an ExplicitBitVect from a float32 array (for reranking stored vectors)."""
    _require_rdkit()
    bv = ExplicitBitVect(FP_NBITS)
    for i, v in enumerate(arr):
        if v > 0.5:
            bv.SetBit(i)
    return bv


def depict_2d_png(smiles: str, size: tuple[int, int] = (300, 300)) -> bytes:
    """Render a 2D depiction of the molecule as PNG bytes."""
    _require_rdkit()
    mol = Chem.MolFromSmiles(canonicalize_smiles(smiles))
    if mol is None:
        raise ValueError(f"Invalid SMILES: {smiles!r}")
    AllChem.Compute2DCoords(mol)
    img = Draw.MolToImage(mol, size=size)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def depict_2d_svg(smiles: str, size: tuple[int, int] = (300, 300)) -> str:
    """Render a 2D depiction of the molecule as SVG string."""
    _require_rdkit()
    from rdkit.Chem.Draw import rdMolDraw2D

    mol = Chem.MolFromSmiles(canonicalize_smiles(smiles))
    if mol is None:
        raise ValueError(f"Invalid SMILES: {smiles!r}")
    AllChem.Compute2DCoords(mol)
    drawer = rdMolDraw2D.MolDraw2DSVG(size[0], size[1])
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    return drawer.GetDrawingText()


def compute_morgan_fp_result(smiles: str) -> MorganFPResult:
    """High-level helper returning a serialisable MorganFPResult."""
    _require_rdkit()
    canonical = canonicalize_smiles(smiles)
    mol = Chem.MolFromSmiles(canonical)
    if mol is None:
        raise ValueError(f"Invalid normalized SMILES: {canonical!r}")
    arr, bitvect = morgan_fp_from_mol(mol)
    return MorganFPResult(
        canonical_smiles=canonical,
        fp_float_list=arr.tolist(),
        fp_bits_hex=bitvect.ToBitString(),
    )
