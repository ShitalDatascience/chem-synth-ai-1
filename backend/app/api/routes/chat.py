"""POST /chat — strictly-routed natural-language query handler.

Pipeline (each stage may short-circuit):

    raw_query
      └─► safe_query_guard.safe_guard()   ── empty / prompt-injection
            └─► query_router.route_query() ── intent + entity + next_action
                  └─► dispatcher
                        ├─► fetch_compounds_by_target(_with_sar)  (ChEMBL)
                        ├─► run_evidence_pipeline                  (ChEMBL → RAG)
                        ├─► run_similarity_pipeline                (RAG)
                        ├─► validate_smiles_then_predict           (DeepChem)
                        ├─► general_llm_response                   (LLM summariser)
                        └─► ask_for_clarification                  (no LLM call)

Every response is wrapped in a :class:`RouterEnvelope` (Step 10 of the spec)
so downstream agents always see ``intent``, ``entity``, ``tool_used``,
``confidence`` and ``status`` regardless of which branch ran.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.orchestrator.query_engine import QueryEngine
from app.schemas.final_report import (
    BlockedSafeModeResponse,
    GeneralBioResponse,
    NoEvidenceResponse,
    PhyschemTrendDTO,
    ReportResponse,
    RiskSummaryLevel,
    RouterEnvelope,
    ScaffoldClusterDTO,
    TargetCompoundDTO,
    TargetReportResponse,
    ToxicityExperimentalEvidenceDTO,
    ToxicityRiskResponse,
    ValidationErrorResponse,
    ValidationSuggestionDTO,
)
from app.services.chembl_service import ChemblService
from app.services.query_router import RouterDecision, route_query
from app.services.safe_query_guard import safe_guard
from app.services.sar_analysis_service import (
    compute_physchem_trends,
    compute_scaffold_clusters,
)
from app.services.validation_service import validate_molecule_query

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    query: str


# ---------------------------------------------------------------------------
# Envelope & failure handling (Steps 5, 9, 10)
# ---------------------------------------------------------------------------

# next_action → tool tag advertised in the envelope.
_NEXT_ACTION_TOOL: Dict[str, str] = {
    "run_evidence_pipeline":             "ChEMBL+RAG",
    "fetch_compounds_by_target":         "ChEMBL",
    "fetch_compounds_by_target_with_sar": "ChEMBL+RDKit",
    "chembl_safety_assay_query":         "ChEMBL_safety_assay",
    "run_similarity_pipeline":           "RAG",
    "validate_smiles_then_predict":      "DeepChem",
    "general_llm_response":              "LLM",
    "ask_for_clarification":             "None",
}


def _envelope_payload(
    decision: RouterDecision,
    *,
    status: str = "success",
    tool_override: Optional[str] = None,
) -> Dict[str, Any]:
    env = RouterEnvelope(
        intent=decision.intent,
        entity=decision.primary_entity,
        resolved_entity_type=decision.resolved_entity_type,
        tool_used=tool_override or _NEXT_ACTION_TOOL.get(decision.next_action, "None"),
        confidence=float(decision.confidence or 0.0),
        status=status,
        next_action=decision.next_action,
        reason=decision.reason,
    )
    return env.model_dump()


def _wrap(decision: RouterDecision, body: BaseModel, *, status: str = "success",
          tool_override: Optional[str] = None) -> JSONResponse:
    """Attach the routing envelope to the typed response body."""
    payload = body.model_dump()
    payload["router"] = _envelope_payload(decision, status=status, tool_override=tool_override)
    return JSONResponse(status_code=200, content=payload)


def _handle_tool_failure(
    raw_query: str,
    decision: RouterDecision,
    error: Exception,
    *,
    tool: str,
) -> JSONResponse:
    """Step 5 — graceful fallback for any execution-layer failure.

    Returns a ``general_bio_query`` body with ``status='fallback'`` so the
    frontend can render a friendly degraded-mode message instead of a 500.
    """
    logger.exception("[CHAT] %s tool failure: %s", tool, error)
    body = GeneralBioResponse(
        query=raw_query,
        message=(
            "We couldn't process this request in structured mode. "
            "Switching to general biomedical search."
        ),
    )
    return _wrap(decision, body, status="fallback", tool_override=tool)


# ---------------------------------------------------------------------------
# Helpers (target query path)
# ---------------------------------------------------------------------------

def _coerce_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _dedupe_best_rows_per_compound(rows: list[dict], *, cap: int = 120) -> list[dict]:
    """Keep the strongest potency row per molecule (pChEMBL desc; tie-break nM ascending)."""

    def potency_sort_key(row: dict) -> tuple[float, float]:
        pch = _coerce_float(row.get("pchembl_value"))
        pch_term = float("inf")
        if pch is not None:
            pch_term = -float(pch)
        su = str(row.get("standard_units") or "").upper().strip()
        sv = _coerce_float(row.get("standard_value"))
        if su == "NM" and sv is not None:
            nm_term = float(sv)
        else:
            nm_term = float("1e18")
        return (pch_term, nm_term)

    ranked = sorted(rows, key=potency_sort_key)
    picked: dict[str, dict] = {}
    for r in ranked:
        cid = str(r.get("chembl_id") or "")
        if not cid:
            continue
        if cid not in picked:
            picked[cid] = r
        if len(picked) >= cap:
            break
    return list(picked.values())


def _herg_potency_nm(row: dict) -> Optional[float]:
    su = str(row.get("standard_units") or "").upper().strip()
    if su != "NM":
        return None
    st = str(row.get("standard_type") or "").upper()
    if st not in {"IC50", "KI", "KD", "EC50", "PIC50", "GI50"}:
        return None
    return _coerce_float(row.get("standard_value"))


def _risk_summary_from_rows(rows: list[dict]) -> RiskSummaryLevel:
    vals = [_herg_potency_nm(r) for r in rows]
    vals_nm = sorted(v for v in vals if v is not None)
    if not vals_nm:
        return "UNKNOWN"
    vmin = vals_nm[0]
    potent = sum(1 for v in vals_nm if v <= 100.0)
    if vmin <= 30 and potent >= 3:
        return "HIGH"
    if vmin <= 100 and potent >= 2:
        return "HIGH"
    if vmin <= 1000:
        return "MEDIUM"
    return "LOW"


def _row_to_target_compound(row: dict) -> TargetCompoundDTO:
    return TargetCompoundDTO(
        chembl_id=str(row.get("chembl_id") or ""),
        molecule_name=row.get("molecule_name"),
        target_chembl_id=row.get("target_chembl_id"),
        target_pref_name=row.get("target_pref_name"),
        organism=row.get("organism"),
        standard_type=row.get("standard_type"),
        standard_value=_coerce_float(row.get("standard_value")),
        standard_units=row.get("standard_units"),
        pchembl_value=_coerce_float(row.get("pchembl_value")),
        assay_type=row.get("assay_type"),
        confidence_score=row.get("confidence_score"),
    )


def _validation_suggestions_to_dto(suggestions) -> list[ValidationSuggestionDTO]:
    return [
        ValidationSuggestionDTO(
            chembl_id=s.chembl_id,
            pref_name=s.pref_name,
            canonical_smiles=s.canonical_smiles,
            similarity_score=s.similarity_score,
        )
        for s in suggestions
    ]


# ---------------------------------------------------------------------------
# Dispatchers — one per RouterDecision.next_action
# ---------------------------------------------------------------------------

def _dispatch_target(raw_query: str, decision: RouterDecision) -> JSONResponse:
    parsed = decision.parsed
    target_name = decision.primary_entity or ""
    if not target_name:
        body = ValidationErrorResponse(
            query=raw_query,
            error_code="invalid_target",
            error_message=(
                "I detected this as a target-lookup query but couldn't identify "
                'the target. Try something like "Find JAK2 inhibitors with IC50 < 50 nM".'
            ),
        )
        return _wrap(decision, body, status="fallback")

    is_sar = decision.next_action == "fetch_compounds_by_target_with_sar"
    filters = dict(parsed.filters or {})
    endpoints = filters.get("endpoints") or ["IC50", "Ki", "Kd", "EC50"]
    value_max_nm = filters.get("value_max_nm")
    value_min_nm = filters.get("value_min_nm")
    organism = filters.get("organism")
    exclude_cell_based = bool(filters.get("exclude_cell_based", False))
    row_limit = 200 if is_sar else 50

    try:
        rows = ChemblService().fetch_compounds_by_target(
            target_name,
            endpoints=list(endpoints),
            value_max_nm=value_max_nm,
            value_min_nm=value_min_nm,
            organism=organism,
            exclude_cell_based=exclude_cell_based,
            limit=row_limit,
        )
    except Exception as exc:
        return _handle_tool_failure(raw_query, decision, exc, tool="ChEMBL")

    compounds = [_row_to_target_compound(r) for r in rows[:50]]
    scaffold_clusters: list[ScaffoldClusterDTO] = []
    physchem_trends: list[PhyschemTrendDTO] = []
    if is_sar and rows:
        try:
            scaffold_clusters = [
                ScaffoldClusterDTO(**c) for c in compute_scaffold_clusters(rows, top_n=8)
            ]
            physchem_trends = [
                PhyschemTrendDTO(**t) for t in compute_physchem_trends(rows)
            ]
        except Exception as exc:
            logger.warning("[CHAT] SAR enrichment failed: %s", exc)

    body = TargetReportResponse(
        query=raw_query,
        target_name=target_name,
        intent=decision.intent,
        filters={
            "endpoints": list(endpoints),
            "value_max_nm": value_max_nm,
            "value_min_nm": value_min_nm,
            "organism": organism,
            "exclude_cell_based": exclude_cell_based,
        },
        total=len(rows),
        compounds=compounds,
        scaffold_clusters=scaffold_clusters,
        physchem_trends=physchem_trends,
    )
    logger.info(
        "[CHAT] target_report target=%r intent=%s rows=%d clusters=%d trends=%d",
        target_name, decision.intent, len(rows),
        len(scaffold_clusters), len(physchem_trends),
    )
    return _wrap(decision, body)


def _dispatch_toxicity_safety(raw_query: str, decision: RouterDecision) -> JSONResponse:
    """ChEMBL binding / inhibition activities on hERG(KCNH2) plus structured risk scaffolding."""
    parsed = decision.parsed
    target_token = decision.primary_entity or "KCNH2"
    display = "hERG (KCNH2)"

    filters = dict(parsed.filters or {})
    _VALID_EP_TYPES = {"IC50", "KI", "KD", "EC50", "% INHIBITION", "INHIBITION", "POTENCY", "PIC50"}
    raw_eps = filters.get("endpoints")
    sanitized_eps: list[str] = []
    if isinstance(raw_eps, list):
        sanitized_eps = [str(e).strip() for e in raw_eps if str(e).strip().upper() in _VALID_EP_TYPES]
    if not sanitized_eps:
        sanitized_eps = ["IC50", "Ki", "Kd", "EC50"]

    organism = filters.get("organism")

    assay_payload = dict(
        target_label=display,
        assay_types_allowed=list(filters.get("assay_types_allowlist") or ["B", "F"]),
        standard_units_allowed=list(
            filters.get("standard_units_allowed") or ["nM", "%"],
        ),
        exclude_cell_based=bool(filters.get("exclude_cell_based", False)),
        endpoints=list(sanitized_eps),
    )

    try:
        rows = ChemblService().fetch_compounds_by_target(
            target_token,
            endpoints=list(sanitized_eps),
            organism=organism,
            exclude_cell_based=bool(filters.get("exclude_cell_based", False)),
            assay_types_allowlist=list(filters.get("assay_types_allowlist") or ["B", "F"]),
            standard_units_allowed=list(filters.get("standard_units_allowed") or ["nM", "%"]),
            limit=min(int(filters.get("row_limit") or 200), 500),
            value_max_nm=filters.get("value_max_nm"),
            value_min_nm=filters.get("value_min_nm"),
        )
    except Exception as exc:
        return _handle_tool_failure(raw_query, decision, exc, tool="ChEMBL_safety_assay")

    best_rows = _dedupe_best_rows_per_compound(rows, cap=120)
    exp_out: list[ToxicityExperimentalEvidenceDTO] = []
    for r in best_rows[:60]:
        st = str(r.get("standard_type") or "")
        val = r.get("standard_value")
        su = str(r.get("standard_units") or "").strip()
        detail = (
            f"{st}: {val} {su}".strip()
            if val is not None
            else (st or "Activity")
        )
        exp_out.append(
            ToxicityExperimentalEvidenceDTO(
                compound=str(r.get("molecule_name") or ""),
                chembl_id=str(r.get("chembl_id") or ""),
                IC50=detail,
                source="ChEMBL",
            ),
        )

    risk = _risk_summary_from_rows(best_rows)
    note_parts = [
        assay_payload["target_label"],
        f"risk tier derived from aggregated ChEMBL nM potencies ({len(best_rows)} unique compounds). "
        "Machine-learning hERG QSAR tiers are placeholders until wired into DeepChem / on-prem models.",
    ]

    body = ToxicityRiskResponse(
        intent="toxicity_risk_analysis",
        query=raw_query,
        target=display,
        experimental_evidence=exp_out,
        predicted_evidence=[],
        risk_summary=risk,
        filters=assay_payload,
        note=" ".join(note_parts),
    )
    logger.info("[CHAT] toxicity_risk target=%r rows=%d risk=%s", target_token, len(rows), risk)
    return _wrap(decision, body)


def _dispatch_evidence(raw_query: str, decision: RouterDecision) -> JSONResponse:
    """Run the full evidence/RAG pipeline for a resolved molecule or SMILES."""
    name_for_pipeline = (
        decision.primary_entity
        or decision.canonical_smiles
        or decision.chembl_id
        or ""
    )
    if not name_for_pipeline:
        body = ValidationErrorResponse(
            query=raw_query,
            error_code="invalid_molecule",
            error_message="Could not determine a molecule to analyse.",
        )
        return _wrap(decision, body, status="fallback")

    validation = validate_molecule_query(name_for_pipeline)
    if not validation.valid:
        body = ValidationErrorResponse(
            query=raw_query,
            error_code=validation.error_code or "invalid_molecule",
            error_message=validation.error_message or "Unknown validation error.",
            suggestions=_validation_suggestions_to_dto(validation.suggestions),
        )
        return _wrap(decision, body, status="fallback")

    resolved_query = validation.resolved_query or name_for_pipeline
    try:
        result = QueryEngine().execute(resolved_query, mode="chat")
    except Exception as exc:
        return _handle_tool_failure(raw_query, decision, exc, tool="ChEMBL+RAG")

    evidence = getattr(result, "evidence_summary", None) or {}
    total = evidence.get("total_activities") if isinstance(evidence, dict) else None
    if total is not None and int(total) == 0:
        body = NoEvidenceResponse(
            query=raw_query,
            chembl_id=decision.chembl_id or validation.chembl_id,
        )
        return _wrap(decision, body, status="fallback")

    return _wrap(decision, ReportResponse(report=result))


def _dispatch_similarity(raw_query: str, decision: RouterDecision) -> JSONResponse:
    """Similarity search reuses the evidence pipeline; QueryEngine handles
    Tanimoto / nearest-neighbour ordering internally for ``mode="chat"``."""
    return _dispatch_evidence(raw_query, decision)


def _dispatch_prediction(raw_query: str, decision: RouterDecision) -> JSONResponse:
    """Prediction path — DeepChem is invoked downstream by QueryEngine when
    a SMILES is in scope.  Falls back to evidence pipeline for now."""
    return _dispatch_evidence(raw_query, decision)


def _dispatch_general(raw_query: str, decision: RouterDecision) -> JSONResponse:
    """Fallback when the router could not lock onto a structured intent."""
    suggestions = [
        ValidationSuggestionDTO(
            chembl_id=str(c.get("chembl_id") or ""),
            pref_name=c.get("pref_name"),
            canonical_smiles=c.get("canonical_smiles"),
            similarity_score=float(c.get("confidence") or 0.0),
        )
        for c in (decision.candidates or [])[:5]
    ]
    body = GeneralBioResponse(
        query=raw_query,
        candidates=suggestions,
    )
    status = "fallback" if decision.next_action == "ask_for_clarification" else "success"
    return _wrap(decision, body, status=status)


_DISPATCH = {
    "fetch_compounds_by_target":         _dispatch_target,
    "fetch_compounds_by_target_with_sar": _dispatch_target,
    "chembl_safety_assay_query":       _dispatch_toxicity_safety,
    "run_evidence_pipeline":             _dispatch_evidence,
    "run_similarity_pipeline":           _dispatch_similarity,
    "validate_smiles_then_predict":      _dispatch_prediction,
    "general_llm_response":              _dispatch_general,
    "ask_for_clarification":             _dispatch_general,
}


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.post("/chat")
def chat(request: ChatRequest) -> JSONResponse:
    raw_query = request.query or ""

    # ── Stage 1: SAFE GUARD ────────────────────────────────────────────────
    guard = safe_guard(raw_query)
    if guard.block:
        logger.info("[CHAT] safe_guard blocked: %s", guard.reason)
        body = BlockedSafeModeResponse(query=raw_query, reason=guard.reason or "blocked")
        env = RouterEnvelope(
            intent="general_bio_query",
            entity=None,
            tool_used="None",
            confidence=0.0,
            status="blocked_safe_mode",
            reason=guard.reason,
        )
        payload = body.model_dump()
        payload["router"] = env.model_dump()
        return JSONResponse(status_code=200, content=payload)

    sanitized = guard.sanitized_query or raw_query

    # ── Stage 2: INTENT ROUTER ─────────────────────────────────────────────
    try:
        decision = route_query(sanitized)
    except Exception as exc:
        logger.exception("[CHAT] router failure: %s", exc)
        body = GeneralBioResponse(
            query=sanitized,
            message="Routing failed. Switching to general biomedical search.",
        )
        env = RouterEnvelope(
            intent="general_bio_query",
            entity=None,
            tool_used="None",
            confidence=0.0,
            status="fallback",
            reason=str(exc),
        )
        payload = body.model_dump()
        payload["router"] = env.model_dump()
        return JSONResponse(status_code=200, content=payload)

    logger.info(
        "[CHAT] router intent=%s entity=%r type=%s next=%s conf=%.2f",
        decision.intent, decision.primary_entity, decision.resolved_entity_type,
        decision.next_action, decision.confidence,
    )

    # ── Stage 3: DISPATCH (tool selector + execution) ──────────────────────
    handler = _DISPATCH.get(decision.next_action, _dispatch_general)
    try:
        return handler(sanitized, decision)
    except Exception as exc:
        return _handle_tool_failure(sanitized, decision, exc, tool="dispatcher")
