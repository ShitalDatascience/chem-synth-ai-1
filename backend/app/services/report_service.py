from __future__ import annotations

"""Report service: assembles OrchestratorResult into a ReportJSON document."""

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from app.llm.schemas import (
    EvidenceSummary,
    MoleculeSection,
    PredictionEntry,
    ReportJSON,
    ReportSections,
    SimilarCompound,
)
from app.schemas.final_report import FinalReport, FinalReportMetadata
from app.services.rag_orchestrator import OrchestratorResult, finalize_molecule_for_response

# ---------------------------------------------------------------------------
# In-memory report store (replace with Postgres table for persistence)
# ---------------------------------------------------------------------------

_report_store: dict[str, ReportJSON] = {}


def save_report(report: ReportJSON) -> None:
    _report_store[report.report_id] = report


def get_report(report_id: str) -> Optional[ReportJSON]:
    return _report_store.get(report_id)


def list_report_ids() -> list[str]:
    return list(_report_store.keys())


def _compute_evidence_confidence(evidence_summary: Dict[str, Any]) -> str:
    """
    Converts raw assay counts + potency stats into a simple confidence label.
    No schema change, only narrative enrichment.
    """
    raw = evidence_summary.get("total_activities")
    try:
        total = int(raw) if raw is not None else 0
    except (TypeError, ValueError):
        total = 0
    if total > 3000:
        return "High confidence (extensive bioactivity coverage)"
    if total > 1000:
        return "Moderate confidence (substantial assay evidence)"
    return "Low confidence (limited assay coverage)"


def _format_sar_context(similar_compounds: List[Dict[str, Any]]) -> str:
    """
    Converts similarity list into research-readable SAR sentence.
    """
    if not similar_compounds:
        return ""
    top = similar_compounds[:2]
    sar_parts: list[str] = []
    for c in top:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("chembl_id") or "").strip()
        if not cid:
            continue
        try:
            tan = float(c.get("tanimoto", 0) or 0)
        except (TypeError, ValueError):
            tan = 0.0
        sar_parts.append(f"{cid} (Tanimoto {tan:.2f})")
    if not sar_parts:
        return ""
    return (
        "Structure-activity context includes close analogs such as "
        + " and ".join(sar_parts)
        + ", supporting scaffold-level comparison."
    )


def _normalize_cox_labels(text: str) -> str:
    """
    Normalize COX casing artifacts from LLM/post-processing.
    """
    if not text:
        return text

    replacements = {
        "cOX-1": "COX-1",
        "cox-1": "COX-1",
        "cOX-2": "COX-2",
        "cox-2": "COX-2",
        "COX1": "COX-1",
        "COX2": "COX-2",
    }

    for k, v in replacements.items():
        text = text.replace(k, v)

    return text


def _fix_sentence_boundaries(text: str) -> str:
    if not text:
        return text

    # fix double periods
    text = re.sub(r"\.\.+", ".", text)

    # fix missing space after period
    text = re.sub(r"\.(?=[A-Z])", ". ", text)

    # normalize multiple spaces
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def assemble_report(result: OrchestratorResult) -> ReportJSON:
    report_id = result.report_id or str(uuid.uuid4())
    now = datetime.now(tz=timezone.utc).isoformat()

    finalize_molecule_for_response(result)

    # Molecule section (mw/logp already set on dict — not recomputed in Pydantic)
    mol_dict = result.molecule or {}
    mw_val = mol_dict.get("mw_freebase")
    if mw_val is None:
        mw_val = mol_dict.get("mw")
    logp_val = mol_dict.get("alogp")
    if logp_val is None:
        logp_val = mol_dict.get("logp")

    molecule = MoleculeSection(
        chembl_id=mol_dict.get("chembl_id"),
        pref_name=mol_dict.get("pref_name"),
        canonical_smiles=mol_dict.get("canonical_smiles"),
        inchi_key=mol_dict.get("standard_inchi_key"),
        mw=mw_val,
        logp=logp_val,
        tpsa=mol_dict.get("psa"),
        hba=mol_dict.get("hba"),
        hbd=mol_dict.get("hbd"),
        rot_bonds=mol_dict.get("rtb"),
        formula=mol_dict.get("full_molformula"),
    )

    # Similar compounds
    similar_compounds = [
        SimilarCompound(
            chembl_id=h.get("chembl_id", ""),
            tanimoto=h.get("tanimoto", 0.0),
            canonical_smiles=h.get("smiles"),
            headline_activity=None,
        )
        for h in result.similar_hits[:20]
    ]

    # Evidence summary from orchestrator (prefer aggregated; fallback to evidence_summary)
    agg = result.aggregated or result.evidence_summary or {}
    raw_tt = agg.get("top_targets", [])
    top_targets_norm: list[dict] = []
    for x in raw_tt:
        if isinstance(x, dict):
            top_targets_norm.append(x)
        elif isinstance(x, (list, tuple)) and len(x) >= 2:
            top_targets_norm.append({"target": x[0], "count": int(x[1])})
    total_activities = agg.get("total_activities")
    if total_activities is None:
        logger.warning("assemble_report: total_activities missing from aggregated dict")
    logger.info(
        "assemble_report: total_activities=%s top_targets_size=%s activity_types_keys=%s",
        total_activities,
        len(top_targets_norm),
        len(agg.get("activity_types") or {}),
    )
    cl_act = agg.get("cell_line_activity")
    if not isinstance(cl_act, list):
        cl_act = []

    evidence_summary = EvidenceSummary(
        top_targets=top_targets_norm,
        potency_stats_by_target=agg.get("potency_stats_by_target", []) or [],
        assay_counts=agg.get("assay_counts", {}) or {},
        total_activities=total_activities,
        cell_line_activity=[dict(x) for x in cl_act if isinstance(x, dict)],
        summary_text=agg.get("summary_text") if isinstance(agg.get("summary_text"), str) else None,
        target_clusters=agg.get("target_clusters", []) or [],
    )

    raw_sug = agg.get("experiment_suggestions") or []
    experiment_list: list[dict] = []
    if isinstance(raw_sug, list):
        for x in raw_sug[:5]:
            if isinstance(x, dict) and x.get("target"):
                experiment_list.append(
                    {
                        "target": str(x.get("target")),
                        "recommended_assay": str(x.get("recommended_assay") or ""),
                        "priority": str(x.get("priority") or "medium"),
                    }
                )

    # Predictions
    predictions = [
        PredictionEntry(
            task=p.get("task", ""),
            label=p.get("label", "Predicted"),
            value=p.get("value"),
            probability=p.get("probability"),
            uncertainty=p.get("uncertainty"),
            unit=p.get("unit"),
            model_name=p.get("model_name", ""),
            training_dataset=p.get("training_dataset", ""),
        )
        for p in result.predictions
    ]

    # Report sections
    rs_dict = result.report_sections or {}
    report_sections = ReportSections(**{k: v for k, v in rs_dict.items() if v is not None})

    report = ReportJSON(
        report_id=report_id,
        created_at=now,
        query=result.query,
        molecule=molecule,
        similar_compounds=similar_compounds,
        evidence_summary=evidence_summary,
        experiment_list=experiment_list,
        predictions=predictions,
        report_sections=report_sections,
    )
    save_report(report)
    return report


def build_final_report(report: ReportJSON) -> FinalReport:
    """Map stored ``ReportJSON`` → locked ``FinalReport`` contract (chem-rag-v2)."""
    from app.services.lora_report_service import (
        _deterministic_executive_narrative,
        _format_experiment_list_prose,
        _infer_mechanism_note,
        _merge_next_experiments_section,
        _predictions_list_to_prose,
        _sanitize_lora_narrative,
        generate_lora_report,
    )

    mol = report.molecule
    base_sections = report.report_sections.model_dump()
    exp_rows = [dict(e) for e in (report.experiment_list or [])]

    narrative = generate_lora_report(
        molecule_data=mol.model_dump() if mol else {},
        evidence_summary=report.evidence_summary.model_dump(),
        predictions=[p.model_dump() for p in report.predictions],
        report_sections=dict(base_sections),
        similar_compounds=[s.model_dump() for s in report.similar_compounds[:25]],
        experiment_list=exp_rows,
    )

    merged_sections = dict(base_sections)
    nar = narrative.strip()
    if nar:
        merged_sections["executive_summary"] = nar

    from app.training.report_lora_finetune import _is_bad_lora_output

    ex = _sanitize_lora_narrative(str(merged_sections.get("executive_summary") or ""))
    if _is_bad_lora_output(ex):
        ex = _deterministic_executive_narrative(
            mol.model_dump() if mol else {},
            report.evidence_summary.model_dump(),
            [p.model_dump() for p in report.predictions],
            dict(base_sections),
            similar_compounds=[s.model_dump() for s in report.similar_compounds[:25]],
            experiment_list=exp_rows,
        )
    ev_dump = report.evidence_summary.model_dump()
    mechanism_note = _infer_mechanism_note(
        (mol.pref_name or "The compound") if mol else "The compound",
        ev_dump.get("top_targets", []),
    )
    sar_note = _format_sar_context(
        [s.model_dump() for s in report.similar_compounds[:25]]
    )

    base_exec = _sanitize_lora_narrative(ex or "").strip()
    base_exec = _normalize_cox_labels(base_exec)
    base_exec = _fix_sentence_boundaries(base_exec)

    mechanism_note = _fix_sentence_boundaries(
        _normalize_cox_labels(mechanism_note or "")
    )
    sar_note = _fix_sentence_boundaries(_normalize_cox_labels(sar_note or ""))

    executive_parts = [base_exec]
    if mechanism_note:
        executive_parts.append(mechanism_note)
    if sar_note:
        executive_parts.append(sar_note)
    executive_summary = " ".join([p for p in executive_parts if p]).strip()
    merged_sections["executive_summary"] = executive_summary

    ce_raw = str(merged_sections.get("chembl_evidence") or "").strip()
    conf_note = _compute_evidence_confidence(ev_dump)
    if ce_raw:
        chembl_evidence = f"{ce_raw}. {conf_note}"
    else:
        chembl_evidence = conf_note
    chembl_evidence = _sanitize_lora_narrative(chembl_evidence)
    chembl_evidence = _normalize_cox_labels(chembl_evidence)
    merged_sections["chembl_evidence"] = chembl_evidence
    merged_sections["predictions"] = _predictions_list_to_prose(
        [p.model_dump() for p in report.predictions]
    )
    next_exp = _merge_next_experiments_section(
        str(merged_sections.get("next_experiments") or "").strip(),
        exp_rows,
    )
    if next_exp and next_exp.strip():
        merged_sections["next_experiments"] = _normalize_cox_labels(
            _sanitize_lora_narrative(next_exp, preserve_newlines=True)
        )
    else:
        merged_sections["next_experiments"] = _normalize_cox_labels(
            _format_experiment_list_prose(exp_rows)
        )

    return FinalReport(
        query=report.query,
        molecule=mol.model_dump() if mol else {},
        similar_compounds=[s.model_dump() for s in report.similar_compounds],
        evidence_summary=report.evidence_summary.model_dump(),
        experiment_list=[dict(e) for e in (report.experiment_list or [])],
        predictions=[p.model_dump() for p in report.predictions],
        report_sections=merged_sections,
        metadata=FinalReportMetadata(),
    )
