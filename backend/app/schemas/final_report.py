"""Locked final response contract for POST /chat and report APIs (chem-rag-v2)."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class FinalReportMetadata(BaseModel):
    model_version: str = "v2"
    pipeline: str = "chem-rag-v2"


class FinalReport(BaseModel):
    """Single canonical JSON shape — all agent-facing endpoints return this."""

    query: str
    molecule: Dict[str, Any] = Field(default_factory=dict)
    similar_compounds: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_summary: Dict[str, Any] = Field(default_factory=dict)
    experiment_list: List[Dict[str, Any]] = Field(default_factory=list)
    predictions: List[Dict[str, Any]] = Field(default_factory=list)
    report_sections: Dict[str, Any] = Field(default_factory=dict)
    metadata: FinalReportMetadata = Field(default_factory=FinalReportMetadata)


# ---------------------------------------------------------------------------
# Typed response envelope — discriminated by `response_type`
# ---------------------------------------------------------------------------

class ValidationSuggestionDTO(BaseModel):
    chembl_id: str
    pref_name: Optional[str] = None
    canonical_smiles: Optional[str] = None
    similarity_score: float = 0.0


class ValidationErrorResponse(BaseModel):
    """Returned when the input molecule cannot be resolved."""
    response_type: Literal["validation_error"] = "validation_error"
    query: str
    error_code: str                                    # "invalid_molecule" | "invalid_smiles"
    error_message: str
    suggestions: List[ValidationSuggestionDTO] = Field(default_factory=list)


class NoEvidenceResponse(BaseModel):
    """Returned when molecule resolves but ChEMBL has zero activities."""
    response_type: Literal["no_evidence"] = "no_evidence"
    query: str
    chembl_id: Optional[str] = None
    message: str = "No reliable evidence found for this molecule in ChEMBL."


class NeedsConfirmationResponse(BaseModel):
    """Returned when the parsed query is ambiguous (e.g. multiple molecules / typo)."""
    response_type: Literal["needs_confirmation"] = "needs_confirmation"
    query: str
    message: str = "Did you mean one of the following?"
    suggestions: List[ValidationSuggestionDTO] = Field(default_factory=list)


class ReportResponse(BaseModel):
    """Successful full-pipeline report."""
    response_type: Literal["report"] = "report"
    report: FinalReport


# ── Target-centric responses ───────────────────────────────────────────────

class TargetCompoundDTO(BaseModel):
    chembl_id: str
    molecule_name: Optional[str] = None
    target_chembl_id: Optional[str] = None
    target_pref_name: Optional[str] = None
    organism: Optional[str] = None
    standard_type: Optional[str] = None
    standard_value: Optional[float] = None
    standard_units: Optional[str] = None
    pchembl_value: Optional[float] = None
    assay_type: Optional[str] = None
    confidence_score: Optional[int] = None


class ScaffoldClusterDTO(BaseModel):
    scaffold: str = ""                   # canonical Murcko scaffold SMILES
    size: int
    examples: List[str] = Field(default_factory=list)   # ChEMBL IDs
    median_pchembl: Optional[float] = None
    median_alogp: Optional[float] = None


class PhyschemTrendDTO(BaseModel):
    descriptor: str
    label: str
    unit: str = ""
    n: int
    mean: float
    median: float
    min: float
    max: float


class TargetReportResponse(BaseModel):
    """Successful target-centric retrieval (e.g. "JAK2 inhibitors with IC50 < 50 nM").

    When the query was an SAR analysis, ``scaffold_clusters`` and
    ``physchem_trends`` are populated by :mod:`sar_analysis_service`.
    """
    response_type: Literal["target_report"] = "target_report"
    query: str
    target_name: str
    intent: str = "target_lookup"        # "target_lookup" | "sar_analysis"
    filters: dict = Field(default_factory=dict)
    total: int = 0
    compounds: List[TargetCompoundDTO] = Field(default_factory=list)
    scaffold_clusters: List[ScaffoldClusterDTO] = Field(default_factory=list)
    physchem_trends: List[PhyschemTrendDTO] = Field(default_factory=list)


RiskSummaryLevel = Literal["HIGH", "MEDIUM", "LOW", "UNKNOWN"]


class ToxicityExperimentalEvidenceDTO(BaseModel):
    compound: str = ""
    chembl_id: str = ""
    IC50: str = Field(
        "",
        description="Primary potency endpoint + value summary (endpoint may be Ki, IC50, % inhibition …).",
    )
    source: str = "ChEMBL"


class ToxicityPredictedEvidenceDTO(BaseModel):
    compound: str = ""
    risk_score: str = ""
    model: str = "DeepChem/ML"


class ToxicityRiskResponse(BaseModel):
    """hERG / cardiac ion-channel safety bundles (experimental ChEMBL + optional ML stubs)."""

    response_type: Literal["toxicity_risk_analysis"] = "toxicity_risk_analysis"
    intent: Literal["toxicity_risk_analysis"] = "toxicity_risk_analysis"
    query: str
    target: str = "hERG (KCNH2)"
    experimental_evidence: List[ToxicityExperimentalEvidenceDTO] = Field(default_factory=list)
    predicted_evidence: List[ToxicityPredictedEvidenceDTO] = Field(default_factory=list)
    risk_summary: RiskSummaryLevel = "UNKNOWN"
    note: str = (
        "Experimental rows are aggregated from ChEMBL binding/inhibition assays. "
        "Predicted tiers are stubs until an on-prem hERG QSAR model is wired in."
    )
    filters: dict = Field(default_factory=dict)


# ── Safe-mode block (prompt injection, empty input, etc.) ──────────────────

class BlockedSafeModeResponse(BaseModel):
    response_type: Literal["blocked_safe_mode"] = "blocked_safe_mode"
    query: str
    reason: str                                         # "empty_query" | "prompt_injection"
    message: str = (
        "Your request was held by the safety guard. "
        "Please rephrase as a chemistry / biology question."
    )


# ── Generic biomedical fallback (LLM summariser only) ──────────────────────

class GeneralBioResponse(BaseModel):
    response_type: Literal["general_bio_query"] = "general_bio_query"
    query: str
    message: str = (
        "I couldn't pin this down to a molecule, target or SAR query. "
        "Could you rephrase with a specific drug name, gene symbol or SMILES?"
    )
    candidates: List[ValidationSuggestionDTO] = Field(default_factory=list)


# ── Step 10 — Output Standardization (router envelope) ─────────────────────

class RouterEnvelope(BaseModel):
    """Mandatory routing envelope attached to every chat response.

    Mirrors the strict contract requested in the architecture spec:
      * ``intent``      — one of the six router intents
      * ``entity``      — resolved entity (or ``None``)
      * ``tool_used``   — ChEMBL | RDKit | RAG | DeepChem | LLM | None
      * ``confidence``  — 0.0 – 1.0
      * ``status``      — success | fallback | blocked_safe_mode
    """

    intent: str
    entity: Optional[str] = None
    resolved_entity_type: Optional[str] = None
    tool_used: Optional[str] = None
    confidence: float = 0.0
    status: Literal["success", "fallback", "blocked_safe_mode"] = "success"
    next_action: Optional[str] = None
    reason: Optional[str] = None


# Discriminated union — the `response_type` field drives frontend branching.
ChatResponse = Union[
    ValidationErrorResponse,
    NoEvidenceResponse,
    NeedsConfirmationResponse,
    ReportResponse,
    TargetReportResponse,
    ToxicityRiskResponse,
    BlockedSafeModeResponse,
    GeneralBioResponse,
]
