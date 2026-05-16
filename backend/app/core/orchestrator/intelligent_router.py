"""Signal-based query routing for auto-mode tagging (no ML). HYBRID = chembl AND vector."""

from __future__ import annotations

import re
from dataclasses import dataclass


class RouteType:
    CHEMBL = "chembl"
    VECTOR = "vector"
    HYBRID = "hybrid"


@dataclass
class RouteDecision:
    route: str
    confidence: float
    reason: str


_CHEMBL_ID = re.compile(r"chembl\d+", re.I)


def _lower(q: str) -> str:
    return (q or "").strip().lower()


def chembl_signals(query: str) -> bool:
    """True when query indicates ChEMBL / bioactivity-style intent."""
    low = _lower(query)
    if "chembl" in low or _CHEMBL_ID.search(query or ""):
        return True
    if re.search(r"\b(ic50|ki|ec50|kd)\b", low):
        return True
    if re.search(r"\b(activity|assay)\b", low):
        return True
    if re.search(
        r"\b(cox-?\d*|ptgs\d*|kinase|receptor|enzyme|target)\b.*\b(activity|ic50|ki|assay|inhibition)\b",
        low,
    ):
        return True
    if re.search(
        r"\b(aspirin|ibuprofen|acetaminophen|paracetamol|compound|molecule|ligand|inhibitor)\b.*\b(ic50|ki|activity|assay)\b",
        low,
    ):
        return True
    return False


def vector_signals(query: str) -> bool:
    """True when query indicates similarity / analog exploration intent."""
    low = _lower(query)
    if re.search(r"\b(similar|analogs?|similarity|embedding|tanimoto)\b", low):
        return True
    if "find compounds like" in low:
        return True
    if re.search(r"\bcompounds?\s+like\b", low):
        return True
    if re.search(r"\b(similar\s+to|like\s+this|structural\s+analog)\b", low):
        return True
    if re.search(r"\blike\b", low) and re.search(
        r"\b(compound|structure|smiles|molecule|analog|scaffold)\b", low
    ):
        return True
    return False


def route_query(query: str) -> RouteDecision:
    """
    Truth source: HYBRID only when both chembl_signals and vector_signals are true.
    No ambiguity-keyword shortcuts (signal overlap only).
    """
    q = query or ""
    low = _lower(q)
    if not low:
        return RouteDecision(
            route=RouteType.VECTOR,
            confidence=0.4,
            reason="empty_query_default_vector",
        )

    chem = chembl_signals(q)
    vec = vector_signals(q)

    if chem and vec:
        return RouteDecision(
            route=RouteType.HYBRID,
            confidence=0.9,
            reason="both_chembl_and_vector_signals",
        )
    if chem:
        return RouteDecision(
            route=RouteType.CHEMBL,
            confidence=0.9,
            reason="chembl_bioactivity_signals_only",
        )
    if vec:
        return RouteDecision(
            route=RouteType.VECTOR,
            confidence=0.9,
            reason="similarity_exploration_signals_only",
        )

    return RouteDecision(
        route=RouteType.VECTOR,
        confidence=0.4,
        reason="default_vector_no_chembl_or_vector_signal",
    )
