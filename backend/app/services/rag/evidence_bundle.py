from collections import defaultdict
from typing import List, Dict, Any

from app.core.processing.evidence_normalizer import EvidenceNormalizer
from app.core.processing.evidence_scorer import EvidenceScorer


class EvidenceBundleBuilder:

    @staticmethod
    def build(chembl_id: str, evidence_rows: List[Dict[str, Any]]) -> Dict[str, Any]:

        # -----------------------------------
        # HANDLE EMPTY CASE
        # -----------------------------------
        if not evidence_rows:
            return {
                "chembl_id": chembl_id,
                "status": "no_evidence",
                "total_records": 0,
                "top_targets": [],
                "assay_distribution": {},
                "top_evidence_score": 0,
                "sample_evidence": []
            }

        # -----------------------------------
        # STEP 1: NORMALIZATION
        # -----------------------------------
        clean_rows = EvidenceNormalizer.normalize_evidence(evidence_rows)

        # -----------------------------------
        # STEP 2: SCORING / RANKING
        # -----------------------------------
        ranked_rows = EvidenceScorer.rank_evidence(clean_rows)

        # -----------------------------------
        # STEP 3: TARGET COUNTING
        # -----------------------------------
        target_counts = defaultdict(int)

        for row in ranked_rows:
            target = row.get("target") or "UNKNOWN"
            target_counts[target] += 1

        top_targets = sorted(
            target_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]

        # -----------------------------------
        # STEP 4: ASSAY DISTRIBUTION
        # -----------------------------------
        assay_counts = defaultdict(int)

        for row in ranked_rows:
            assay_type = row.get("type") or "UNKNOWN"
            assay_counts[assay_type] += 1

        # -----------------------------------
        # STEP 5: TOP EVIDENCE SAMPLE
        # -----------------------------------
        sample_evidence = []

        for row in ranked_rows[:5]:
            sample_evidence.append({
                "activity_id": row.get("activity_id"),
                "assay_id": row.get("assay_id"),
                "target": row.get("target"),
                "type": row.get("type"),
                "value_nM": row.get("value_nM"),
                "confidence": row.get("confidence"),
                "score": row.get("evidence_score"),
                "high_quality": row.get("is_high_quality", False)
            })

        # -----------------------------------
        # FINAL RAG BUNDLE
        # -----------------------------------
        return {
            "chembl_id": chembl_id,
            "status": "ok",
            "total_records": len(ranked_rows),

            "top_targets": top_targets,
            "assay_distribution": dict(assay_counts),

            "top_evidence_score": ranked_rows[0].get("evidence_score", 0) if ranked_rows else 0,

            "sample_evidence": sample_evidence
        }