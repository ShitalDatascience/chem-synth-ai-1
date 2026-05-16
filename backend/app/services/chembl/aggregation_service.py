from collections import defaultdict
from statistics import mean
from typing import List, Dict, Any, Optional


class ActivityAggregator:
    """
    Phase 3: Aggregates cleaned bioactivity data into ML-ready molecular features.
    """

    def aggregate_by_molecule(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped = defaultdict(list)

        for row in rows:
            chembl_id = row.get("chembl_id")
            if chembl_id:
                grouped[chembl_id].append(row)

        results = []

        for chembl_id, items in grouped.items():
            features = self._aggregate_single_molecule(chembl_id, items)
            if features:
                results.append(features)

        return results

    def _aggregate_single_molecule(
        self, chembl_id: str, rows: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:

        ic50_values = []
        ki_values = []
        pic50_values = []
        valid_counts = 0

        for r in rows:
            if not r.get("is_valid"):
                continue

            valid_counts += 1
            value = r.get("value_nm")

            if value is None:
                continue

            std_type = r.get("standard_type")

            if std_type == "IC50":
                ic50_values.append(value)
            elif std_type == "Ki":
                ki_values.append(value)
            elif std_type == "pIC50":
                pic50_values.append(value)

        if valid_counts == 0:
            return None

        return {
            "chembl_id": chembl_id,
            "ic50_mean": mean(ic50_values) if ic50_values else None,
            "ic50_min": min(ic50_values) if ic50_values else None,
            "ic50_max": max(ic50_values) if ic50_values else None,
            "ki_mean": mean(ki_values) if ki_values else None,
            "ki_min": min(ki_values) if ki_values else None,
            "pic50_mean": mean(pic50_values) if pic50_values else None,
            "activity_count": valid_counts,
            "has_ic50": len(ic50_values) > 0,
            "has_ki": len(ki_values) > 0,
        }
