"""LoRA-backed medicinal-chemistry narrative (optional runtime; deterministic fallback)."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_LOCK = Lock()
_TOK: Any = None
_MODEL: Any = None
_LOAD_ATTEMPTED = False
_LOAD_OK = False
_STARTUP_PROBE_DONE = False

try:
    from app.training.report_lora_finetune import (
        ADAPTER_OUT_DIR,
        MODEL_NAME_DEFAULT,
        _is_bad_lora_output,
    )
except Exception:  # pragma: no cover
    ADAPTER_OUT_DIR = Path("model/output/report_lora_adapter")
    MODEL_NAME_DEFAULT = "google/flan-t5-small"

    def _is_bad_lora_output(t: str) -> bool:  # type: ignore[misc]
        return len((t or "").strip()) < 40


def _adapter_path() -> Path:
    return Path(ADAPTER_OUT_DIR).resolve()


def _adapter_ready(ap: Path) -> bool:
    return ap.exists() and (ap / "adapter_config.json").exists()


def _require_stack() -> bool:
    try:
        import accelerate  # noqa: F401
        import peft  # noqa: F401
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except Exception:
        return False
    return True


def _infer_mechanism_note(molecule_name: str, targets: list) -> str:
    """
    Lightweight rule-based mechanistic enrichment (no LLM dependency).
    ``targets`` may be target name strings or dicts with a ``target`` key.
    """
    names: list[str] = []
    for t in targets or []:
        if isinstance(t, str) and t.strip():
            names.append(t.strip())
        elif isinstance(t, dict) and str(t.get("target") or "").strip():
            names.append(str(t["target"]).strip())
        elif isinstance(t, (list, tuple)) and len(t) >= 1 and str(t[0]).strip():
            names.append(str(t[0]).strip())
    targets_text = " ".join(names).lower()
    tl = targets_text
    tl = tl.replace("prostaglandin g/h synthase 1", "cox-1")
    tl = tl.replace("prostaglandin g/h synthase 2", "cox-2")
    tl = tl.replace("cyclooxygenase-1", "cox-1").replace("cyclooxygenase-2", "cox-2")
    tl = tl.replace("cyclooxygenase 1", "cox-1").replace("cyclooxygenase 2", "cox-2")
    tl = tl.replace("cox 1", "cox-1").replace("cox 2", "cox-2")
    name = (molecule_name or "").strip() or "This compound"
    has_cox1 = "cox-1" in tl or re.search(r"\bcox[-\s]?1\b", tl) is not None
    has_cox2 = "cox-2" in tl or re.search(r"\bcox[-\s]?2\b", tl) is not None
    if has_cox1 and has_cox2:
        return (
            f"{name} likely acts via cyclooxygenase inhibition "
            "(COX-1/COX-2 pathway modulation), consistent with NSAID pharmacology."
        )
    if has_cox1:
        return (
            f"{name} shows primary COX-1 engagement suggesting prostaglandin pathway inhibition."
        )
    if has_cox2:
        return (
            f"{name} shows primary COX-2 engagement suggesting prostaglandin pathway modulation."
        )
    return (
        f"{name} exhibits multi-target bioactivity with no single dominant mechanism "
        "inferred from annotated targets alone."
    )


# ---------------------------------------------------------------------------
# Post-decode narrative cleanup (plain executive prose; no JSON artifacts)
# ---------------------------------------------------------------------------
def _polish_sentence_flow(text: str) -> str:
    """Normalize spacing, capitalize sentence starts, end sentences, drop duplicates."""
    if not isinstance(text, str) or not text.strip():
        return ""
    t = " ".join(text.split())
    # Strip robotic boilerplate tails the model sometimes echoes
    t = re.sub(
        r"\b(Query compound maps to|ChEMBL entity)\b[^.!?]*$",
        "",
        t,
        flags=re.IGNORECASE,
    ).strip()
    chunks = re.split(r"(?<=[.!?])\s+", t)
    seen: set[str] = set()
    out: list[str] = []
    for ch in chunks:
        s = ch.strip()
        if not s:
            continue
        key = re.sub(r"\s+", " ", s.lower())
        if key in seen:
            continue
        seen.add(key)
        # Capitalize first alphabetic character
        m = re.search(r"[A-Za-z]", s)
        if m:
            i = m.start()
            s = s[:i] + s[i].upper() + s[i + 1 :]
        if len(s) > 12 and s[-1] not in ".!?":
            s += "."
        out.append(s)
    merged = " ".join(out).strip()
    # Remove doubled short phrases ("supported by X. Supported by X.")
    merged = re.sub(r"(\b[\w\s,]{8,40}\b)(\.\s*\1\.)", r"\1.", merged, flags=re.IGNORECASE)
    return " ".join(merged.split()).strip()


def _sanitize_lora_narrative(text: str, *, preserve_newlines: bool = False) -> str:
    """Collapse punctuation noise, strip JSON-like fragments, trim junk tails."""
    if not isinstance(text, str):
        return ""
    if preserve_newlines:
        blocks = [b for b in text.split("\n")]
        cleaned = [
            _sanitize_lora_narrative(b, preserve_newlines=False).strip() for b in blocks
        ]
        return "\n".join(c for c in cleaned if c).strip()
    t = text.replace("\\n", " ").replace("\\t", " ")
    # JSON / field leakage
    t = re.sub(r'"\s*target\s*"\s*:\s*[^,}\]]*', " ", t, flags=re.IGNORECASE)
    t = re.sub(r'"\s*target\s*"', " ", t, flags=re.IGNORECASE)
    t = re.sub(r'"[a-zA-Z0-9_]+"\s*:', " ", t)
    t = re.sub(r"\\+\"", " ", t)
    t = re.sub(r"[\{\}\[\]]", " ", t)
    # Repeated commas / semicolons
    t = re.sub(r",(\s*,)+", ", ", t)
    t = re.sub(r";(\s*;)+", "; ", t)
    t = re.sub(r"\.(\s*\.)+", ". ", t)
    t = re.sub(r"\s+", " ", t).strip()
    # Truncate pathological repetition of the same short token run
    t = re.sub(r"(\b\w{1,4}\b)(\s+\1){4,}", r"\1", t, flags=re.IGNORECASE)
    # Drop dangling incomplete JSON-ish tails
    t = re.sub(r',\s*"[^"]*$', "", t)
    t = re.sub(r":\s*$", "", t)
    t = re.sub(r"^[,\s;:\"'\.]+", "", t)
    return _polish_sentence_flow(" ".join(t.split()).strip())


def _qual_bioactivity(score: float) -> str:
    s = max(0.0, min(1.0, float(score)))
    if s >= 0.68:
        return "support a comparatively strong predicted bioactivity signal for the queried scaffold"
    if s >= 0.42:
        return "point to moderate predicted bioactivity consistent with many primary-screen hits"
    return "suggest a comparatively modest predicted bioactivity readout in this surrogate model"


def _qual_solubility(score: float) -> str:
    s = max(0.0, min(1.0, float(score)))
    if s >= 0.68:
        return "favorable solubility characteristics"
    if s >= 0.4:
        return "intermediate solubility that merits formulation-aware follow-up"
    return "solubility-limited characteristics that may constrain developability unless addressed early"


def _qual_toxicity(score: float) -> str:
    s = max(0.0, min(1.0, float(score)))
    if s >= 0.62:
        return "elevated predicted toxicity signals that warrant orthogonal confirmation beyond the evaluated profile"
    if s >= 0.35:
        return "moderate predicted toxicity within the evaluated surrogate panel"
    return "comparatively restrained predicted toxicity in the evaluated Tox21-style readout"


def _predictions_scores_narrative(
    *,
    bioactivity: Optional[float] = None,
    solubility: Optional[float] = None,
    toxicity: Optional[float] = None,
) -> str:
    """One or two flowing sentences; no 'task: value' phrasing."""
    clauses: list[str] = []
    if bioactivity is not None:
        clauses.append(
            f"Integrated activity models {_qual_bioactivity(bioactivity)}."
        )
    if solubility is not None and toxicity is not None:
        clauses.append(
            f"Model outputs suggest {_qual_solubility(solubility)}, while {_qual_toxicity(toxicity)}."
        )
    elif solubility is not None:
        clauses.append(f"Model outputs suggest {_qual_solubility(solubility)}.")
    elif toxicity is not None:
        clauses.append(
            f"From a safety-readout perspective, {_qual_toxicity(toxicity)}."
        )
    if not clauses:
        return "No quantitative predictions were returned for this request."
    text = " ".join(clauses)
    return _polish_sentence_flow(text)


def _predictions_list_to_prose(predictions: List[Any]) -> str:
    """Medchem-style narrative from structured prediction entries (no 'task: value' phrasing)."""
    bio = sol = tox = None
    extras: list[str] = []
    for p in predictions or []:
        if not isinstance(p, dict):
            continue
        task = str(p.get("task") or p.get("label") or "").strip().lower()
        val = p.get("value")
        if not isinstance(val, (int, float)):
            continue
        v = float(val)
        if "solubil" in task:
            sol = v
        elif "tox" in task:
            tox = v
        elif "activ" in task or "bioactiv" in task or task in ("pa", "predicted activity"):
            bio = v
        else:
            extras.append(
                f"the {task.replace('_', ' ')} readout centers near {v:.2f} in the deployed surrogate"
            )
    text = _predictions_scores_narrative(
        bioactivity=bio, solubility=sol, toxicity=tox
    )
    if extras and text and not text.startswith("No quantitative"):
        tail = " Additional endpoints indicate that " + extras[0] + "."
        text = _polish_sentence_flow(text + tail)
    return text


def _predictions_misc_to_prose(preds: Any) -> str:
    """Orchestrator-style dict (nested predictions) or list of dicts → narrative."""
    if isinstance(preds, list):
        return _predictions_list_to_prose(preds)
    if not isinstance(preds, dict):
        return "No quantitative predictions were returned for this request."
    inner = preds.get("predictions")
    bio = sol = tox = None
    pa = preds.get("predicted_activity")
    if isinstance(pa, (int, float)):
        bio = float(pa)
    if isinstance(inner, dict):
        for key in ("bioactivity", "activity"):
            v = inner.get(key)
            if isinstance(v, (int, float)) and bio is None:
                bio = float(v)
                break
        s = inner.get("solubility")
        if isinstance(s, (int, float)):
            sol = float(s)
        t = inner.get("toxicity")
        if isinstance(t, (int, float)):
            tox = float(t)
    text = _predictions_scores_narrative(bioactivity=bio, solubility=sol, toxicity=tox)
    if not text.startswith("No quantitative"):
        return text
    # Rare path: scalar fields not in expected slots
    parts: list[str] = []
    for k, v in list(preds.items())[:8]:
        if k in ("predictions", "predicted_activity"):
            continue
        if isinstance(v, (int, float)):
            parts.append(
                f"the {k.replace('_', ' ')} surrogate reads near {float(v):.2f}"
            )
    if not parts:
        return "Model outputs did not include numeric scores for this run."
    return _polish_sentence_flow(
        "Computational readouts indicate that " + ", and that ".join(parts) + "."
    )


def _format_experiment_list_prose(experiment_list: List[Dict[str, Any]]) -> str:
    """Readable bullets: assay + target + priority; line breaks (no giant single line)."""
    lines: list[str] = []
    for e in experiment_list or []:
        if not isinstance(e, dict):
            continue
        tgt = str(e.get("target") or "").strip()
        if not tgt:
            continue
        assay = str(e.get("recommended_assay") or "confirmatory potency assay").strip()
        pri = str(e.get("priority") or "medium").strip().lower()
        pri_phrase = {"high": "high", "medium": "medium", "low": "low"}.get(pri, pri)
        assay_uc = assay[0].upper() + assay[1:] if assay else "Potency assay"
        low = assay_uc.lower()
        if low.startswith(("confirmatory", "selectivity", "orthogonal", "prioritize")):
            disp = assay_uc
        else:
            disp = f"Confirmatory {assay_uc[0].lower()}{assay_uc[1:]}"
        lines.append(f"• {disp} on {tgt} ({pri_phrase} priority).")
    if not lines:
        return (
            "• Confirmatory potency on primary hypotheses with standardized nM readouts (high priority).\n"
            "• Orthogonal selectivity and counter-screen assays matched to the target class (medium priority)."
        )
    return "\n".join(lines)


def _merge_next_experiments_section(
    base_text: str,
    experiment_list: List[Dict[str, Any]],
) -> str:
    bullets = _format_experiment_list_prose(experiment_list)
    base = (base_text or "").strip()
    if base and bullets:
        return base + "\n\n" + bullets
    return base or bullets


def _evidence_dict_to_sentences(evidence_summary: Dict[str, Any]) -> list[str]:
    out: list[str] = []
    st = evidence_summary.get("summary_text")
    if isinstance(st, str) and st.strip():
        raw = _sanitize_lora_narrative(st.strip())
        # sanitize already polishes; avoid double-stripping nuance
        raw_inner = raw.replace("\\n", " ")
        for chunk in re.split(r"(?<=[.!?])\s+", raw_inner):
            c = chunk.strip()
            if c:
                out.append(c)
        return out[:4]
    tt = evidence_summary.get("top_targets") or []
    names: list[str] = []
    for x in tt[:4]:
        if isinstance(x, dict) and x.get("target"):
            names.append(str(x["target"]).strip())
        elif isinstance(x, (list, tuple)) and len(x) >= 1:
            names.append(str(x[0]).strip())
    total = evidence_summary.get("total_activities")
    if names:
        line = (
            f"Bioactivity concentrates on well-annotated targets including {', '.join(names)}, "
            "consistent with a mature public data footprint for this chemotype class."
        )
        if total is not None:
            line += (
                f" Potency trends should be read in the context of {int(total)} supporting "
                "activity records in this retrieval slice."
            )
        out.append(line)
    else:
        out.append(
            "Target-level evidence is sparse in the current retrieval window; "
            "confirm structure and broaden the evidence query before committing to SAR claims."
        )
    return out[:4]


def _executive_identity_lead(name: str, chembl: str, ev_sents: list[str]) -> str:
    """Natural opening line — avoid robotic 'Query compound maps' phrasing."""
    if ev_sents:
        first = ev_sents[0].strip()
        if name and name.lower() not in first.lower():
            return (
                f"{name} demonstrates substantial ChEMBL-backed target annotation relevant to this review. "
                f"{first}"
            )
        return first
    if name:
        return (
            f"{name} demonstrates substantial historical target engagement supported by ChEMBL bioactivity records"
            + (f" ({chembl})" if chembl else "")
            + "."
        )
    if chembl:
        return (
            f"The resolved structure aligns to ChEMBL {chembl}, supporting a conservative, target-centric medchem synopsis."
        )
    return "Compound identity is partially specified; confirm structure before interpreting SAR."


def _deterministic_executive_narrative(
    molecule_data: Dict[str, Any],
    evidence_summary: Dict[str, Any],
    predictions: List[Any],
    report_sections: Dict[str, Any],
    similar_compounds: Optional[List[Dict[str, Any]]] = None,
    experiment_list: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Two to four sentences: identity, evidence, predictions — narrative medchem voice."""
    name = str(molecule_data.get("pref_name") or molecule_data.get("name") or "").strip()
    chembl = str(molecule_data.get("chembl_id") or "").strip()

    ev_sents = _evidence_dict_to_sentences(evidence_summary)
    s0 = _executive_identity_lead(name, chembl, ev_sents)
    ev_block = " ".join(ev_sents[1:3]).strip()

    pred_line = _predictions_list_to_prose(predictions)
    pred_short = pred_line
    if len(pred_short) > 420:
        pred_short = pred_short[:417].rsplit(" ", 1)[0] + "…"

    sim = similar_compounds or []
    sim_note = ""
    if sim and isinstance(sim[0], dict):
        cid = sim[0].get("chembl_id", "n/a")
        tan = float(sim[0].get("tanimoto", 0) or 0)
        sim_note = (
            f" Close analogs include ChEMBL {cid} at Tanimoto similarity {tan:.2f}, useful for SAR context."
        )

    parts = [s0, ev_block, pred_short + sim_note]
    text = " ".join(p for p in parts if p).strip()
    text = _sanitize_lora_narrative(text)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if len(sentences) > 4:
        text = " ".join(sentences[:4])
    else:
        text = " ".join(sentences) if sentences else text
    if experiment_list:
        first = experiment_list[0]
        if isinstance(first, dict) and str(first.get("target") or "").strip():
            tgt = str(first["target"]).strip()
            hint = f" A practical next step is prioritized confirmatory profiling on {tgt}."
            if len(text) + len(hint) < 1050:
                text = (text + hint).strip()
    return _polish_sentence_flow(text) or s0


def _executive_fallback_from_pipeline(
    evidence_summary: Any,
    predictions: Any,
    experiment_list: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Fallback executive text when LoRA output is invalid (string or dict evidence)."""
    sents: list[str] = []
    if isinstance(evidence_summary, dict):
        sents = _evidence_dict_to_sentences(evidence_summary)
    elif isinstance(evidence_summary, str) and evidence_summary.strip():
        raw = evidence_summary.strip()
        sents = [c.strip() for c in re.split(r"(?<=[.!?])\s+", raw) if c.strip()][:4]
        sents = [_sanitize_lora_narrative(s) for s in sents if s]
    if not sents:
        sents = [
            "Evidence is thin in this slice; confirm structure and broaden retrieval before firm SAR commitments."
        ]
    pred_p = _predictions_misc_to_prose(predictions)
    if len(pred_p) > 380:
        pred_p = pred_p[:377].rsplit(" ", 1)[0] + "…"
    body = " ".join(sents[:3]) + " " + pred_p
    body = _sanitize_lora_narrative(body)
    sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+", body) if x.strip()]
    merged = " ".join(sentences[:4]).strip() or sents[0]
    return _polish_sentence_flow(merged)


def log_lora_startup_status() -> None:
    """
    Optional startup probe: never raises. Logs availability of LoRA stack vs deterministic fallback.
    """
    global _STARTUP_PROBE_DONE
    if _STARTUP_PROBE_DONE:
        return
    _STARTUP_PROBE_DONE = True
    try:
        ap = _adapter_path()
        if not _require_stack():
            logger.warning("LoRA unavailable; deterministic report fallback active")
            return
        logger.info("LoRA runtime dependencies available")
        if not _adapter_ready(ap):
            logger.warning("LoRA adapter not found; using deterministic report fallback")
            return
        logger.info("LoRA adapter loaded")
    except Exception as exc:  # pragma: no cover
        logger.warning("LoRA startup probe failed: %s", exc)


def _load_if_needed_locked() -> tuple[Optional[Any], Optional[Any]]:
    """Must be called with ``_LOCK`` held. Returns (tokenizer, model) or (None, None)."""
    global _TOK, _MODEL, _LOAD_ATTEMPTED, _LOAD_OK
    if _LOAD_OK and _TOK is not None and _MODEL is not None:
        return _TOK, _MODEL
    if _LOAD_ATTEMPTED and not _LOAD_OK:
        return None, None
    _LOAD_ATTEMPTED = True
    ap = _adapter_path()
    if not _adapter_ready(ap):
        logger.warning("LoRA adapter not found; using deterministic report fallback")
        return None, None
    if not _require_stack():
        logger.warning("LoRA unavailable; deterministic report fallback active")
        return None, None
    try:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        torch.manual_seed(42)
        tok = AutoTokenizer.from_pretrained(str(ap))
        base = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME_DEFAULT)
        base = base.to("cpu")
        model = PeftModel.from_pretrained(base, str(ap))
        model.eval()
        _TOK = tok
        _MODEL = model
        _LOAD_OK = True
        return _TOK, _MODEL
    except Exception as exc:
        logger.warning("LoRA load failed — fallback to deterministic report: %s", exc)
        _LOAD_OK = False
        _TOK = None
        _MODEL = None
        return None, None


def _build_prompt(
    molecule_data: Dict[str, Any],
    evidence_summary: Dict[str, Any],
    predictions: List[Any],
    report_sections: Dict[str, Any],
    similar_compounds: Optional[List[Dict[str, Any]]],
) -> str:
    sim = similar_compounds or []
    # Narrative-only hints to the model: avoid echoing huge JSON blobs in the output.
    ev_compact = {
        "summary_text": evidence_summary.get("summary_text"),
        "total_activities": evidence_summary.get("total_activities"),
        "top_target_names": [
            (x.get("target") if isinstance(x, dict) else (x[0] if isinstance(x, (list, tuple)) else None))
            for x in (evidence_summary.get("top_targets") or [])[:6]
        ],
    }
    pred_hint = _predictions_list_to_prose(predictions)[:1200]
    rs_hint = {
        k: report_sections.get(k)
        for k in ("executive_summary", "chembl_evidence", "next_experiments")
        if report_sections.get(k)
    }
    return (
        "You are a senior medicinal chemist. Write ONE cohesive professional narrative "
        "for a discovery report. Use ONLY the facts below. Do not invent ChEMBL IDs, "
        "assay values, mechanisms, or literature citations. If data are sparse, say so.\n\n"
        f"MOLECULE: {json.dumps(molecule_data, ensure_ascii=False)[:2500]}\n\n"
        f"EVIDENCE_SUMMARY (compact): {json.dumps(ev_compact, ensure_ascii=False)[:4000]}\n\n"
        f"PREDICTIONS (plain): {pred_hint}\n\n"
        f"SIMILAR_COMPOUNDS (count {len(sim)}): "
        f"{json.dumps(sim[:12], ensure_ascii=False)[:4000]}\n\n"
        f"PIPELINE_DRAFT (compact): {json.dumps(rs_hint, ensure_ascii=False)[:3000]}\n\n"
        "Output plain text only (no JSON, no field names like target, no comma lists of tokens). "
        "Integrate identity, key targets, potency evidence where present, predictions, "
        "similarity context, and suggested next steps in full sentences."
    )


def generate_lora_report(
    molecule_data: Dict[str, Any],
    evidence_summary: Dict[str, Any],
    predictions: List[Any],
    report_sections: Dict[str, Any],
    similar_compounds: Optional[List[Dict[str, Any]]] = None,
    experiment_list: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Generate a medicinal-chemistry narrative from existing pipeline outputs.

    Returns deterministic executive prose if LoRA is unavailable, inference fails,
    or decoded text fails quality validation.
    """
    exp_list: List[Dict[str, Any]] = [e for e in (experiment_list or []) if isinstance(e, dict)]

    def _fallback() -> str:
        return _deterministic_executive_narrative(
            molecule_data,
            evidence_summary,
            predictions,
            report_sections,
            similar_compounds=similar_compounds,
            experiment_list=exp_list,
        )

    with _LOCK:
        tok, model = _load_if_needed_locked()
        if tok is None or model is None:
            return _fallback()

        prompt = _build_prompt(
            molecule_data,
            evidence_summary,
            predictions,
            report_sections,
            similar_compounds,
        )

        try:
            import torch

            enc = tok(prompt, return_tensors="pt", truncation=True, max_length=1024)
            enc = {k: v.to("cpu") for k, v in enc.items()}
            with torch.no_grad():
                out_ids = model.generate(
                    **enc,
                    max_new_tokens=384,
                    do_sample=False,
                    num_beams=1,
                )
            text = tok.decode(out_ids[0], skip_special_tokens=True).strip()
        except Exception as exc:
            logger.warning("LoRA inference failed — fallback to deterministic report: %s", exc)
            return _fallback()

    if not text:
        logger.warning("LoRA decode empty — fallback to deterministic report")
        return _fallback()

    sanitized = _sanitize_lora_narrative(text)
    if _is_bad_lora_output(sanitized):
        logger.warning("LoRA narrative failed validation — deterministic executive fallback")
        return _fallback()
    return sanitized


__all__ = ["generate_lora_report", "log_lora_startup_status"]
