from __future__ import annotations

"""Pydantic schemas for LLM structured outputs: intent plan, report sections."""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Intent / Tool Plan (ChemLLM intent classifier output)
# ---------------------------------------------------------------------------

class IntentType(str, Enum):
    lookup = "lookup"
    evidence_retrieval = "evidence_retrieval"
    similarity_search = "similarity_search"
    prediction = "prediction"
    reporting = "reporting"
    conversation_memory = "conversation_memory"


class ToolName(str, Enum):
    ResolveMoleculeTool = "ResolveMoleculeTool"
    SimilaritySearchTool = "SimilaritySearchTool"
    FetchChemblEvidenceTool = "FetchChemblEvidenceTool"
    DeepChemPredictTool = "DeepChemPredictTool"
    AggregateEvidenceTool = "AggregateEvidenceTool"
    WriteReportTool = "WriteReportTool"
    VerifyReportTool = "VerifyReportTool"


class MoleculeCandidate(BaseModel):
    type: str  # "name" | "smiles" | "chembl_id" | "inchi" | "inchikey"
    value: str
    confidence: float = 1.0


class PlanFilters(BaseModel):
    target_keywords: List[str] = []
    assay_types: List[str] = []
    endpoints: List[str] = []
    organism: Optional[str] = None
    max_records: int = 500
    time_window: Optional[str] = None


class ToolPlan(BaseModel):
    intents: List[IntentType] = []
    molecule_candidates: List[MoleculeCandidate] = []
    filters: PlanFilters = Field(default_factory=PlanFilters)
    tool_sequence: List[ToolName] = []
    reasoning_brief: str = ""

    @classmethod
    def safe_default(cls, query: str) -> "ToolPlan":
        """Fallback plan: always resolve + retrieve evidence."""
        return cls(
            intents=[IntentType.lookup, IntentType.evidence_retrieval],
            molecule_candidates=[MoleculeCandidate(type="name", value=query, confidence=0.5)],
            tool_sequence=[
                ToolName.ResolveMoleculeTool,
                ToolName.FetchChemblEvidenceTool,
                ToolName.AggregateEvidenceTool,
                ToolName.WriteReportTool,
                ToolName.VerifyReportTool,
            ],
            reasoning_brief="Fallback plan: no structured JSON returned by ChemLLM.",
        )


# ---------------------------------------------------------------------------
# Normalized request (output of input parsing, passed to agent/tools)
# ---------------------------------------------------------------------------

class InputType(str, Enum):
    chembl_id = "chembl_id"
    inchi = "inchi"
    inchikey = "inchikey"
    smiles = "smiles"
    name = "name"


class NormalizedRequest(BaseModel):
    raw_query: str
    input_type: InputType
    value: str
    canonical_smiles: Optional[str] = None
    inchi_key: Optional[str] = None
    chembl_id: Optional[str] = None
    tool_plan: ToolPlan = Field(default_factory=ToolPlan)


# Re-export the natural-language ParsedQuery schema produced by
# :mod:`app.services.query_parser_service` so consumers can import both
# schemas from one place.
from app.services.query_parser_service import ParsedQuery  # noqa: E402, F401


# ---------------------------------------------------------------------------
# Report JSON schema
# ---------------------------------------------------------------------------

class MoleculeSection(BaseModel):
    chembl_id: Optional[str] = None
    pref_name: Optional[str] = None
    canonical_smiles: Optional[str] = None
    inchi_key: Optional[str] = None
    mw: Optional[float] = None
    logp: Optional[float] = None
    tpsa: Optional[float] = None
    hba: Optional[int] = None
    hbd: Optional[int] = None
    rot_bonds: Optional[int] = None
    formula: Optional[str] = None


class SimilarCompound(BaseModel):
    chembl_id: str
    tanimoto: float
    pref_name: Optional[str] = None
    canonical_smiles: Optional[str] = None
    headline_activity: Optional[str] = None


class EvidenceSummary(BaseModel):
    top_targets: List[Dict[str, Any]] = []
    potency_stats_by_target: List[Dict[str, Any]] = []
    assay_counts: Dict[str, int] = {}
    total_activities: int | None = None
    cell_line_activity: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Cell-line–centric activity counts (kept separate from protein targets)",
    )
    summary_text: Optional[str] = Field(
        default=None,
        description="Concise scientific summary of evidence after QC",
    )
    target_clusters: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="IC50 clusters by target_chembl_id (nM-normalized)",
    )


class ExperimentEntry(BaseModel):
    activity_id: Optional[int] = None
    chembl_id: str
    assay_chembl_id: Optional[str] = None
    target_chembl_id: Optional[str] = None
    target_pref_name: Optional[str] = None
    standard_type: Optional[str] = None
    standard_value: Optional[float] = None
    standard_units: Optional[str] = None
    value_nm: Optional[float] = None
    pchembl_value: Optional[float] = None
    assay_type: Optional[str] = None
    confidence_score: Optional[int] = None
    doc_chembl_id: Optional[str] = None
    pubmed_id: Optional[str] = None


class PredictionEntry(BaseModel):
    task: str
    label: str = "Predicted"
    value: Optional[float] = None
    probability: Optional[float] = None
    uncertainty: Optional[float] = None
    unit: Optional[str] = None
    model_name: str
    training_dataset: str


class ReportSections(BaseModel):
    executive_summary: str = ""
    molecular_identity: str = ""
    physchem: str = ""
    similar_compounds: str = ""
    chembl_evidence: str = ""
    predictions: str = ""
    risks: str = ""
    next_experiments: str = ""
    citations: str = ""
    disclaimer: str = (
        "This report is for research purposes only and does not constitute medical advice. "
        "All predictions are computational estimates and must be validated experimentally."
    )


class ReportJSON(BaseModel):
    report_id: str
    created_at: str
    query: str
    molecule: MoleculeSection = Field(default_factory=MoleculeSection)
    similar_compounds: List[SimilarCompound] = []
    evidence_summary: EvidenceSummary = Field(default_factory=EvidenceSummary)
    experiment_list: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Top 3–5 suggested follow-on experiments (target, assay, priority)",
    )
    predictions: List[PredictionEntry] = []
    report_sections: ReportSections = Field(default_factory=ReportSections)
