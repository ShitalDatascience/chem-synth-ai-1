"""Evidence aggregation: target clustering (IC50 in nM) and confidence-weighted summaries."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from statistics import median
from typing import Any, Dict, List, Optional, Tuple

_NM_MAX_SANE = 1_000_000_000.0

_GENERIC_TARGET_NAMES: frozenset[str] = frozenset(
    {
        "homo sapiens",
        "rattus norvegicus",
        "mus musculus",
        "plasma",
        "blood",
        "brain",
        "platelet",
        "hepatotoxicity",
        "molecular identity unknown",
        "serum",
        "liver",
        "kidney",
        "heart",
        "lung",
        "skin",
        "spleen",
        "urine",
        "adipocyte",
        "human",
        "mouse",
        "rat",
        "unchecked",
        "no relevant target",
        "non-protein target",
        "admet",
    }
)

_CELL_LINE_RE = re.compile(
    r"(cell\s*line|atcc\b|derived\s+from\b|"
    r"\bNCI-[Hh]?\d+|\bRPMI[- ]?\d+|\bHT[- ]?\d+\b|\bSK[- ]?BR[- ]?3\b|\bSK[- ]?OV[- ]?3\b|"
    r"\bPC[- ]?3\b|\bHCT[- ]?116\b|\bU[- ]?87(?:MG)?\b|\bK[- ]?562\b|"
    r"\bHEK[- ]?293(?:T|A)?\b|\bCHO[- ]?K1\b|\bTHP[- ]?1\b|\bA549\b|\bMCF[- ]?7\b|"
    r"\bMDA[- ]?MB[- ]?\d+\b|\bSW[- ]?480\b|\bCO\s*LO\s*205\b|\bGI[- ]?\d+\b)",
    re.I,
)

_PHARM_CLASS_RE = re.compile(
    r"\b(kinase|receptor|channel|transporter|oxidase|synthase|protease|phosphatase|"
    r"dehydrogenase|hydrolase|reductase|ligase|isomerase|peptidase)\b",
    re.I,
)

_WS_COLLAPSE = re.compile(r"\s+")
_COX2_TOKEN = re.compile(r"\b(ptgs2|ptgs\s*2|pghs[-\s]?2|cox[-\s]?2|cox2)\b", re.I)
_COX1_TOKEN = re.compile(r"\b(ptgs1|ptgs\s*1|pghs[-\s]?1|cox[-\s]?1|cox1)\b", re.I)


def _collapse_ws(s: str) -> str:
    return _WS_COLLAPSE.sub(" ", (s or "").strip())


def canonical_target_label(pref_name: Optional[str]) -> str:
    """Merge synonymous enzyme/protein labels; COX isoforms collapse to exactly COX-1 / COX-2."""
    if not pref_name or not str(pref_name).strip():
        return ""
    raw = _collapse_ws(str(pref_name))
    if not raw:
        return ""
    low = raw.lower()
    # COX-2 before COX-1 (isoform 2 is a substring risk in rare names).
    if _COX2_TOKEN.search(raw):
        return "COX-2"
    if (
        "prostaglandin g/h synthase 2" in low
        or "prostaglandin-endoperoxide synthase 2" in low
        or "prostaglandin g/h synthase ii" in low
    ):
        return "COX-2"
    if "prostaglandin" in low and "synthase" in low and re.search(r"\bsynthase\s+2\b", low):
        return "COX-2"
    if "cyclooxygenase-2" in low or "cyclooxygenase 2" in low:
        return "COX-2"

    if _COX1_TOKEN.search(raw):
        return "COX-1"
    if "prostaglandin g/h synthase 1" in low or "prostaglandin-endoperoxide synthase 1" in low:
        return "COX-1"
    if "prostaglandin g/h synthase i" in low and "ii" not in low:
        return "COX-1"
    if "prostaglandin" in low and "synthase" in low and re.search(r"\bsynthase\s+1\b", low):
        return "COX-1"
    if "cyclooxygenase-1" in low or "cyclooxygenase 1" in low:
        return "COX-1"

    if "cyclooxygenase" in low and "prostaglandin" not in low:
        if re.search(r"(?:^|[\s(-])2(?:\b|[\s).,-])", raw):
            return "COX-2"
        return "COX-1"
    return raw


def is_generic_low_info_target(pref_name: Optional[str]) -> bool:
    t = (pref_name or "").strip().lower()
    if not t:
        return True
    if t in _GENERIC_TARGET_NAMES:
        return True
    if "molecular identity unknown" in t:
        return True
    if t.endswith(" toxicity") or t.endswith("toxicity"):
        return True
    return False


def is_cell_line_target(pref_name: Optional[str]) -> bool:
    if not pref_name or not str(pref_name).strip():
        return False
    s = str(pref_name).strip()
    if _CELL_LINE_RE.search(s):
        return True
    up = s.upper().replace(" ", "")
    if re.match(r"^[A-Z]{2,6}-\d{2,4}[A-Z]?$", up):
        return True
    return False


def _row_value_nm(row: Dict[str, Any]) -> Optional[float]:
    if row.get("value_nm") is not None:
        try:
            v = float(row["value_nm"])
        except (TypeError, ValueError):
            v = None
        else:
            if 0 < v <= _NM_MAX_SANE:
                return v
            return None
    from app.core.processing.evidence_normalizer import EvidenceNormalizer

    v = EvidenceNormalizer.to_nanomolar(row.get("standard_value"), str(row.get("standard_units") or ""))
    if v is None or not math.isfinite(float(v)) or float(v) <= 0 or float(v) > _NM_MAX_SANE:
        return None
    return float(v)


def _iqr_keep(values: List[float], iqr_factor: float = 1.0) -> List[float]:
    vals = sorted(float(x) for x in values if x is not None and math.isfinite(float(x)))
    n = len(vals)
    if n <= 3:
        return vals
    mid = n // 2
    lower = vals[:mid] if mid else vals
    upper = vals[mid:] if mid else vals
    q1 = float(median(lower))
    q3 = float(median(upper))
    iqr = q3 - q1
    if iqr <= 0:
        return vals
    lo = q1 - iqr_factor * iqr
    hi = q3 + iqr_factor * iqr
    kept = [x for x in vals if lo <= x <= hi]
    return kept if kept else vals


def _percentile_trim(values: List[float], low: float = 0.08, high: float = 0.92) -> List[float]:
    vals = sorted(float(x) for x in values if x is not None and math.isfinite(float(x)))
    if len(vals) <= 8:
        return vals
    lo_i = int(len(vals) * low)
    hi_i = max(lo_i + 1, min(len(vals) - 1, int(len(vals) * high)))
    return vals[lo_i : hi_i + 1]


_POTENCY_MIN_RAW = 4
_POTENCY_MIN_AFTER_TRIM = 3
_NM_DISPLAY_CAP = 1_000_000.0


def robust_potency_min_median_max(values: List[float]) -> Optional[Dict[str, Any]]:
    v0 = [float(x) for x in values if x is not None and 0 < float(x) <= _NM_MAX_SANE and math.isfinite(float(x))]
    if len(v0) < _POTENCY_MIN_RAW:
        return None
    trimmed = _iqr_keep(v0, iqr_factor=1.0)
    if len(trimmed) < _POTENCY_MIN_AFTER_TRIM:
        return None
    if len(trimmed) >= 10:
        trimmed = _percentile_trim(trimmed, 0.08, 0.92)
    if len(trimmed) < _POTENCY_MIN_AFTER_TRIM:
        return None
    med = float(median(trimmed))
    lo_v = float(min(trimmed))
    hi_raw = float(max(trimmed))
    mid = len(trimmed) // 2
    if mid < 1:
        q1, q3 = lo_v, hi_raw
    else:
        q1 = float(median(trimmed[:mid]))
        q3 = float(median(trimmed[mid:]))
    iqr = max(q3 - q1, 1e-9)
    winsor_hi = q3 + 2.0 * iqr
    spread_cap = min(_NM_DISPLAY_CAP, max(1e4, med * 400.0))
    max_v = min(hi_raw, winsor_hi, spread_cap)
    return {
        "median_value": med,
        "min_value": lo_v,
        "max_value": max_v,
        "sample_size": len(trimmed),
    }


def _species_like_target_name(low: str) -> bool:
    """Latin binomial–style names without obvious protein pharmacology tokens."""
    if _PHARM_CLASS_RE.search(low) or "cox" in low:
        return False
    return bool(re.match(r"^[a-z][a-z-]+\s+[a-z][a-z-]+$", low)) and len(low) < 48


def _protein_target_tier(name: str, cnt: int, human_n: int) -> int:
    """
    Sort tier: 1 = best (human + pharmacology), 5 = weakest.
    Order intent: human proteins > pharmacology class > partial human > species-like > remainder.
    """
    if cnt <= 0:
        return 5
    hf = float(human_n) / float(cnt)
    low = name.lower()
    pharma = bool(_PHARM_CLASS_RE.search(low)) or name in ("COX-1", "COX-2")
    if hf >= 0.35 and pharma:
        return 1
    if pharma:
        return 2
    if hf >= 0.5:
        return 3
    if hf > 0:
        return 3
    if _species_like_target_name(low):
        return 4
    return 5


def _merge_top_target_entries(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    acc: dict[str, int] = defaultdict(int)
    for it in items or []:
        if not isinstance(it, dict):
            continue
        raw = str(it.get("target") or "").strip()
        if not raw:
            continue
        k = canonical_target_label(raw) or raw
        acc[k] += int(it.get("count") or 0)
    return [{"target": t, "count": int(n)} for t, n in sorted(acc.items(), key=lambda x: (-x[1], x[0]))]


def _dedupe_target_clusters(clusters: Any) -> Any:
    if clusters is None:
        return []
    if not isinstance(clusters, list):
        return clusters
    out: List[Any] = []
    for c in clusters:
        if not isinstance(c, dict):
            out.append(c)
            continue
        c2 = dict(c)
        tt = c2.get("top_targets")
        if isinstance(tt, list):
            merged: dict[str, int] = defaultdict(int)
            for x in tt:
                if not isinstance(x, dict):
                    continue
                raw = str(x.get("target") or "").strip()
                if not raw:
                    continue
                k = canonical_target_label(raw) or raw
                merged[k] += int(x.get("count") or 0)
            c2["top_targets"] = [
                {"target": t, "count": int(n)}
                for t, n in sorted(merged.items(), key=lambda x: (-x[1], x[0]))[:10]
            ]
        out.append(c2)
    return out


def suggest_experiments_from_targets(targets: List[str], limit: int = 5) -> List[Dict[str, Any]]:
    """Backward-compatible thin wrapper (count order only)."""
    return suggest_experiments_evidence_aware(
        [{"target": t, "count": 1} for t in (targets or []) if t],
        [],
        {},
        [],
        limit=limit,
    )


def suggest_experiments_evidence_aware(
    top_targets: List[Dict[str, Any]],
    potency_stats: List[Dict[str, Any]],
    activity_types: Dict[str, Any],
    evidence_rows: List[Dict[str, Any]],
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Evidence-aware suggestions: strongest potencies, dominant endpoints, high-confidence enzyme rows."""
    out: List[Dict[str, Any]] = []

    def _best_type_for_target(tgt: str) -> str:
        st_scores: dict[str, int] = defaultdict(int)
        for r in evidence_rows or []:
            raw_pref = str(r.get("target_pref_name") or "").strip()
            if not raw_pref:
                continue
            c = canonical_target_label(raw_pref) or raw_pref
            if c != tgt:
                continue
            st = (r.get("standard_type") or "").strip().upper()
            if st in {"IC50", "KI", "EC50"}:
                st_scores[st] += 1
        if not st_scores:
            return "IC50"
        return max(st_scores.items(), key=lambda kv: kv[1])[0]

    def _max_conf_for_target(tgt: str) -> int:
        m = 0
        for r in evidence_rows or []:
            raw_pref = str(r.get("target_pref_name") or "").strip()
            if not raw_pref:
                continue
            c = canonical_target_label(raw_pref) or raw_pref
            if c != tgt:
                continue
            try:
                m = max(m, int(r.get("confidence_score") or 0))
            except (TypeError, ValueError):
                continue
        return m

    ranked_types = sorted(
        (activity_types or {}).items(),
        key=lambda kv: (-int(kv[1] or 0), str(kv[0])),
    )
    dom_st = str(ranked_types[0][0]).upper() if ranked_types else "IC50"

    cands: List[tuple[float, int, str]] = []
    seen: set[str] = set()
    for p in potency_stats or []:
        if not isinstance(p, dict):
            continue
        t = str(p.get("target") or "").strip()
        if not t or t in seen:
            continue
        try:
            med = float(p.get("median_value"))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(med) or med <= 0:
            continue
        seen.add(t)
        cands.append((med, _max_conf_for_target(t), t))
    cands.sort(key=lambda x: (x[0], -x[1], x[2]))

    for _, conf, tgt in cands:
        if len(out) >= limit:
            break
        low = tgt.lower()
        stt = _best_type_for_target(tgt)
        prio = "high" if conf >= 8 or low in ("cox-1", "cox-2") else "medium"
        if low == "cox-1":
            rec = "COX-1 enzymatic IC50 assay (arachidonic acid / PGH2 pathway)"
        elif low == "cox-2":
            rec = "COX-2 selectivity profiling vs COX-1 under matched assay conditions"
        elif "kinase" in low or "phosphatase" in low:
            rec = f"{stt} biochemical kinase/phosphatase assay with orthogonal ATP-site probe"
        elif "receptor" in low:
            rec = "Competitive radioligand binding plus functional readout where available"
        elif stt == "EC50":
            rec = "Follow-up EC50 validation in a disease-relevant human cellular model"
        elif dom_st in {"IC50", "KI", "EC50"}:
            rec = f"{dom_st}-driven potency confirmation on {tgt} with replicate curves"
        else:
            rec = f"Quantitative {stt or 'IC50'} assay on {tgt} with standardized nM readout"
        out.append({"target": tgt, "recommended_assay": rec, "priority": prio})

    for it in top_targets or []:
        if len(out) >= limit:
            break
        if not isinstance(it, dict):
            continue
        tgt = str(it.get("target") or "").strip()
        if not tgt or any(e.get("target") == tgt for e in out):
            continue
        low = tgt.lower()
        cnt = int(it.get("count") or 0)
        if low in ("cox-1", "cox-2"):
            prio = "high" if cnt >= 4 else "medium"
        else:
            prio = "low" if cnt < 5 else "medium"
        if low == "cox-1":
            rec = "COX-1 enzymatic IC50 assay"
        elif low == "cox-2":
            rec = "COX-2 selectivity profiling"
        elif "receptor" in low:
            rec = "Human recombinant receptor binding / signaling assay"
        else:
            rec = f"Primary {dom_st} potency assay on {tgt} with assay confidence ≥7 where possible"
        out.append({"target": tgt, "recommended_assay": rec, "priority": prio})

    if len(out) < limit and ranked_types:
        if not any("viability" in (e.get("recommended_assay") or "").lower() for e in out):
            hc = sum(
                1
                for r in evidence_rows or []
                if str((r.get("target_organism") or "")).strip().lower() == "homo sapiens"
            )
            if hc >= 20:
                out.append(
                    {
                        "target": "Human cellular context",
                        "recommended_assay": "Human cell viability / proliferation assay with reference cytotoxic control",
                        "priority": "medium",
                    }
                )

    return out[:limit]


def build_evidence_summary_text(
    total_activities: Optional[int],
    top_targets: List[Dict[str, Any]],
    assay_counts: Dict[str, Any],
    potency_stats: List[Dict[str, Any]],
    activity_types: Optional[Dict[str, Any]] = None,
    compound_label: Optional[str] = None,
) -> str:
    names = [
        str(x.get("target"))
        for x in (top_targets or [])[:4]
        if isinstance(x, dict) and x.get("target")
    ]
    lead = ", ".join(names) if names else "no high-confidence protein target after QC"
    ac = assay_counts or {}
    top_assays = sorted(ac.items(), key=lambda kv: (-int(kv[1] or 0), str(kv[0])))[:3]
    assay_part = (
        ", ".join(f"{k} ({v})" for k, v in top_assays)
        if top_assays
        else "mixed assay modalities in ChEMBL source rows"
    )
    at = activity_types or {}
    top_endpoints = sorted(at.items(), key=lambda kv: (-int(kv[1] or 0), str(kv[0])))[:3]
    end_part = (
        ", ".join(f"{k} ({v})" for k, v in top_endpoints)
        if top_endpoints
        else "mixed standard types"
    )
    pot = [p for p in (potency_stats or []) if isinstance(p, dict)]
    ta = int(total_activities or 0)
    pot_bits: List[str] = []
    if pot:
        for p in pot[:3]:
            t = str(p.get("target") or "")
            st = str(p.get("activity_type") or "")
            try:
                m = float(p.get("median_value"))
                m_txt = f"{m:.3g}" if m >= 0.001 else f"{m:.2e}"
            except (TypeError, ValueError):
                m_txt = "n/a"
            pot_bits.append(f"{t} {st} median ≈ {m_txt} nM (trimmed cohort n={p.get('sample_size')})")
        pot_sentence = "Potency evidence: " + "; ".join(pot_bits) + "."
    else:
        pot_sentence = "Sparse reproducible nM potency cohorts after strict QC (need more IC50/Ki/EC50 rows)."

    if compound_label and names:
        opener = (
            f"{compound_label} shows the strongest consolidated signals on {lead} "
            f"({ta} supporting ChEMBL activity row(s))."
        )
    elif compound_label:
        opener = f"{compound_label} has {ta} ChEMBL activity row(s); target attribution is thin after QC."
    else:
        opener = f"{ta} ChEMBL activity row(s); strongest consolidated targets are {lead}."

    return (
        f"{opener} Dominant assay classes: {assay_part}. "
        f"Most frequent standard types: {end_part}. {pot_sentence}"
    )


def refine_evidence_bundle(
    base: Dict[str, Any],
    evidence_rows: List[Dict[str, Any]],
    compound_label: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Refine SQL-backed evidence aggregates using detail rows: target QC, cell-line split,
    canonicalization, robust potency, and narrative summary (same response shape).
    """
    out = dict(base or {})
    rows = list(evidence_rows or [])
    atypes = out.get("activity_types") or {}
    if not rows:
        out.setdefault("cell_line_activity", [])
        tt_fb = _merge_top_target_entries(out.get("top_targets") or [])
        out["target_clusters"] = _dedupe_target_clusters(out.get("target_clusters"))
        out["experiment_suggestions"] = suggest_experiments_evidence_aware(
            tt_fb,
            out.get("potency_stats_by_target") or [],
            atypes,
            [],
            limit=5,
        )
        if not out.get("summary_text"):
            out["summary_text"] = build_evidence_summary_text(
                out.get("total_activities"),
                tt_fb,
                out.get("assay_counts") or {},
                out.get("potency_stats_by_target") or [],
                activity_types=atypes,
                compound_label=compound_label,
            )
        return out

    protein_counts: dict[str, int] = defaultdict(int)
    cell_counts: dict[str, int] = defaultdict(int)
    human_hits: dict[str, int] = defaultdict(int)

    for row in rows:
        raw_name = row.get("target_pref_name")
        if raw_name is None:
            continue
        raw_s = str(raw_name).strip()
        if not raw_s:
            continue
        if is_generic_low_info_target(raw_s):
            continue
        if is_cell_line_target(raw_s):
            cell_counts[raw_s] += 1
            continue
        canon = canonical_target_label(raw_s) or raw_s
        protein_counts[canon] += 1
        org = (row.get("target_organism") or "").strip().lower()
        if org == "homo sapiens":
            human_hits[canon] += 1

    total_per_target = {k: protein_counts[k] for k in protein_counts}

    scored: List[tuple[int, int, int, str]] = []
    for tgt, cnt in total_per_target.items():
        hn = int(human_hits.get(tgt, 0))
        tier = _protein_target_tier(tgt, cnt, hn)
        if len(tgt) > 100:
            tier = min(5, tier + 1)
        scored.append((tier, cnt, hn, tgt))
    scored.sort(key=lambda x: (x[0], -x[1], -(x[2] / max(x[1], 1)), x[3]))

    top_targets = [{"target": t, "count": int(c)} for _, c, _, t in scored[:12]]
    top_targets = _merge_top_target_entries(top_targets)
    top_targets.sort(
        key=lambda d: (
            _protein_target_tier(
                str(d.get("target") or ""),
                int(d.get("count") or 0),
                int(human_hits.get(str(d.get("target") or ""), 0)),
            ),
            -int(d.get("count") or 0),
            str(d.get("target") or ""),
        )
    )
    top_targets = top_targets[:10]

    if not top_targets:
        merged_fb: dict[str, int] = defaultdict(int)
        for item in out.get("top_targets") or []:
            if not isinstance(item, dict):
                continue
            raw_s = str(item.get("target") or "").strip()
            if not raw_s or is_generic_low_info_target(raw_s) or is_cell_line_target(raw_s):
                continue
            canon = canonical_target_label(raw_s) or raw_s
            cnt = int(item.get("count") or 0)
            if cnt > 0:
                merged_fb[canon] += cnt
        top_targets = [
            {"target": t, "count": int(n)}
            for t, n in sorted(merged_fb.items(), key=lambda x: (-x[1], x[0]))[:12]
        ]
        top_targets = _merge_top_target_entries(top_targets)
        top_targets.sort(
            key=lambda d: (
                _protein_target_tier(
                    str(d.get("target") or ""),
                    int(d.get("count") or 0),
                    int(human_hits.get(str(d.get("target") or ""), 0)),
                ),
                -int(d.get("count") or 0),
                str(d.get("target") or ""),
            )
        )
        top_targets = top_targets[:10]

    cell_line_activity = [
        {"target": t, "count": int(n)}
        for t, n in sorted(cell_counts.items(), key=lambda x: (-x[1], x[0]))[:15]
    ]

    potency_allowed = {"IC50", "KI", "EC50"}
    pot_groups: dict[tuple[str, str], List[float]] = defaultdict(list)
    for row in rows:
        raw_name = row.get("target_pref_name")
        if raw_name is None:
            continue
        raw_s = str(raw_name).strip()
        if is_generic_low_info_target(raw_s) or is_cell_line_target(raw_s):
            continue
        st = (row.get("standard_type") or "").strip().upper()
        if st not in potency_allowed:
            continue
        nm = _row_value_nm(row)
        if nm is None:
            continue
        tgt = canonical_target_label(raw_s) or raw_s
        pot_groups[(tgt, st)].append(nm)

    potency_stats_by_target: List[Dict[str, Any]] = []
    for (tgt, st), vals in pot_groups.items():
        agg = robust_potency_min_median_max(vals)
        if not agg:
            continue
        potency_stats_by_target.append(
            {
                "target": tgt,
                "activity_type": st,
                "median_value": agg["median_value"],
                "min_value": agg["min_value"],
                "max_value": agg["max_value"],
                "unit": "nM",
                "sample_size": int(agg["sample_size"]),
            }
        )
    potency_stats_by_target.sort(key=lambda x: (-int(x.get("sample_size") or 0), str(x.get("target")), str(x.get("activity_type"))))
    potency_stats_by_target = potency_stats_by_target[:25]

    out["top_targets"] = top_targets
    out["cell_line_activity"] = cell_line_activity
    out["potency_stats_by_target"] = potency_stats_by_target
    out["target_clusters"] = _dedupe_target_clusters(out.get("target_clusters"))
    out["summary_text"] = build_evidence_summary_text(
        out.get("total_activities"),
        top_targets,
        out.get("assay_counts") or {},
        potency_stats_by_target,
        activity_types=atypes,
        compound_label=compound_label,
    )
    out["experiment_suggestions"] = suggest_experiments_evidence_aware(
        top_targets,
        potency_stats_by_target,
        atypes,
        rows,
        limit=5,
    )
    return out


def normalize_ic50_to_nM(value: float, unit: str) -> float:
    """
    Convert all potency values to nM.
    STRICT conversion only (plan.md compliant).
    """

    if value is None:
        return None

    unit = (unit or "").lower()

    if unit == "nm":
        return float(value)

    if unit == "um" or unit == "µm":
        return float(value) * 1000

    if unit == "mm":
        return float(value) * 1_000_000

    # fallback: assume already nM
    return float(value)


def potency_stats_by_target_from_experiments(experiment_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from collections import defaultdict

    target_map = defaultdict(list)

    for exp in experiment_list or []:
        target = exp.get("target_pref_name")
        value = exp.get("standard_value")
        unit = exp.get("standard_units")

        if not target or value is None:
            continue

        try:
            ic50_nm = normalize_ic50_to_nM(float(value), str(unit or ""))
        except (TypeError, ValueError):
            continue

        target_map[target].append(ic50_nm)

    potency_stats_by_target = []

    for target, values in target_map.items():
        if not values:
            continue
        vals = [float(x) for x in values if x is not None and 0 < float(x) <= _NM_MAX_SANE]
        if not vals:
            continue
        agg = robust_potency_min_median_max(vals)
        if not agg:
            continue
        potency_stats_by_target.append(
            {
                "target": target,
                "min_ic50_nM": agg["min_value"],
                "median_ic50_nM": agg["median_value"],
                "assay_count": int(agg["sample_size"]),
            }
        )

    return potency_stats_by_target


def _ic50_row_value_nM(row: Dict[str, Any]) -> Tuple[Optional[float], int]:
    """Return (value_nM, confidence) for IC50-like rows only."""
    from app.core.processing.evidence_normalizer import EvidenceNormalizer

    st = (row.get("standard_type") or "").upper()
    if "IC50" not in st:
        return None, 0
    nM = EvidenceNormalizer.to_nanomolar(
        row.get("standard_value"), str(row.get("standard_units") or "")
    )
    if nM is None or not math.isfinite(float(nM)) or float(nM) <= 0 or float(nM) > _NM_MAX_SANE:
        return None, 0
    try:
        conf = int(row.get("confidence_score") or 0)
    except (TypeError, ValueError):
        conf = 0
    return float(nM), conf


def cluster_ic50_by_target(evidence_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Group by ``target_chembl_id`` for IC50 endpoints with nM-normalized values.

    Emits per target: min / median IC50 (nM), assay count, confidence-weighted mean nM.
    """
    groups: dict[str, list[tuple[float, int]]] = defaultdict(list)

    for row in evidence_rows or []:
        tid = str(row.get("target_chembl_id") or "").strip().upper()
        if not tid.startswith("CHEMBL"):
            continue
        val_nM, conf = _ic50_row_value_nM(row)
        if val_nM is None:
            continue
        groups[tid].append((val_nM, max(conf, 0)))

    names: dict[str, str] = {}
    for row in evidence_rows or []:
        tid = str(row.get("target_chembl_id") or "").strip().upper()
        nm = str(row.get("target_pref_name") or "").strip()
        if tid.startswith("CHEMBL") and nm and tid not in names:
            names[tid] = nm

    out: list[dict[str, Any]] = []
    for tid, pairs in groups.items():
        vals = [v for v, _ in pairs]
        weights = [max(c, 1) for _, c in pairs]
        w_sum = float(sum(weights))
        w_mean = sum(v * w for v, w in zip(vals, weights)) / w_sum if w_sum else 0.0
        out.append(
            {
                "target_chembl_id": tid,
                "target_pref_name": names.get(tid, ""),
                "ic50_min_nM": round(min(vals), 4),
                "ic50_median_nM": round(float(median(vals)), 4),
                "assay_count": len(pairs),
                "confidence_weighted_mean_nM": round(float(w_mean), 4),
            }
        )

    out.sort(key=lambda x: x["ic50_median_nM"])
    return out[:50]
