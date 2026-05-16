from __future__ import annotations

"""
Milestone 5 — LoRA fine-tuning for report generation style only.

NOTE:
- Safe fallback if ML stack is missing
- No architectural changes
- Deterministic outputs preserved
"""

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable

MODEL_NAME_DEFAULT = "google/flan-t5-small"
ADAPTER_OUT_DIR = Path("model/output/report_lora_adapter").resolve()


# -----------------------------
# Utility: confidence mapping
# -----------------------------
def _confidence_label(score: float) -> str:
    if score < 0.3:
        return "Low"
    if score < 0.7:
        return "Moderate"
    return "High"


# -----------------------------
# Structured prediction block
# -----------------------------
def _prediction_block(
    title: str,
    score: float,
    interpretation: str,
    decision_insight: str,
) -> Dict[str, Any]:
    return {
        "title": title,
        "predicted_score": float(score),
        "confidence": _confidence_label(float(score)),
        "interpretation": interpretation,
        "decision_insight": decision_insight,
    }


# -----------------------------
# Report formatter (deterministic fallback logic)
# -----------------------------
def format_pharma_grade_report(predictions: Dict[str, Any]) -> Dict[str, Any]:
    report: Dict[str, Any] = {}

    pa = predictions.get("predicted_activity")
    if isinstance(pa, (int, float)):
        score = float(pa)
        conf = _confidence_label(score)

        report["bioactivity"] = _prediction_block(
            "Bioactivity Prediction",
            score,
            "Low/moderate/high bioactivity interpretation generated deterministically.",
            "Screening decision based on model threshold rules.",
        )

    preds = predictions.get("predictions")
    if isinstance(preds, dict):
        if isinstance(preds.get("solubility"), (int, float)):
            s = float(preds["solubility"])
            report["solubility"] = _prediction_block(
                "Solubility Prediction",
                s,
                "Solubility impact assessment based on model output.",
                "Formulation guidance generated deterministically.",
            )

        if isinstance(preds.get("toxicity"), (int, float)):
            t = float(preds["toxicity"])
            report["toxicity"] = _prediction_block(
                "Toxicity Prediction",
                t,
                "Toxicity risk interpretation based on model output.",
                "Safety guidance generated deterministically.",
            )

    report["model"] = "lora_report_writer_v1"
    return report


# -----------------------------
# LoRA output quality gate (invalid → deterministic fallback)
# -----------------------------
def _is_bad_lora_output(text: str) -> bool:
    """Return True if generated text should be rejected (degenerate / JSON leak / too short)."""
    if not isinstance(text, str):
        return True
    t = text.strip()
    if len(t) < 40:
        return True
    # Repeated commas (degenerate lists)
    if ", , ," in t or re.search(r",\s*,\s*,", t):
        return True
    # Repeated JSON-style target fragments
    if t.count('"target"') >= 2 or t.count('"target":') >= 2:
        return True
    if t.count("{") >= 4 and t.count("}") >= 4:
        return True
    # Too many quote characters (likely JSON dump)
    q = t.count('"') + t.count("'")
    if q > max(24, len(t) // 6):
        return True
    # Same 3-word phrase repeated more than 3 times
    words = t.split()
    if len(words) >= 6:
        shingles: list[str] = []
        for i in range(len(words) - 2):
            shingles.append(" ".join(words[i : i + 3]).lower())
        if shingles:
            top = Counter(shingles).most_common(1)[0][1]
            if top > 3:
                return True
    # Target / ChEMBL ID spam (repeated duplication)
    ids = re.findall(r"CHEMBL\d+", t, re.I)
    if len(ids) >= 6 and len(set(ids)) <= 2:
        return True
    if t.lower().count("target") > 12:
        return True
    return False


def _deterministic_lora_fallback(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Structured report when LoRA output is invalid or narrative check fails."""
    from app.services.lora_report_service import (
        _executive_fallback_from_pipeline,
        _format_experiment_list_prose,
        _predictions_misc_to_prose,
        _sanitize_lora_narrative,
    )

    preds = input_data.get("predictions", {})
    ev = input_data.get("evidence_summary", "")
    exp_raw = input_data.get("experiment_list") or []
    exp_list = [e for e in exp_raw if isinstance(e, dict)]
    summary = _sanitize_lora_narrative(
        _executive_fallback_from_pipeline(ev, preds, exp_list)
    )
    pred_prose = _predictions_misc_to_prose(preds)
    nx = _format_experiment_list_prose(exp_list)
    return {
        "summary": summary,
        "interpretation": pred_prose[:1500],
        "risk_assessment": "Risks are not expanded beyond the supplied computational readouts.",
        "conclusion": "Deterministic fallback used after LoRA narrative validation.",
        "model": "lora_report_writer_v1",
        "report_sections": {
            "executive_summary": summary,
            "predictions": pred_prose,
            "next_experiments": nx,
        },
    }


# -----------------------------
# ML dependency guard
# -----------------------------
def _require_ml_stack() -> None:
    try:
        import torch  # noqa
        import transformers  # noqa
        import peft  # noqa
    except Exception as exc:
        raise RuntimeError(
            "LoRA requires torch + transformers + peft installed."
        ) from exc


# -----------------------------
# Dataset iterator
# -----------------------------
def _iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


# -----------------------------
# TRAINING FUNCTION
# -----------------------------
def finetune_report_writer(
    dataset_path: str = "data/training/report_dataset.jsonl",
    model_name: str = MODEL_NAME_DEFAULT,
    output_dir: str = str(ADAPTER_OUT_DIR),
    max_steps: int = 200,
    lr: float = 2e-4,
) -> str:

    ds_path = Path(dataset_path)
    if not ds_path.exists():
        print("⚠️ Dataset missing - skipping LoRA training safely")
        return "SKIPPED_NO_DATASET"

    _require_ml_stack()

    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
    from peft import LoraConfig, TaskType, get_peft_model

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    base_model = AutoModelForSeq2SeqLM.from_pretrained(model_name)

    lora_cfg = LoraConfig(
        r=8,
        lora_alpha=16,
        lora_dropout=0.1,
        target_modules=["q", "v", "q_proj", "v_proj"],
        task_type=TaskType.SEQ_2_SEQ_LM,
    )

    model = get_peft_model(base_model, lora_cfg)
    model.train()

    optimizer = torch.optim.AdamW(model.parameters(), lr=lr)

    steps = 0

    for row in _iter_jsonl(ds_path):
        if steps >= max_steps:
            break

        inp = row.get("input", {})
        out = row.get("output", {}).get("report_sections", {})

        prompt = (
            "Generate scientific report.\n\n"
            f"EVIDENCE: {inp.get('evidence_summary','')}\n"
            f"PREDICTIONS: {json.dumps(inp.get('predictions', {}))}\n"
        )

        target = (
            f"summary: {out.get('summary','')}\n"
            f"interpretation: {out.get('interpretation','')}\n"
            f"risk: {out.get('risk_assessment','')}\n"
            f"conclusion: {out.get('conclusion','')}\n"
        )

        x = tokenizer(prompt, return_tensors="pt", truncation=True)
        y = tokenizer(target, return_tensors="pt", truncation=True)

        loss = model(**x, labels=y["input_ids"]).loss
        loss.backward()

        optimizer.step()
        optimizer.zero_grad(set_to_none=True)

        steps += 1
        print(f"step={steps} loss={loss.item():.4f}")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    model.save_pretrained(out_dir)
    tokenizer.save_pretrained(out_dir)

    print(f"Adapter saved at: {out_dir}")
    return str(out_dir)


# -----------------------------
# INFERENCE (adapter required; invalid narrative → deterministic fallback)
# -----------------------------
def generate_report_with_lora(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """LoRA seq2seq inference; bad or degenerate outputs fall back to deterministic text."""
    adapter_dir = ADAPTER_OUT_DIR

    if not adapter_dir.exists() or not (adapter_dir / "adapter_config.json").exists():
        raise RuntimeError("LoRA adapter missing - training required before inference")

    _require_ml_stack()

    try:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        tok = AutoTokenizer.from_pretrained(str(adapter_dir))
        base = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME_DEFAULT)
        base = base.to("cpu")

        model = PeftModel.from_pretrained(base, str(adapter_dir))
        model.eval()

        prompt = (
            f"EVIDENCE: {input_data.get('evidence_summary', '')}\n"
            f"PREDICTIONS: {json.dumps(input_data.get('predictions', {}))}\n"
        )

        enc = tok(prompt, return_tensors="pt", truncation=True)
        enc = {k: v.to("cpu") for k, v in enc.items()}

        with torch.no_grad():
            out_ids = model.generate(**enc, max_new_tokens=256, do_sample=False, num_beams=1)

        text = tok.decode(out_ids[0], skip_special_tokens=True)

        from app.services.lora_report_service import _sanitize_lora_narrative

        san = _sanitize_lora_narrative(text)
        if _is_bad_lora_output(san):
            raise ValueError("Invalid LoRA narrative")

        return {
            "summary": san,
            "model": "lora_report_writer_v1",
            "report_sections": {
                "executive_summary": san,
            },
        }
    except ValueError as e:
        if "Invalid LoRA narrative" in str(e):
            return _deterministic_lora_fallback(input_data)
        raise
    except Exception as e:
        raise RuntimeError(f"LoRA inference failed: {str(e)}") from e


__all__ = [
    "finetune_report_writer",
    "generate_report_with_lora",
    "format_pharma_grade_report",
    "_is_bad_lora_output",
]

if __name__ == "__main__":
    print("🚀 LoRA training starting...")
    finetune_report_writer()
    print("✅ LoRA training finished.")