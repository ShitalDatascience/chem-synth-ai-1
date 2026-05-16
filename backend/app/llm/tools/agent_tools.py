from __future__ import annotations

"""LangChain Pydantic-typed tools for the ChemSynth agentic RAG pipeline.

All tools are importable without langchain installed (the decorator is only applied
if langchain is available). They can also be called as plain Python functions.
"""

import logging
import math
from typing import Any, Dict, List, Optional, Type

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

try:
    from langchain.tools import BaseTool
    _LC_AVAILABLE = True
except ImportError:
    _LC_AVAILABLE = False
    BaseTool = object  # type: ignore[assignment, misc]


# ---------------------------------------------------------------------------
# Helper: lazy service imports
# ---------------------------------------------------------------------------

def _chembl():
    from app.services.chembl_service import ChemblService, EvidenceFilters
    return ChemblService(), EvidenceFilters


def _rdkit():
    from app.services import rdkit_service
    return rdkit_service


def _milvus():
    from app.services.milvus_service import MilvusService
    return MilvusService()


def _deepchem():
    from app.services import deepchem_service
    return deepchem_service


def _chemllm():
    from app.llm.chemllm_client import ChemLLMClient
    return ChemLLMClient()


# ===========================================================================
# 1. ResolveMoleculeTool
# ===========================================================================

class ResolveMoleculeInput(BaseModel):
    query_text: str = Field(..., description="Drug name or text to resolve to a ChEMBL molecule")
    optional_smiles: Optional[str] = Field(None, description="SMILES if already known")
    limit: int = Field(5, description="Max number of candidate molecules to return")


class ResolveMoleculeOutput(BaseModel):
    candidates: List[Dict[str, Any]]
    resolved_chembl_id: Optional[str] = None
    resolved_smiles: Optional[str] = None
    resolved_inchi_key: Optional[str] = None


def resolve_molecule(inp: ResolveMoleculeInput) -> ResolveMoleculeOutput:
    chembl, EvidenceFilters = _chembl()
    candidates_raw = chembl.resolve_molecule_by_name(inp.query_text, limit=inp.limit)
    candidates = [
        {
            "chembl_id": c.molecule.chembl_id,
            "pref_name": c.molecule.pref_name,
            "canonical_smiles": c.molecule.canonical_smiles,
            "standard_inchi_key": c.molecule.standard_inchi_key,
            "match_type": c.match_type,
            "confidence": c.confidence,
        }
        for c in candidates_raw
    ]
    top = candidates[0] if candidates else {}
    return ResolveMoleculeOutput(
        candidates=candidates,
        resolved_chembl_id=top.get("chembl_id"),
        resolved_smiles=top.get("canonical_smiles"),
        resolved_inchi_key=top.get("standard_inchi_key"),
    )


class ResolveMoleculeTool(BaseTool):  # type: ignore[misc]
    name: str = "ResolveMoleculeTool"
    description: str = (
        "Resolve a drug name or text query to ChEMBL molecule IDs and SMILES. "
        "Returns candidate molecules sorted by match confidence."
    )
    args_schema: Type[BaseModel] = ResolveMoleculeInput

    def _run(self, **kwargs: Any) -> Dict:
        return resolve_molecule(ResolveMoleculeInput(**kwargs)).model_dump()


# ===========================================================================
# 2. SimilaritySearchTool
# ===========================================================================

class SimilaritySearchInput(BaseModel):
    smiles: str = Field(..., description="Canonical SMILES of the query molecule")
    top_k: int = Field(100, description="Final number of similar molecules to return after rerank")
    min_similarity: float = Field(0.2, description="Minimum RDKit Tanimoto (Morgan r=2, 2048) threshold")


class SimilaritySearchOutput(BaseModel):
    hits: List[Dict[str, Any]]


def similarity_search(inp: SimilaritySearchInput) -> SimilaritySearchOutput:
    from app.config import get_settings

    settings = get_settings()
    milvus = _milvus()

    reranked = milvus.search_with_rdkit_rerank(
        inp.smiles, top_k_coarse=settings.milvus_top_k_candidates
    )
    reranked = [h for h in reranked if (h.tanimoto or 0.0) >= inp.min_similarity]
    reranked = reranked[: inp.top_k]

    return SimilaritySearchOutput(
        hits=[
            {
                "chembl_id": h.chembl_id,
                "tanimoto": round(h.tanimoto or 0.0, 4),
                "smiles": h.smiles,
                "inchi_key": h.inchi_key,
                "milvus_score": round(h.milvus_score, 4),
            }
            for h in reranked
        ]
    )


class SimilaritySearchTool(BaseTool):  # type: ignore[misc]
    name: str = "SimilaritySearchTool"
    description: str = (
        "Search for structurally similar compounds in Milvus using Morgan fingerprints, "
        "then rerank with RDKit Tanimoto for correct chemical similarity ordering."
    )
    args_schema: Type[BaseModel] = SimilaritySearchInput

    def _run(self, **kwargs: Any) -> Dict:
        return similarity_search(SimilaritySearchInput(**kwargs)).model_dump()


# ===========================================================================
# 3. FetchChemblEvidenceTool
# ===========================================================================

class FetchChemblEvidenceInput(BaseModel):
    chembl_ids: List[str] = Field(..., description="List of ChEMBL IDs to fetch evidence for")
    target_keywords: List[str] = Field([], description="Filter by target name keywords")
    assay_types: List[str] = Field([], description="Filter by assay type (e.g. B, F, A)")
    organisms: List[str] = Field([], description="Filter by target organism")
    min_confidence_score: Optional[int] = Field(None, description="Minimum assay confidence score")
    endpoint_types: List[str] = Field([], description="Endpoint types to include (IC50, Ki, etc.)")
    max_rows: int = Field(500, description="Max evidence rows to return")


class FetchChemblEvidenceOutput(BaseModel):
    total: int
    rows: List[Dict[str, Any]]


def fetch_chembl_evidence(inp: FetchChemblEvidenceInput) -> FetchChemblEvidenceOutput:
    from app.services.chembl_service import EvidenceFilters
    chembl, _ = _chembl()
    filters = EvidenceFilters(
        target_keywords=inp.target_keywords,
        assay_types=inp.assay_types,
        organisms=inp.organisms,
        min_confidence_score=inp.min_confidence_score,
        endpoint_types=inp.endpoint_types,
        max_rows=inp.max_rows,
    )
    rows = chembl.get_evidence_bundle(inp.chembl_ids, filters=filters)
    return FetchChemblEvidenceOutput(
        total=len(rows),
        rows=[r.model_dump() for r in rows],
    )


class FetchChemblEvidenceTool(BaseTool):  # type: ignore[misc]
    name: str = "FetchChemblEvidenceTool"
    description: str = (
        "Fetch bounded, normalized bioactivity evidence from ChEMBL Postgres "
        "(activities + assays + targets + citations) for a list of ChEMBL IDs."
    )
    args_schema: Type[BaseModel] = FetchChemblEvidenceInput

    def _run(self, **kwargs: Any) -> Dict:
        return fetch_chembl_evidence(FetchChemblEvidenceInput(**kwargs)).model_dump()


# ===========================================================================
# 4. DeepChemPredictTool
# ===========================================================================

class DeepChemPredictInput(BaseModel):
    smiles: str = Field(..., description="Canonical SMILES of the molecule")
    tasks: List[str] = Field(
        default=["esol_solubility", "clintox_toxicity"],
        description="Prediction tasks: esol_solubility, clintox_toxicity",
    )
    inchi_key: Optional[str] = Field(None, description="InChIKey for caching")
    n_ensemble: int = Field(1, description="Ensemble runs for uncertainty proxy")


class DeepChemPredictOutput(BaseModel):
    smiles: str
    results: List[Dict[str, Any]]


def deepchem_predict(inp: DeepChemPredictInput) -> DeepChemPredictOutput:
    dc_svc = _deepchem()
    preds = dc_svc.predict(
        smiles=inp.smiles,
        tasks=inp.tasks,
        inchi_key=inp.inchi_key,
        n_ensemble=inp.n_ensemble,
    )
    return DeepChemPredictOutput(
        smiles=preds.smiles,
        results=[r.model_dump() for r in preds.results],
    )


class DeepChemPredictTool(BaseTool):  # type: ignore[misc]
    name: str = "DeepChemPredictTool"
    description: str = (
        "Run DeepChem ML predictions (solubility, toxicity) for a SMILES string. "
        "All results are labeled 'Predicted' and must not be mixed with experimental data."
    )
    args_schema: Type[BaseModel] = DeepChemPredictInput

    def _run(self, **kwargs: Any) -> Dict:
        return deepchem_predict(DeepChemPredictInput(**kwargs)).model_dump()


# ===========================================================================
# 5. AggregateEvidenceTool (pandas-based)
# ===========================================================================

class AggregateEvidenceInput(BaseModel):
    evidence_rows: List[Dict[str, Any]] = Field(..., description="Normalized EvidenceRow dicts")
    similar_hits: List[Dict[str, Any]] = Field([], description="SimilarityHit dicts with tanimoto")
    user_intent: str = Field("", description="User intent string for context")


class AggregateEvidenceOutput(BaseModel):
    top_targets: List[Dict[str, Any]]
    potency_stats_by_target: List[Dict[str, Any]]
    assay_counts: Dict[str, int]
    nearest_neighbors_summary: List[Dict[str, Any]]
    total_activities: int


def aggregate_evidence(inp: AggregateEvidenceInput) -> AggregateEvidenceOutput:
    rows = inp.evidence_rows
    if not rows:
        return AggregateEvidenceOutput(
            top_targets=[], potency_stats_by_target={},
            assay_counts={}, nearest_neighbors_summary=[], total_activities=0
        )

    df = pd.DataFrame(rows)

    # --- Top targets ---
    top_targets = []
    if "target_pref_name" in df.columns:
        tgt_counts = (
            df.groupby(["target_chembl_id", "target_pref_name", "target_organism"])
            .size()
            .reset_index(name="activity_count")
            .sort_values("activity_count", ascending=False)
            .head(10)
        )
        top_targets = tgt_counts.to_dict("records")

    # --- Potency stats per target ---
    potency_stats = []
    if "target_pref_name" in df.columns and "value_nm" in df.columns:
        potency_df = df[df["value_nm"].notna()].copy()
        if not potency_df.empty:
            potency_df["log10_nm"] = potency_df["value_nm"].apply(
                lambda x: math.log10(x) if x > 0 else None
            )
            stats = (
                potency_df.groupby(["target_chembl_id", "target_pref_name", "standard_type"])
                .agg(
                    count=("value_nm", "count"),
                    best_nm=("value_nm", "min"),
                    median_nm=("value_nm", "median"),
                )
                .reset_index()
            )
            potency_stats = stats.to_dict("records")

    # --- Assay type counts ---
    assay_counts: dict[str, int] = {}
    if "assay_type" in df.columns:
        assay_counts = df["assay_type"].value_counts().to_dict()

    # --- Nearest neighbors summary ---
    nn_summary = []
    for hit in sorted(inp.similar_hits, key=lambda h: h.get("tanimoto", 0), reverse=True)[:10]:
        nn_summary.append(
            {
                "chembl_id": hit.get("chembl_id"),
                "tanimoto": hit.get("tanimoto"),
                "smiles": hit.get("smiles"),
            }
        )

    return AggregateEvidenceOutput(
        top_targets=top_targets,
        potency_stats_by_target=potency_stats,
        assay_counts=assay_counts,
        nearest_neighbors_summary=nn_summary,
        total_activities=len(rows),
    )


class AggregateEvidenceTool(BaseTool):  # type: ignore[misc]
    name: str = "AggregateEvidenceTool"
    description: str = (
        "Aggregate normalized evidence rows (pandas) into a compact EvidenceBundleSummary "
        "suitable for fitting in the ChemLLM context window."
    )
    args_schema: Type[BaseModel] = AggregateEvidenceInput

    def _run(self, **kwargs: Any) -> Dict:
        return aggregate_evidence(AggregateEvidenceInput(**kwargs)).model_dump()


# ===========================================================================
# 6. WriteReportTool
# ===========================================================================

class WriteReportInput(BaseModel):
    evidence_summary: Dict[str, Any] = Field(..., description="AggregateEvidenceTool output")
    predictions: List[Dict[str, Any]] = Field([], description="DeepChemPredictTool results")
    molecule: Dict[str, Any] = Field({}, description="Molecule identity dict")
    query: str = Field("", description="Original user query")


class WriteReportOutput(BaseModel):
    sections: Dict[str, str]


def write_report(inp: WriteReportInput) -> WriteReportOutput:
    client = _chemllm()
    bundle = {
        "molecule": inp.molecule,
        "evidence_summary": inp.evidence_summary,
    }
    sections = client.generate_report(
        evidence_bundle=bundle,
        predictions=inp.predictions,
        query=inp.query,
    )
    return WriteReportOutput(sections=sections.model_dump())


class WriteReportTool(BaseTool):  # type: ignore[misc]
    name: str = "WriteReportTool"
    description: str = (
        "Generate a structured medicinal chemistry report using ChemLLM (Ollama). "
        "Produces all report sections with citations."
    )
    args_schema: Type[BaseModel] = WriteReportInput

    def _run(self, **kwargs: Any) -> Dict:
        return write_report(WriteReportInput(**kwargs)).model_dump()


# ===========================================================================
# 7. VerifyReportTool
# ===========================================================================

class VerifyReportInput(BaseModel):
    report_sections: Dict[str, str] = Field(..., description="Generated report sections")
    evidence_bundle: Dict[str, Any] = Field(..., description="Evidence bundle for cross-checking")


class VerifyReportOutput(BaseModel):
    verified_sections: Dict[str, str]
    issues_found: List[str]


def verify_report(inp: VerifyReportInput) -> VerifyReportOutput:
    from app.llm.schemas import ReportSections

    client = _chemllm()
    sections = ReportSections(**inp.report_sections)
    verified = client.verify_report(sections, inp.evidence_bundle)

    issues: list[str] = []
    for field, text in verified.model_dump().items():
        if "[UNVERIFIED]" in (text or ""):
            issues.append(f"Unverified claim in section: {field}")

    return VerifyReportOutput(
        verified_sections=verified.model_dump(),
        issues_found=issues,
    )


class VerifyReportTool(BaseTool):  # type: ignore[misc]
    name: str = "VerifyReportTool"
    description: str = (
        "Verify the generated report for consistency: check citations, unit consistency, "
        "and that computational predictions are clearly labeled."
    )
    args_schema: Type[BaseModel] = VerifyReportInput

    def _run(self, **kwargs: Any) -> Dict:
        return verify_report(VerifyReportInput(**kwargs)).model_dump()
