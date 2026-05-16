from __future__ import annotations

import json
import logging
import re
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.llm.schemas import (
    InputType,
    IntentType,
    NormalizedRequest,
    ToolName,
    ToolPlan,
)
from app.schemas.final_report import FinalReport, FinalReportMetadata

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_SIMILARITY_TANIMOTO_MIN = 0.2
_SIMILARITY_OUTPUT_CAP = 10

# Phase 2 caches (in-memory, keyed by InChIKey)
_SIM_CACHE: dict[str, list[dict[str, Any]]] = {}
_EVID_CACHE: dict[str, dict[str, Any]] = {}
_PRED_CACHE: dict[str, list[dict[str, Any]]] = {}

# Intent tokens removed for molecule resolution only (full query kept in result.query).
_RESOLUTION_INTENT_TOKENS = (
    "IC50",
    "Ki",
    "EC50",
    "assay",
    "COX-1",
    "COX-2",
    "inhibition",
    "activity",
)


def _strip_resolution_intent(raw: str) -> str:
    """Strip bioactivity / assay intent tokens; used only for NormalizationService.resolve."""
    s = (raw or "").strip()
    if not s:
        return ""
    for tok in sorted(_RESOLUTION_INTENT_TOKENS, key=len, reverse=True):
        s = re.sub(re.escape(tok), " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _resolution_input_query(raw_query: str) -> str:
    """Prefer cleaned string for resolution when it differs from the user query."""
    raw_q = (raw_query or "").strip()
    cleaned = _strip_resolution_intent(raw_q)
    if cleaned and cleaned.lower() != raw_q.lower():
        return cleaned
    return raw_q


def _chembl_fallback_by_name(chembl: Any, candidates: List[str]) -> Optional[Dict[str, Any]]:
    """Retry resolution via existing ChemblService.search_by_name when chembl_id is still null."""
    seen: set[str] = set()
    for cand in candidates:
        c = (cand or "").strip()
        if len(c) < 2:
            continue
        key = c.lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            rows = chembl.search_by_name(c, limit=10)
        except Exception:
            logger.exception("[PIPELINE] search_by_name failed for %r", c)
            continue
        for row in rows or []:
            cid = row.get("chembl_id")
            if not cid:
                continue
            full = chembl.get_by_chembl_id(cid)
            if full and full.get("canonical_smiles"):
                return full
    return None


def _coerce_int(val: Any) -> Optional[int]:
    if val is None:
        return None
    if isinstance(val, bool):
        return int(val)
    if isinstance(val, int):
        return val
    if isinstance(val, Decimal):
        return int(val)
    try:
        return int(val)
    except (TypeError, ValueError):
        try:
            return int(Decimal(str(val)))
        except Exception:
            return None


def _format_evidence_bundle_from_sql(bundle: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize get_evidence_bundle.sql JSON for API (typing only; no re-aggregation)."""
    out: Dict[str, Any] = {
        "total_activities": bundle.get("total_activities"),
        "top_targets": [],
        "activity_types": {},
        "assay_counts": {},
        "potency_stats_by_target": [],
        "target_clusters": [],
    }
    ta = _coerce_int(out["total_activities"])
    out["total_activities"] = ta

    tt = bundle.get("top_targets")
    if isinstance(tt, str):
        try:
            tt = json.loads(tt)
        except json.JSONDecodeError:
            tt = []
    if isinstance(tt, list):
        for x in tt:
            if not isinstance(x, dict):
                continue
            tgt = x.get("target")
            cnt = _coerce_int(x.get("count"))
            if tgt is None or cnt is None:
                continue
            out["top_targets"].append({"target": str(tgt), "count": cnt})

    at = bundle.get("activity_types")
    if isinstance(at, str):
        try:
            at = json.loads(at)
        except json.JSONDecodeError:
            at = {}
    if isinstance(at, dict):
        for k, v in at.items():
            iv = _coerce_int(v)
            if iv is not None:
                out["activity_types"][str(k)] = iv

    ac = bundle.get("assay_counts")
    if isinstance(ac, str):
        try:
            ac = json.loads(ac)
        except json.JSONDecodeError:
            ac = {}
    if isinstance(ac, dict):
        for k, v in ac.items():
            iv = _coerce_int(v)
            if iv is not None:
                out["assay_counts"][str(k)] = iv

    tc = bundle.get("target_clusters")
    if isinstance(tc, str):
        try:
            tc = json.loads(tc)
        except json.JSONDecodeError:
            tc = []
    if isinstance(tc, list):
        out["target_clusters"] = tc

    ps = bundle.get("potency_stats_by_target")
    if isinstance(ps, str):
        try:
            ps = json.loads(ps)
        except json.JSONDecodeError:
            ps = []
    if isinstance(ps, list):
        out["potency_stats_by_target"] = ps
    return out


# =====================================================
# SAFE NORMALIZER
# =====================================================
def normalize_request(query: str) -> NormalizedRequest:
    return NormalizedRequest(
        raw_query=query,
        input_type=InputType.name,
        value=query,
        tool_plan=ToolPlan(intents=[IntentType.lookup], tool_sequence=[]),
    )


# =====================================================
# RESULT MODEL
# =====================================================
class OrchestratorResult(BaseModel):
    query: str
    normalized: NormalizedRequest
    molecule: Optional[Dict[str, Any]] = None
    similar_hits: List[Dict[str, Any]] = []
    evidence_rows: List[Dict[str, Any]] = []
    evidence_summary: Optional[Dict[str, Any]] = None
    predictions: List[Dict[str, Any]] = []
    aggregated: Optional[Dict[str, Any]] = None
    report_sections: Optional[Dict[str, Any]] = None
    deepchem_raw: Optional[Dict[str, Any]] = None
    report_id: Optional[str] = None
    errors: List[str] = []


# =====================================================
# REQUIRED BY REPORT SERVICE
# =====================================================
def finalize_molecule_for_response(result: OrchestratorResult) -> None:
    try:
        mol = result.molecule or {}
        smi = mol.get("canonical_smiles") or result.normalized.value
        if smi:
            mol["canonical_smiles"] = smi
        result.molecule = mol
    except Exception as e:
        logger.warning(f"finalize failed: {e}")


# =====================================================
# MAIN PIPELINE (🔥 UPDATED WITH RDKit PHYS-CHEM)
# =====================================================
def run_pipeline_raw(query: str) -> OrchestratorResult:
    result = OrchestratorResult(
        query=query,
        normalized=normalize_request(query),
    )

    # Phase 3: deterministic execution order (always runs)
    logger.info("[PIPELINE] tool_order=ResolveMolecule→SimilaritySearch→FetchChemblEvidence→AggregateEvidence→WriteReport")

    try:
        from app.services.chembl_service import ChemblService
        from app.services.normalization_service import NormalizationService
        from app.services import rdkit_service

        chembl = ChemblService()
        raw_q = (query or "").strip()
        resolve_input = _resolution_input_query(query)

        norm = NormalizationService.resolve(resolve_input)
        if norm.get("canonical_smiles"):
            result.normalized.canonical_smiles = norm["canonical_smiles"]
        if norm.get("chembl_id"):
            result.normalized.chembl_id = str(norm["chembl_id"]).upper()

        if result.normalized.canonical_smiles:
            v = rdkit_service.validate_smiles(result.normalized.canonical_smiles)
            result.normalized.inchi_key = v.inchi_key
            if not result.normalized.chembl_id and v.inchi_key:
                try:
                    m2 = chembl.get_molecule_by_inchi_key(v.inchi_key)
                    if m2 and m2.get("chembl_id"):
                        result.normalized.chembl_id = str(m2["chembl_id"]).upper()
                except Exception:
                    logger.exception("[PIPELINE] ChEMBL inchi_key lookup failed")
            result.molecule = {
                "canonical_smiles": v.canonical_smiles,
                "name": norm.get("name") or resolve_input or raw_q,
                "mw": v.mw,
                "logp": v.logp,
                "tpsa": v.tpsa,
                "hba": v.hba,
                "hbd": v.hbd,
            }
            if result.normalized.chembl_id:
                result.molecule["chembl_id"] = result.normalized.chembl_id
        else:
            result.molecule = {"name": norm.get("name") or resolve_input or raw_q}

        # PLAN: if chembl_id still null, retry with existing search_by_name (no new service).
        if not result.normalized.chembl_id:
            fb = _chembl_fallback_by_name(
                chembl,
                [
                    resolve_input,
                    raw_q,
                    resolve_input.split()[0] if resolve_input.split() else "",
                    raw_q.split()[0] if raw_q.split() else "",
                ],
            )
            if fb and fb.get("canonical_smiles"):
                result.normalized.chembl_id = str(fb["chembl_id"]).upper()
                result.normalized.canonical_smiles = fb.get("canonical_smiles")
                v = rdkit_service.validate_smiles(result.normalized.canonical_smiles)
                result.normalized.inchi_key = v.inchi_key
                result.molecule = {
                    "canonical_smiles": v.canonical_smiles,
                    "name": fb.get("pref_name") or norm.get("name") or resolve_input or raw_q,
                    "mw": v.mw,
                    "logp": v.logp,
                    "tpsa": v.tpsa,
                    "hba": v.hba,
                    "hbd": v.hbd,
                    "chembl_id": result.normalized.chembl_id,
                }

        mol_r = result.molecule or {}
        has_smi = bool(mol_r.get("canonical_smiles") or result.normalized.canonical_smiles)
        has_cid = bool(result.normalized.chembl_id or mol_r.get("chembl_id"))
        if not has_smi and not has_cid:
            result.errors.append("Could not resolve molecule (no ChEMBL ID and no structure)")
        elif not has_smi:
            result.errors.append("Could not resolve molecule")
    except Exception as e:
        logger.exception("[PIPELINE] resolve failed")
        result.errors.append(f"resolve_error: {e}")

    # -------------------------------------------------
    # SAFE PIPELINE STEPS (plan.md: evidence/sim/predict/report)
    # -------------------------------------------------
    result = _step_similarity(result)
    result = _step_evidence(result)
    result = _step_predict(result)
    result = _step_aggregate(result)
    result = _step_report(result)

    # REQUIRED
    finalize_molecule_for_response(result)

    result.report_id = str(uuid.uuid4())

    return result


def _step_evidence(result: OrchestratorResult) -> OrchestratorResult:
    try:
        from app.services.chembl_service import ChemblService

        chembl = ChemblService()

        cid = (result.normalized.chembl_id or (result.molecule or {}).get("chembl_id") or "").strip()
        if not cid:
            logger.info("[EVIDENCE] gated: no chembl_id — skipping ChEMBL enrichment")
            result.evidence_rows = []
            result.evidence_summary = {
                "total_activities": 0,
                "top_targets": [],
                "activity_types": {},
            }
            return result

        key = result.normalized.inchi_key
        if key and key in _EVID_CACHE:
            cached = _EVID_CACHE[key]
            if not isinstance(cached, dict):
                del _EVID_CACHE[key]
            else:
                result.evidence_rows = list(cached.get("rows") or [])
                result.evidence_summary = dict(cached.get("bundle") or {})
                es = result.evidence_summary or {}
                logger.info(
                    "[EVIDENCE] cache hit rows=%s bundle_total_activities=%s top_targets_n=%s",
                    len(result.evidence_rows),
                    es.get("total_activities"),
                    len(es.get("top_targets") or []),
                )
                return result

        mol_row = chembl.get_by_chembl_id(cid)
        molregno = (mol_row or {}).get("molregno")
        if molregno is None:
            result.evidence_summary = {
                "total_activities": 0,
                "top_targets": [],
                "activity_types": {},
            }
            result.evidence_rows = []
            result.errors.append("evidence_error: missing molregno for chembl_id")
            return result

        molregno_int = int(molregno)
        logger.info("[EVIDENCE] resolved molregno=%s chembl_id=%s", molregno_int, cid)

        raw_bundle = chembl.fetch_evidence_bundle_aggregates(molregno_int)
        result.evidence_summary = _format_evidence_bundle_from_sql(raw_bundle)
        if result.molecule is not None:
            result.molecule["molregno"] = molregno_int

        evidence = chembl.fetch_evidence_by_chembl_id(cid, limit=5000, molregno=molregno_int)

        def _to_nm(value: Any, unit: Any) -> Optional[float]:
            if value is None:
                return None
            try:
                v = float(value)
            except Exception:
                return None
            if v <= 0:
                return None
            u = str(unit or "").strip().lower()
            if not u:
                return None
            if u == "nm":
                out = v
            elif u in ("um", "µm"):
                out = v * 1000.0
            elif u == "mm":
                out = v * 1_000_000.0
            else:
                return None
            if out > 1_000_000_000.0:
                return None
            return out

        cleaned: list[dict[str, Any]] = []
        seen: set[tuple[Any, Any, Any, Any]] = set()
        for r in evidence or []:
            row = dict(r)
            st = (row.get("standard_type") or "").upper()
            if st in {"IC50", "KI", "EC50"}:
                nm = _to_nm(row.get("standard_value"), row.get("standard_units"))
                if nm is not None:
                    row["value_nm"] = float(nm)
            else:
                # keep non-potency rows unchanged
                pass

            dedupe_key = (
                row.get("chembl_id"),
                row.get("assay_id") or row.get("assay_chembl_id"),
                row.get("standard_type"),
                row.get("standard_value"),
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            cleaned.append(row)

        result.evidence_rows = cleaned
        es = result.evidence_summary or {}
        logger.info(
            "[EVIDENCE] molregno=%s detail_rows=%s bundle_total_activities=%s top_targets_n=%s",
            molregno_int,
            len(cleaned),
            es.get("total_activities"),
            len(es.get("top_targets") or []),
        )
        if key:
            _EVID_CACHE[key] = {
                "rows": list(cleaned),
                "bundle": dict(result.evidence_summary or {}),
            }

    except Exception as e:
        logger.error(f"[EVIDENCE ERROR] {e}")
        result.evidence_rows = []
        result.evidence_summary = {
            "total_activities": 0,
            "top_targets": [],
            "activity_types": {},
        }
        result.errors.append(f"evidence_error: {str(e)}")

    return result


def _step_similarity(result: OrchestratorResult) -> OrchestratorResult:
    try:
        from app.services.milvus_service import MilvusService
        from app.services import rdkit_service

        mol = result.molecule or {}
        smiles = (mol.get("canonical_smiles") or result.normalized.canonical_smiles or "").strip()
        cid = (mol.get("chembl_id") or result.normalized.chembl_id or "").strip()
        if not smiles and not cid:
            logger.info("[SIMILARITY] gated: no structure and no chembl_id — skipping vector search")
            return result
        if not smiles:
            logger.info("[SIMILARITY] gated: no valid SMILES for query compound — skipping vector search")
            return result
        try:
            rdkit_service.validate_smiles(smiles)
        except Exception:
            logger.info("[SIMILARITY] gated: SMILES validation failed — skipping vector search")
            return result

        key = result.normalized.inchi_key
        if key and key in _SIM_CACHE:
            result.similar_hits = list(_SIM_CACHE[key])
            return result

        milvus = MilvusService()
        milvus.ensure_collection()
        stats = milvus.get_collection_stats()
        if not stats.get("exists") or int(stats.get("count", 0)) == 0:
            result.similar_hits = []
            return result

        reranked = milvus.search_with_rdkit_rerank(smiles, top_k_coarse=200)
        q_can = rdkit_service.canonicalize_smiles(smiles)

        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for h in reranked or []:
            hit_cid = str(h.chembl_id or "").strip()
            if not hit_cid or hit_cid in seen:
                continue
            seen.add(hit_cid)
            smi = (h.smiles or "").strip()
            if not smi:
                continue
            if "." in smi:
                continue
            try:
                smi_can = rdkit_service.canonicalize_smiles(smi)
            except Exception:
                smi_can = smi
            if smi_can == q_can:
                continue
            tani = float(h.tanimoto or 0.0)
            if tani < _SIMILARITY_TANIMOTO_MIN:
                continue
            out.append(
                {
                    "chembl_id": hit_cid,
                    "smiles": smi_can,
                    "tanimoto": round(tani, 3),
                    "milvus_score": float(h.milvus_score),
                }
            )

        # Deterministic ordering (tanimoto desc, chembl_id asc).
        out.sort(key=lambda x: (-float(x.get("tanimoto", 0.0) or 0.0), str(x.get("chembl_id") or "")))

        # Diversity: prefer one compound per Murcko scaffold when possible.
        diverse: list[dict[str, Any]] = []
        seen_scaffolds: set[str] = set()
        try:
            from rdkit import Chem
            from rdkit.Chem.Scaffolds import MurckoScaffold

            for hit in out:
                smi_can = str(hit.get("smiles") or "").strip()
                if not smi_can:
                    continue
                mol = Chem.MolFromSmiles(smi_can)
                if mol is None:
                    continue
                scaf = MurckoScaffold.MurckoScaffoldSmiles(mol=mol) or ""
                if scaf and scaf in seen_scaffolds:
                    continue
                if scaf:
                    seen_scaffolds.add(scaf)
                diverse.append(hit)
                if len(diverse) >= _SIMILARITY_OUTPUT_CAP:
                    break
        except Exception:
            diverse = []

        if diverse:
            out = diverse
        out = out[:_SIMILARITY_OUTPUT_CAP]
        result.similar_hits = out
        if key:
            _SIM_CACHE[key] = list(out)

    except Exception as e:
        logger.error(f"[SIMILARITY ERROR] {e}")
        result.similar_hits = []
        result.errors.append(f"similarity_error: {str(e)}")

    return result


def _step_predict(result: OrchestratorResult) -> OrchestratorResult:
    try:
        mol = result.molecule or {}
        smi = (mol.get("canonical_smiles") or result.normalized.canonical_smiles or "").strip()
        if not smi:
            result.predictions = []
            return result

        key = result.normalized.inchi_key
        if key and key in _PRED_CACHE:
            result.predictions = list(_PRED_CACHE[key])
            return result

        preds: list[dict[str, Any]] = []
        try:
            from app.services.deepchem.deepchem_predict_tool import DeepChemPredictTool

            tool = DeepChemPredictTool()
            raw = tool.predict(smi)
            inner = raw.get("predictions") if isinstance(raw, dict) else None
            meta = raw.get("model_metadata") if isinstance(raw, dict) else None
            if isinstance(inner, dict):
                sol = inner.get("solubility")
                tox = inner.get("toxicity")
                if sol is not None:
                    preds.append(
                        {
                            "task": "solubility",
                            "label": "Predicted",
                            "value": float(sol),
                            "unit": None,
                            "model_name": (meta or {}).get("solubility_model", {}).get("model_name", ""),
                            "training_dataset": (meta or {}).get("solubility_model", {}).get("training_dataset", ""),
                        }
                    )
                if tox is not None:
                    preds.append(
                        {
                            "task": "toxicity",
                            "label": "Predicted",
                            "value": float(tox),
                            "unit": None,
                            "model_name": (meta or {}).get("toxicity_model", {}).get("model_name", ""),
                            "training_dataset": (meta or {}).get("toxicity_model", {}).get("training_dataset", ""),
                        }
                    )
        except Exception as e:
            # No DeepChem available; keep empty to preserve separation.
            result.errors.append(f"predict_unavailable: {e}")
            preds = []

        result.predictions = preds
        if key:
            _PRED_CACHE[key] = list(preds)

    except Exception as e:
        logger.error(f"[PREDICTION ERROR] {e}")
        result.predictions = []
        result.errors.append(f"prediction_error: {str(e)}")

    return result


def _step_aggregate(result: OrchestratorResult) -> OrchestratorResult:
    base = dict(result.evidence_summary or {})
    if not base:
        base = {"total_activities": 0, "top_targets": [], "activity_types": {}}
    merged = {
        "total_activities": base.get("total_activities"),
        "top_targets": base.get("top_targets") or [],
        "activity_types": base.get("activity_types") or {},
        "assay_counts": base.get("assay_counts") or {},
        "potency_stats_by_target": base.get("potency_stats_by_target") or [],
        "target_clusters": base.get("target_clusters") or [],
    }
    try:
        from app.services.rag.aggregate_evidence import refine_evidence_bundle

        mol = result.molecule or {}
        compound_label = (mol.get("pref_name") or mol.get("name") or "").strip() or None
        result.aggregated = refine_evidence_bundle(
            merged, result.evidence_rows or [], compound_label=compound_label
        )
    except Exception as e:
        logger.warning("[AGGREGATE] refine_evidence_bundle skipped: %s", e)
        result.aggregated = merged
    return result


def _step_report(result: OrchestratorResult) -> OrchestratorResult:
    try:
        mol = result.molecule or {}
        agg = result.aggregated or {}
        tt = agg.get("top_targets") or []
        tt_names = []
        for x in tt[:5]:
            if isinstance(x, dict):
                nm = x.get("target")
                if nm:
                    tt_names.append(str(nm))
            elif isinstance(x, (list, tuple)) and len(x) >= 1:
                nm = x[0]
                if nm:
                    tt_names.append(str(nm))
        tt_str = ", ".join(tt_names)

        ta = agg.get("total_activities")
        if ta is None:
            logger.warning("[REPORT] total_activities missing from aggregated evidence summary")
            ta_display = "?"
        else:
            ta_display = str(int(ta))

        # Contextual evidence summary (no LLM; deterministic template).
        enz = None
        for c in (agg.get("target_clusters") or []):
            if isinstance(c, dict) and c.get("cluster") == "enzyme":
                enz = c
                break
        enz_names: list[str] = []
        if isinstance(enz, dict):
            for x in (enz.get("top_targets") or [])[:3]:
                if isinstance(x, dict) and x.get("target"):
                    enz_names.append(str(x["target"]))
        enz_str = ", ".join(enz_names)

        assay_counts = agg.get("assay_counts") or {}

        pot = agg.get("potency_stats_by_target") or []
        pot_n = len(pot) if isinstance(pot, list) else 0

        summary_text = agg.get("summary_text")
        if isinstance(summary_text, str) and summary_text.strip():
            evidence_line = summary_text.strip()
        elif enz_str:
            evidence_line = f"{ta_display} activity record(s); key enzyme targets: {enz_str}."
        else:
            evidence_line = f"{ta_display} activity record(s); top targets: {tt_str}."

        next_exp = "Prioritize in-vitro potency (IC50/Ki/EC50) confirmation on COX-1/COX-2 and orthogonal selectivity assays."
        if pot_n:
            next_exp = (
                f"Validate potency trends (n={pot_n} summarized target/type group(s)) with "
                "standardized nM endpoints on COX targets and human-relevant assays."
            )

        name = mol.get("name")
        smi_disp = (mol.get("canonical_smiles") or "").strip()
        if name is None and not smi_disp:
            executive_summary = "Unknown molecule (ambiguous query)"
        elif smi_disp:
            executive_summary = f"Molecule resolved: {smi_disp}"
        elif name:
            executive_summary = f"Molecule resolved: {name}"
        else:
            executive_summary = "Unknown molecule (ambiguous query)"

        result.report_sections = {
            "executive_summary": executive_summary,
            "molecular_identity": mol.get("name", ""),
            "physchem": f"MW: {mol.get('mw')} | LogP: {mol.get('logp')}",
            "chembl_evidence": evidence_line,
            "predictions": ", ".join(
                f"{p.get('task')}={p.get('value')}"
                for p in (result.predictions or [])
                if isinstance(p, dict)
            ),
            "risks": "Not evaluated",
            "next_experiments": next_exp,
            "citations": "ChEMBL",
            "disclaimer": "For research use only",
        }

    except Exception as e:
        logger.error(f"[REPORT ERROR] {e}")
        mol_f = result.molecule or {}
        name_f = mol_f.get("name")
        smi_f = (mol_f.get("canonical_smiles") or "").strip()
        if name_f is None and not smi_f:
            exec_fallback = "Unknown molecule (ambiguous query)"
        elif smi_f:
            exec_fallback = f"Molecule resolved: {smi_f}"
        elif name_f:
            exec_fallback = f"Molecule resolved: {name_f}"
        else:
            exec_fallback = "Unknown molecule (ambiguous query)"
        result.report_sections = {
            "executive_summary": exec_fallback,
            "molecular_identity": str(mol_f.get("name") or ""),
            "physchem": "",
            "chembl_evidence": "",
            "predictions": "",
            "risks": "Not evaluated",
            "next_experiments": "",
            "citations": "ChEMBL",
            "disclaimer": "For research use only",
        }

    return result


# =====================================================
# FINAL API ENTRY
# =====================================================
def run_pipeline(query: str) -> FinalReport:
    from app.services.report_service import assemble_report, build_final_report

    raw = run_pipeline_raw(query)
    report = assemble_report(raw)
    return build_final_report(report)


# =====================================================
# EXPORTS
# =====================================================
__all__ = [
    "run_pipeline",
    "run_pipeline_raw",
    "finalize_molecule_for_response",
    "OrchestratorResult",
]