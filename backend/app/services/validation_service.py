"""Molecule input validation — runs BEFORE any RAG orchestration.

Responsibilities
----------------
* Classify the input as a molecule name, SMILES string, or ChEMBL ID.
* Try an exact lookup in ChEMBL; on failure run lightweight fuzzy matching.
* Validate SMILES structurally via RDKit.
* Return a :class:`ValidationResult` that the orchestrator uses to gate the
  pipeline: if ``valid=False`` the pipeline STOPS and the error is returned to
  the caller without touching LangChain / Milvus / DeepChem / LoRA.
"""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public schemas (also importable from here for use in routes / frontend types)
# ---------------------------------------------------------------------------

class ValidationSuggestion(BaseModel):
    """A candidate correction the caller can offer the user."""
    chembl_id: str
    pref_name: Optional[str] = None
    canonical_smiles: Optional[str] = None
    similarity_score: float = Field(ge=0.0, le=1.0, description="String similarity to the original query")


class ValidationResult(BaseModel):
    valid: bool
    query: str
    resolved_query: Optional[str] = None        # canonical name / SMILES to pass downstream
    chembl_id: Optional[str] = None             # resolved ChEMBL ID when valid
    input_type: str = "unknown"                  # "name" | "smiles" | "chembl_id"
    error_code: Optional[str] = None            # "invalid_molecule" | "invalid_smiles" | "no_evidence"
    error_message: Optional[str] = None
    suggestions: List[ValidationSuggestion] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Input-type detection
# ---------------------------------------------------------------------------

_CHEMBL_ID_RE = re.compile(r"^CHEMBL\d+$", re.IGNORECASE)
# Strong SMILES indicators — bond/branch/ring chars that essentially never
# appear in molecule names, target symbols, or assay codes.
_SMILES_STRONG_CHARS = set("[]=#@\\")
# Aromatic atoms (lowercase). Their presence in a token strongly suggests SMILES.
_SMILES_AROMATIC_CHARS = set("bcnops")
# Gene-symbol shape: 2–5 caps optionally followed by a digit run (JAK2, BRD4,
# COX1, AZD9291, EGFR…). NOT a SMILES.
_GENE_SYMBOL_RE = re.compile(r"^[A-Z][A-Z]+\d{0,4}([-/][A-Z0-9]+)?$")


def _looks_like_smiles(text: str) -> bool:
    """Conservative SMILES detector — only true for tokens that almost
    certainly are chemical structure notation.

    Rejects:
    * gene/target symbols (JAK2, BRD4, EGFR, AZD9291, COX-2)
    * single words / proper nouns (Aspirin, Warfarin)
    * assay shorthands (IC50, pKi, Kd)
    * anything with whitespace or quoting
    """
    s = (text or "").strip()
    if len(s) < 4 or " " in s or "\t" in s:
        return False
    # Gene/target symbols look like "JAK2", "AZD9291", "COX-1" — never SMILES.
    if _GENE_SYMBOL_RE.match(s):
        return False
    # Must contain a strong SMILES char OR an aromatic atom letter.
    has_strong = bool(_SMILES_STRONG_CHARS.intersection(s))
    has_aromatic = any(c in _SMILES_AROMATIC_CHARS for c in s)
    if not (has_strong or has_aromatic):
        return False
    # Must contain a SMILES atom letter (B, C, N, O, P, S, F, Cl, Br, I or aromatic)
    has_atom = bool(set("BCNOPSFI").intersection(s)) or has_aromatic
    if not has_atom:
        return False
    # Letter-density guard — real SMILES are dense in non-letter chars.
    letters = sum(1 for c in s if c.isalpha())
    if letters / max(len(s), 1) > 0.85 and not has_strong:
        return False
    return True


def _looks_like_chembl_id(text: str) -> bool:
    return bool(_CHEMBL_ID_RE.match(text.strip()))


def _detect_input_type(query: str) -> str:
    q = query.strip()
    if _looks_like_chembl_id(q):
        return "chembl_id"
    if _looks_like_smiles(q):
        return "smiles"
    return "name"


# ---------------------------------------------------------------------------
# Fuzzy name matching helpers
# ---------------------------------------------------------------------------

def _name_similarity(a: str, b: str) -> float:
    """Normalised string similarity in [0, 1]."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _build_suggestions(
    query: str,
    candidates: List[dict],
    top_n: int = 3,
    min_score: float = 0.45,
) -> List[ValidationSuggestion]:
    scored: list[tuple[float, dict]] = []
    for row in candidates:
        name = (row.get("pref_name") or row.get("chembl_id") or "").strip()
        score = _name_similarity(query, name) if name else 0.0
        if score >= min_score:
            scored.append((score, row))

    scored.sort(key=lambda x: x[0], reverse=True)
    out: list[ValidationSuggestion] = []
    for score, row in scored[:top_n]:
        cid = row.get("chembl_id")
        if not cid:
            continue
        out.append(
            ValidationSuggestion(
                chembl_id=str(cid),
                pref_name=row.get("pref_name"),
                canonical_smiles=row.get("canonical_smiles"),
                similarity_score=round(score, 3),
            )
        )
    return out


# ---------------------------------------------------------------------------
# Main validator
# ---------------------------------------------------------------------------

class MoleculeValidator:
    """Stateless validator; call :meth:`validate` with a raw user query."""

    def validate(self, query: str) -> ValidationResult:
        q = (query or "").strip()
        if not q:
            return ValidationResult(
                valid=False,
                query=query,
                error_code="invalid_molecule",
                error_message="Query is empty.",
            )

        input_type = _detect_input_type(q)
        logger.info("[VALIDATION] query=%r input_type=%s", q, input_type)

        if input_type == "smiles":
            return self._validate_smiles(q)
        if input_type == "chembl_id":
            return self._validate_chembl_id(q)
        return self._validate_name(q)

    # ------------------------------------------------------------------
    # SMILES path
    # ------------------------------------------------------------------
    def _validate_smiles(self, smiles: str) -> ValidationResult:
        try:
            from app.services.rdkit_service import validate_smiles as rdkit_validate
            rdkit_validate(smiles)
            logger.info("[VALIDATION] SMILES valid: %r", smiles)
            return ValidationResult(
                valid=True,
                query=smiles,
                resolved_query=smiles,
                input_type="smiles",
            )
        except Exception as exc:
            logger.info("[VALIDATION] invalid SMILES %r: %s", smiles, exc)
            return ValidationResult(
                valid=False,
                query=smiles,
                input_type="smiles",
                error_code="invalid_smiles",
                error_message=(
                    f"The input looks like a SMILES string but could not be parsed: {exc}. "
                    "Please check the structure notation."
                ),
            )

    # ------------------------------------------------------------------
    # ChEMBL ID path
    # ------------------------------------------------------------------
    def _validate_chembl_id(self, chembl_id: str) -> ValidationResult:
        cid = chembl_id.strip().upper()
        try:
            from app.services.chembl_service import ChemblService

            svc = ChemblService()
            row = svc.get_by_chembl_id(cid)
        except Exception as exc:
            logger.exception("[VALIDATION] ChEMBL lookup error for %r: %s", cid, exc)
            # Don't block the pipeline on a DB error — let it proceed
            return ValidationResult(
                valid=True,
                query=chembl_id,
                resolved_query=cid,
                chembl_id=cid,
                input_type="chembl_id",
            )

        if row:
            pref = row.get("pref_name") or cid
            logger.info("[VALIDATION] ChEMBL ID resolved: %s → %s", cid, pref)
            return ValidationResult(
                valid=True,
                query=chembl_id,
                resolved_query=pref,
                chembl_id=cid,
                input_type="chembl_id",
            )

        logger.info("[VALIDATION] ChEMBL ID not found: %s", cid)
        return ValidationResult(
            valid=False,
            query=chembl_id,
            input_type="chembl_id",
            error_code="invalid_molecule",
            error_message=f"{cid} was not found in ChEMBL. Please check the identifier.",
        )

    # ------------------------------------------------------------------
    # Name path (fuzzy)
    # ------------------------------------------------------------------
    def _validate_name(self, name: str) -> ValidationResult:
        try:
            from app.services.chembl_service import ChemblService

            svc = ChemblService()
            rows = svc.search_by_name(name, limit=10)
        except Exception as exc:
            logger.exception("[VALIDATION] name search error for %r: %s", name, exc)
            # DB error → pass through, let the pipeline handle it
            return ValidationResult(
                valid=True,
                query=name,
                resolved_query=name,
                input_type="name",
            )

        if rows:
            top = rows[0]
            cid = top.get("chembl_id")
            pref = top.get("pref_name") or name
            logger.info("[VALIDATION] name resolved: %r → %s (%s)", name, pref, cid)
            return ValidationResult(
                valid=True,
                query=name,
                resolved_query=pref,
                chembl_id=cid,
                input_type="name",
            )

        # No exact/partial match → fuzzy correction attempt
        logger.info("[VALIDATION] no DB match for %r — running fuzzy correction", name)
        suggestions = self._fuzzy_suggestions(name)

        if suggestions:
            top_score = suggestions[0].similarity_score
            top_name = suggestions[0].pref_name or suggestions[0].chembl_id
            msg = (
                f'"{name}" did not match any molecule in ChEMBL. '
                f'Did you mean "{top_name}" ({suggestions[0].chembl_id})?'
            )
        else:
            msg = (
                f'"{name}" did not match any molecule in ChEMBL and no similar '
                "compounds were found. Please check the spelling."
            )

        return ValidationResult(
            valid=False,
            query=name,
            input_type="name",
            error_code="invalid_molecule",
            error_message=msg,
            suggestions=suggestions,
        )

    def _fuzzy_suggestions(self, name: str) -> list[ValidationSuggestion]:
        """Search ChEMBL with progressively shorter prefixes to generate candidates."""
        try:
            from app.services.chembl_service import ChemblService

            svc = ChemblService()
            candidates: list[dict] = []
            # Try the full name, then the first 5 chars prefix
            for probe in [name, name[:5]] if len(name) > 5 else [name]:
                rows = svc.search_by_name(probe, limit=20)
                for r in rows:
                    if r.get("chembl_id") not in {c.get("chembl_id") for c in candidates}:
                        candidates.append(r)

            return _build_suggestions(name, candidates)
        except Exception as exc:
            logger.warning("[VALIDATION] fuzzy suggestion error: %s", exc)
            return []


# Convenience singleton
_validator = MoleculeValidator()


def validate_molecule_query(query: str) -> ValidationResult:
    """Module-level entry point — used by :class:`QueryEngine`."""
    return _validator.validate(query)
