from __future__ import annotations

"""Phase 3 DeepChem predictor (plan: mock/stub predictor).

This module exists to provide the import path expected by the Phase 3 E2E test:
    from app.services.deepchem.deepchem_predictor import DeepChemPredictor

It returns a deterministic float under the key 'predicted_activity'.
"""

from typing import Any, Dict


class DeepChemPredictor:
    @staticmethod
    def predict(smiles: str) -> Dict[str, Any]:
        if not smiles:
            return {"smiles": smiles, "predicted_activity": None, "model_type": "mock"}

        # Deterministic mock score (kept stable for tests)
        if smiles == "CCO":
            score = 0.73
        else:
            # simple stable heuristic in [0,1]
            score = round(min(0.99, max(0.01, (len(smiles) % 100) / 100.0)), 2)

        return {
            "smiles": smiles,
            "predicted_activity": float(score),
            "model_type": "mock",
        }

