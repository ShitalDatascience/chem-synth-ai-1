"""Strict intent-classification gateway.

Runs AFTER ``safe_query_guard`` and BEFORE any ChEMBL / RDKit / Milvus /
DeepChem / LLM call.  Every chat request is funnelled through
:func:`route_query`; the chat handler dispatches purely on the returned
:class:`RouterDecision`.

Hard rules enforced here:

* RDKit and the SMILES regex are NEVER applied to a target-classified query.
* Assay shorthands (``IC50``, ``EC50``, ``Ki``, ``Kd``, ``pIC50``) are
  metadata only — never molecules, never SMILES candidates.
* Synonym + fuzzy ChEMBL resolver is ALWAYS tried before "molecule not
  recognised" is emitted.
* Top candidate is auto-selected when ``confidence >= 0.5`` — the chat
  surface MUST NOT show "needs confirmation" prompts.

Intent set:
    molecule_lookup           — SMILES / ChEMBL IDs / synonym-resolved drugs.
    target_lookup             — single-protein assays (gene symbols).
    toxicity_risk_analysis    — cardiac / hERG / off-target safety bundles.
    similarity_search / sar_analysis / prediction / general_bio_query — as before.

Domain-first rules (critical for hERG / off-target flows):
    * Safety + hERG/KCNH2 wording resolves to ``toxicity_risk_analysis`` **before**
      molecule synonym resolution tries to treat ``hERG`` as a drug name.
    * High-priority target keywords (:data:`TARGET_KEYWORDS`) classify as
      ``target_lookup`` **before** ChEMBL name resolution unless a structure
      token (CHEMBL id / SMILES) already won.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.services.query_parser_service import (
    ParsedQuery,
    _rdkit_validates,
    build_normalized_request,
    pick_primary_target,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INTENTS = (
    "molecule_lookup",
    "target_lookup",
    "toxicity_risk_analysis",
    "similarity_search",
    "sar_analysis",
    "prediction",
    "general_bio_query",
)

ENTITY_TYPES = (
    "smiles",
    "chembl_id",
    "molecule_name",
    "compound",
    "target_symbol",
    "protein_target",
    "target_assay",
    "none",
)

NEXT_ACTIONS = (
    "run_evidence_pipeline",                # molecule_lookup → ChEMBL evidence + report
    "fetch_compounds_by_target",            # target_lookup
    "fetch_compounds_by_target_with_sar",   # sar_analysis
    "chembl_safety_assay_query",            # toxicity_risk_analysis (binding / inhibition)
    "run_similarity_pipeline",              # similarity_search
    "validate_smiles_then_predict",         # prediction (DeepChem)
    "general_llm_response",                # general_bio_query
    "ask_for_clarification",               # confidence < threshold
)

# ── Routing map advertised to logs / tooling (SPEC FIX 3) ─────────────────────
TOOL_MAP: Dict[str, str] = {
    "molecule_lookup": "RDKit + ChEMBL_compound",
    "target_lookup": "ChEMBL_target_assay",
    "toxicity_risk_analysis": "ChEMBL_safety_assay",
    "sar_analysis": "ChEMBL + RAG + clustering",
    "prediction": "DeepChem / ML model",
    "general_bio_query": "LLM_RAG",
    "similarity_search": "RAG + ChEMBL",
}

TARGET_KEYWORDS: List[str] = [
    # Prefer longer synonyms first when scanning positional matches below.
    "KCNH2",
    "hERG",
    "HERG",
    "DRD2",
    "BRD4",
    "EGFR",
    "JAK2",
]

# hERG spelling variants (“hERG”, “HERG”), never bare “ERG” (too noisy vs other gene families).
_HERG_FAMILY_RE = re.compile(r"\b(?:kcnh2|h[-]?erg)\b", re.IGNORECASE)
_CHEMBL_ID_FRAGMENT_RE = re.compile(r"\bCHEMBL\d+\b", re.IGNORECASE)
_SMILES_STUB_RE = re.compile(r"\bcc\d*=", re.IGNORECASE)

# Assay shorthands — metadata only, never molecules.
ASSAY_TERMS = {"IC50", "EC50", "KI", "KD", "PIC50", "PEC50", "TM", "LD50"}

# Auto-resolution threshold (Step 4 of the spec).
DEFAULT_MIN_CONFIDENCE = 0.5

_CHEMBL_ID_RE = re.compile(r"^CHEMBL\d+$", re.IGNORECASE)
_SIMILARITY_RE = re.compile(
    r"\b(similar(?:\s+to)?|analog[s]?|analogue[s]?|nearest|closest|tanimoto)\b",
    re.IGNORECASE,
)
_SAR_RE = re.compile(
    r"\b(sar|structure[-\s]?activity|scaffold[s]?|cluster(?:ing|ed)?|"
    r"substitut(?:ion|e)s?|pka|pkb|trend[s]?|murcko|functional\s+group[s]?)\b",
    re.IGNORECASE,
)
_PREDICT_RE = re.compile(
    r"\b(predict|prediction|predicted|forecast|estimate|simulat\w*|"
    r"properties?\s+of)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Public schema
# ---------------------------------------------------------------------------

class RouterDecision(BaseModel):
    """Routing decision handed to the chat dispatcher.

    Mandatory fields (Step 10 — Output Standardization):
    * ``intent``                — one of :data:`INTENTS`
    * ``resolved_entity_type``  — one of :data:`ENTITY_TYPES`
    * ``next_action``           — one of :data:`NEXT_ACTIONS`
    * ``confidence``            — 0.0 – 1.0
    """

    intent: str
    resolved_entity_type: str
    next_action: str
    confidence: float = 0.0
    needs_clarification: bool = False

    primary_entity: Optional[str] = None
    chembl_id: Optional[str] = None
    canonical_smiles: Optional[str] = None
    reason: str = ""
    parsed: ParsedQuery
    candidates: List[Dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_chembl_id(token: str) -> bool:
    return bool(_CHEMBL_ID_RE.fullmatch((token or "").strip()))


def _is_assay_term(token: str) -> bool:
    return (token or "").upper() in ASSAY_TERMS


def _mentions_herg_or_kcnh2(query: str) -> bool:
    q = query or ""
    return bool(_HERG_FAMILY_RE.search(q)) or bool(re.search(r"\bkcnh2\b", q, re.IGNORECASE))


def _token_is_herg_channel_alias(tok: str) -> bool:
    """True when a parser token is HERG/KCNh2-ish (never a marketed drug spelling)."""
    if not tok or _is_chembl_id(tok) or _is_assay_term(tok) or _rdkit_validates(tok):
        return False
    compact = re.sub(r"[-\s]+", "", (tok or "").lower())
    return compact in {"herg", "kcnh2"}


def _looks_like_structure_or_chembl_id_token(query: str) -> bool:
    """Molecule branch guard — SPEC: only treat as compound when CHEMBL / SMILES stubs appear."""
    if not query:
        return False
    if _CHEMBL_ID_FRAGMENT_RE.search(query):
        return True
    if _SMILES_STUB_RE.search(query):
        return True
    return False


def classify_intent(query: str) -> Dict[str, Any]:
    """Light-weight deterministic classifier mirroring SPEC FIX 2 (logging / tests)."""
    q = (query or "").strip()
    out: Dict[str, Any] = {"intent": "general_bio_query", "entity_type": "none", "next_step": "LLM_RAG"}
    if not q:
        return out

    if _is_toxicity_risk_bundle(q):
        _, display = _resolve_herg_entity_labels(q)
        out.update(
            {
                "intent": "toxicity_risk_analysis",
                "entity_type": "target_assay",
                "resolved_entity": display,
                "next_step": "ChEMBL_safety_assay_query",
            },
        )
        return out

    hit = _first_priority_target_hit(q)
    if hit:
        search_tok = _canonical_target_search_token(hit)
        out.update(
            {
                "intent": "target_lookup",
                "entity_type": "protein_target",
                "resolved_entity": search_tok,
                "next_step": "ChEMBL_target_assay_query",
            },
        )
        return out

    if _looks_like_structure_or_chembl_id_token(q):
        out.update(
            {
                "intent": "molecule_lookup",
                "entity_type": "compound",
                "next_step": "rdkit_validation",
            },
        )
    return out


def _is_toxicity_risk_bundle(query: str) -> bool:
    """True for off-target / cardiac-risk language combined with hERG / KCNH2."""
    if not _mentions_herg_or_kcnh2(query):
        return False
    ql = (query or "").lower()
    if "off-target" in ql or "off target" in ql or "offtarget" in ql.replace(" ", ""):
        return True
    if re.search(
        r"\b(cardiotox|cardiotoxicity|pro[-\s]?arrhythm|qt\b|qt[-\s]?interval|"
        r"qt[-\s]?prolon|torsad|torsade|cardiac\s+risk|"
        r"risk\s+signals?|summarize\s+risk|toxicity\s+risk|safety\s+assays?)\b",
        ql,
    ):
        return True
    # “evidence / compounds … on hERG” style questions (SPEC sample query)
    if re.search(
        r"\b(compounds?|ligands?|evidence|activity|inhibition|blocker|blockers|"
        r"antagonist|antagonists|binders?|potency)\b",
        ql,
    ) and re.search(r"\b(?:on|against|for|at)\b", ql):
        return True
    return False


def _resolve_herg_entity_labels(_query: str) -> tuple[str, str]:
    """Return (ChEMBL search token, display label).

    Ion channel synonyms are consolidated to gene symbol ``KCNH2``.
    """
    return "KCNH2", "hERG (KCNH2)"


def _canonical_target_search_token(hit: str) -> str:
    """Map surface token → target_dictionary / component_synonyms search key."""
    t = (hit or "").strip()
    if not t:
        return t
    compact = re.sub(r"[-\s]+", "", t.lower())
    if compact in {"herg", "kcnh2"}:
        return "KCNH2"
    return t.upper()


def _first_priority_target_hit(query: str) -> Optional[str]:
    """First TARGET_KEYWORD match in reading order (longest keyword preferred at each position)."""
    if not query:
        return None
    ordered = sorted(TARGET_KEYWORDS, key=lambda t: (-len(t), t.lower()))
    best_pos: Optional[int] = None
    best_kw: Optional[str] = None
    for kw in ordered:
        pat = re.compile(r"(?<![A-Za-z0-9])" + re.escape(kw) + r"(?![A-Za-z0-9])", re.IGNORECASE)
        m = pat.search(query)
        if not m:
            continue
        pos = m.start()
        if best_pos is None or pos < best_pos or (pos == best_pos and len(kw) > len(best_kw or "")):
            best_pos = pos
            best_kw = kw
    return best_kw


def _decision_from_priority_target(
    raw_query: str,
    parsed: ParsedQuery,
    hit: str,
) -> RouterDecision:
    search = _canonical_target_search_token(hit)
    is_sar = parsed.intent == "sar_analysis" or bool(_SAR_RE.search(raw_query))
    intent = "sar_analysis" if is_sar else "target_lookup"
    etype = "protein_target"
    return RouterDecision(
        intent=intent,
        resolved_entity_type=etype,
        primary_entity=search,
        confidence=1.0,
        next_action=(
            "fetch_compounds_by_target_with_sar" if is_sar else "fetch_compounds_by_target"
        ),
        reason=(
            f"High-priority target keyword {hit!r} → ChEMBL search token {search!r} "
            f"({TOOL_MAP.get(intent, intent)})."
        ),
        parsed=parsed,
    )


def _toxicity_router_decision(raw_query: str, parsed: ParsedQuery) -> RouterDecision:
    search_tok, display = _resolve_herg_entity_labels(raw_query)
    return RouterDecision(
        intent="toxicity_risk_analysis",
        resolved_entity_type="target_assay",
        primary_entity=search_tok,
        confidence=1.0,
        next_action="chembl_safety_assay_query",
        reason=(
            f"{TOOL_MAP['toxicity_risk_analysis']}: cardiac / off-target wording with "
            f"{display}; experimental evidence from ChEMBL (predicted placeholders optional)."
        ),
        parsed=parsed,
    )


def _resolve_via_synonyms(name: str) -> List[Dict[str, Any]]:
    """ChEMBL synonym + fuzzy resolver — tried BEFORE any rejection."""
    try:
        from app.services.chembl_service import ChemblService
        return ChemblService().resolve_molecule_with_synonyms(name)
    except Exception as exc:
        logger.warning("[ROUTER] synonym resolver failed for %r: %s", name, exc)
        return []


def _general_bio_decision(
    parsed: ParsedQuery,
    *,
    primary_entity: Optional[str] = None,
    candidates: Optional[List[Dict[str, Any]]] = None,
    confidence: float = 0.0,
    reason: str = "",
) -> "RouterDecision":
    return RouterDecision(
        intent="general_bio_query",
        resolved_entity_type="none",
        next_action="ask_for_clarification" if confidence < DEFAULT_MIN_CONFIDENCE else "general_llm_response",
        confidence=confidence,
        needs_clarification=confidence < DEFAULT_MIN_CONFIDENCE,
        primary_entity=primary_entity,
        reason=reason or "Falling back to general biomedical query.",
        parsed=parsed,
        candidates=candidates or [],
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def route_query(raw_query: str, *, min_confidence: float = DEFAULT_MIN_CONFIDENCE) -> RouterDecision:
    """Classify ``raw_query`` and produce a :class:`RouterDecision`.

    Priority ladder:
      1. Explicit ChEMBL ID molecule token      → ``molecule_lookup``
      2. RDKit-validated SMILES                 → ``molecule_lookup`` / ``prediction``
      3. Off-target cardiac / hERG safety bundle→ ``toxicity_risk_analysis``
      4. Parsed gene-level targets               → ``target_lookup`` / ``sar_analysis``
      5. High-priority kinase/channel keywords    → ``target_lookup`` / ``sar_analysis``
      6. ChEMBL synonym drug resolution         → molecule / similarity / prediction
      7. Fallback                                → ``general_bio_query``
    """
    parsed = build_normalized_request(raw_query, verify=False)

    # ── Rule 1: explicit ChEMBL ID ──────────────────────────────────────────
    chembl_id_token = next(
        (m for m in parsed.molecules if _is_chembl_id(m)),
        None,
    )
    if chembl_id_token:
        cid = chembl_id_token.upper()
        return RouterDecision(
            intent="molecule_lookup",
            resolved_entity_type="chembl_id",
            primary_entity=cid,
            chembl_id=cid,
            confidence=1.0,
            next_action="run_evidence_pipeline",
            reason="ChEMBL ID detected — deterministic resolution.",
            parsed=parsed,
        )

    # ── Rule 2: RDKit-validated SMILES (deterministic) ─────────────────────
    # Only candidates that already passed the parser's strict heuristic
    # AND aren't assay shorthands reach RDKit.
    smiles_token = next(
        (
            m for m in parsed.molecules
            if not _is_chembl_id(m)
            and not _is_assay_term(m)
            and _rdkit_validates(m)
        ),
        None,
    )
    if smiles_token:
        is_prediction = bool(_PREDICT_RE.search(raw_query))
        return RouterDecision(
            intent="prediction" if is_prediction else "molecule_lookup",
            resolved_entity_type="smiles",
            primary_entity=smiles_token,
            canonical_smiles=smiles_token,
            confidence=1.0,
            next_action=(
                "validate_smiles_then_predict" if is_prediction
                else "run_evidence_pipeline"
            ),
            reason="Valid SMILES detected — bypassing molecule resolution.",
            parsed=parsed,
        )

    # ── Cardiac safety / off-target bundles (DOMAIN PRIORITY OVER MOLECULES) ──
    logger.debug("[ROUTER] classify_intent snapshot=%s", classify_intent(raw_query))
    if _is_toxicity_risk_bundle(raw_query):
        return _toxicity_router_decision(raw_query, parsed)

    # ── Rule 3: target gene symbol ─────────────────────────────────────────
    if parsed.targets and (
        parsed.query_type == "target_query"
        or parsed.intent in {"target_lookup", "sar_analysis"}
    ):
        primary = pick_primary_target(parsed.targets)
        is_sar = parsed.intent == "sar_analysis" or bool(_SAR_RE.search(raw_query))
        intent = "sar_analysis" if is_sar else "target_lookup"
        return RouterDecision(
            intent=intent,
            resolved_entity_type="target_symbol",
            primary_entity=primary,
            confidence=1.0 if primary else 0.3,
            needs_clarification=primary is None,
            next_action=(
                "fetch_compounds_by_target_with_sar" if is_sar
                else "fetch_compounds_by_target"
            ),
            reason=(
                f"Target-classified query ({intent}); primary target = {primary}."
                if primary else "Target wording detected but no specific target token."
            ),
            parsed=parsed,
        )

    # ── High-priority target keywords (covers parser misses except when a
    #     drug/compound phrase is explicitly present alongside the kinase).
    kw_hit = _first_priority_target_hit(raw_query)
    if kw_hit is not None:
        canon_kw = _canonical_target_search_token(kw_hit)
        if canon_kw == "KCNH2" or not parsed.molecules:
            return _decision_from_priority_target(raw_query, parsed, kw_hit)

    # ── Rule 4: drug name via ChEMBL synonyms ──────────────────────────────
    name_candidates = [
        m for m in parsed.molecules
        if not _is_chembl_id(m) and not _is_assay_term(m)
    ]

    if name_candidates:
        if any(_token_is_herg_channel_alias(c) for c in name_candidates):
            if _is_toxicity_risk_bundle(raw_query):
                return _toxicity_router_decision(raw_query, parsed)
            return RouterDecision(
                intent="target_lookup",
                resolved_entity_type="protein_target",
                primary_entity="KCNH2",
                confidence=1.0,
                next_action="fetch_compounds_by_target",
                reason=(
                    "Parsed token matches hERG/KCNH2 aliases — forcing target lookup "
                    f"instead of molecule synonym resolution ({TOOL_MAP['target_lookup']})."
                ),
                parsed=parsed,
            )

        best_hit: Optional[Dict[str, Any]] = None
        best_token: Optional[str] = None
        all_hits: List[Dict[str, Any]] = []
        for cand in name_candidates:
            hits = _resolve_via_synonyms(cand)
            if not hits:
                continue
            all_hits.extend(hits[:3])
            top = hits[0]
            top_conf = float(top.get("confidence") or 0.0)
            if best_hit is None or top_conf > float(best_hit.get("confidence") or 0.0):
                best_hit = top
                best_token = cand

        if best_hit and float(best_hit.get("confidence") or 0.0) >= min_confidence:
            cid = best_hit.get("chembl_id")
            pref = best_hit.get("pref_name") or best_token
            wants_similarity = bool(_SIMILARITY_RE.search(raw_query))
            wants_prediction = bool(_PREDICT_RE.search(raw_query))

            if wants_similarity:
                intent = "similarity_search"
                next_action = "run_similarity_pipeline"
            elif wants_prediction:
                intent = "prediction"
                next_action = "validate_smiles_then_predict"
            else:
                intent = "molecule_lookup"
                next_action = "run_evidence_pipeline"

            return RouterDecision(
                intent=intent,
                resolved_entity_type="molecule_name",
                primary_entity=pref,
                chembl_id=cid,
                canonical_smiles=best_hit.get("canonical_smiles"),
                confidence=round(float(best_hit.get("confidence") or 0.0), 3),
                next_action=next_action,
                reason=(
                    f'Resolved {best_token!r} → {pref} ({cid}) via '
                    f'{best_hit.get("match_type")} match.'
                ),
                parsed=parsed,
                candidates=all_hits[:5],
            )

        # Synonym resolver returned nothing usable → general_bio_query with
        # the candidate as a hint so the LLM/UX can suggest a correction.
        return _general_bio_decision(
            parsed,
            primary_entity=name_candidates[0],
            candidates=all_hits[:5],
            confidence=round(
                float(best_hit.get("confidence") or 0.0) if best_hit else 0.0,
                3,
            ),
            reason=(
                f'No high-confidence ChEMBL match for {name_candidates[0]!r}; '
                f"falling back to general biomedical query."
            ),
        )

    # ── Rule 5: nothing actionable extracted ───────────────────────────────
    return _general_bio_decision(
        parsed,
        confidence=0.0,
        reason="No molecule, target or actionable entity detected in input.",
    )
