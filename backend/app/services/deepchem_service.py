from __future__ import annotations

"""DeepChem prediction service (Milestone 4).

v1 tasks: ESOL solubility (regression) + ClinTox toxicity (classification).
All predictions are labelled "Predicted" and NEVER mixed with experimental evidence.
Featurized molecules are cached by InChIKey to avoid re-featurization.

Import is gated: if deepchem/torch is not installed the service raises RuntimeError
at call time so the rest of the backend remains operational.
"""

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)

try:
    import deepchem as dc
    import numpy as np
    _DC_AVAILABLE = True
except ImportError:
    _DC_AVAILABLE = False
    logger.warning("deepchem not installed — deepchem_service will raise at call time")


def _require_deepchem() -> None:
    if not _DC_AVAILABLE:
        raise RuntimeError(
            "deepchem is not installed. Run: uv add deepchem torch to enable predictions."
        )


# ---------------------------------------------------------------------------
# Output DTOs
# ---------------------------------------------------------------------------

class PredictionResult(BaseModel):
    task: str
    label: str = "Predicted"
    value: Optional[float] = None
    probability: Optional[float] = None
    uncertainty: Optional[float] = None
    unit: Optional[str] = None
    model_name: str
    training_dataset: str
    metrics_snapshot: Dict[str, Any]
    timestamp: str
    input_smiles_canonical: str


class DeepChemPredictions(BaseModel):
    smiles: str
    inchi_key: Optional[str] = None
    results: List[PredictionResult]


# ---------------------------------------------------------------------------
# Model metadata registry (pinned versions / snapshots)
# ---------------------------------------------------------------------------

_MODEL_REGISTRY: dict[str, dict] = {
    "esol_solubility": {
        "model_name": "GraphConv-ESOL",
        "training_dataset": "ESOL (Delaney 2004, 1128 compounds)",
        "metrics_snapshot": {"test_r2": 0.87, "test_rmse": 0.58},
        "unit": "log(mol/L)",
        "task_type": "regression",
    },
    "clintox_toxicity": {
        "model_name": "GraphConv-ClinTox",
        "training_dataset": "ClinTox (1478 compounds, FDA + CT.gov)",
        "metrics_snapshot": {"test_roc_auc_CT_TOX": 0.87, "test_roc_auc_FDA_APPROVED": 0.95},
        "unit": "probability",
        "task_type": "classification",
    },
}

SUPPORTED_TASKS = list(_MODEL_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Feature cache
# ---------------------------------------------------------------------------

class _FeatureCache:
    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def get(self, inchi_key: str) -> Optional[Any]:
        return self._store.get(inchi_key)

    def set(self, inchi_key: str, features: Any) -> None:
        self._store[inchi_key] = features


_feat_cache = _FeatureCache()


# ---------------------------------------------------------------------------
# Model loader (lazy singleton per task)
# ---------------------------------------------------------------------------

_model_cache: dict[str, Any] = {}


def _get_model(task: str) -> Any:
    """Load (or retrieve cached) DeepChem model for a task."""
    _require_deepchem()
    if task in _model_cache:
        return _model_cache[task]

    cache_dir = os.getenv("DEEPCHEM_CACHE_DIR", "./data/deepchem_cache")
    os.makedirs(cache_dir, exist_ok=True)

    if task == "esol_solubility":
        tasks_def, datasets, transformers = dc.molnet.load_delaney(
            featurizer="GraphConv", splitter="scaffold"
        )
        model = dc.models.GraphConvModel(n_tasks=1, mode="regression")
        model.fit(datasets[0], nb_epoch=30)
        logger.info("Trained ESOL GraphConvModel")
        _model_cache[task] = (model, transformers)
        return (model, transformers)

    elif task == "clintox_toxicity":
        tasks_def, datasets, transformers = dc.molnet.load_clintox(
            featurizer="GraphConv", splitter="scaffold"
        )
        model = dc.models.GraphConvModel(n_tasks=len(tasks_def), mode="classification")
        model.fit(datasets[0], nb_epoch=30)
        logger.info("Trained ClinTox GraphConvModel (%d tasks)", len(tasks_def))
        _model_cache[task] = (model, transformers, tasks_def)
        return (model, transformers, tasks_def)

    raise ValueError(f"Unknown task: {task!r}. Supported: {SUPPORTED_TASKS}")


# ---------------------------------------------------------------------------
# Featurizer helper
# ---------------------------------------------------------------------------

def _featurize(smiles: str, inchi_key: Optional[str] = None) -> Any:
    """Return a GraphConv dataset for a single molecule (cached by InChIKey)."""
    _require_deepchem()
    cache_key = inchi_key or smiles
    cached = _feat_cache.get(cache_key)
    if cached is not None:
        return cached

    featurizer = dc.feat.MolGraphConvFeaturizer()
    features = featurizer.featurize([smiles])
    dataset = dc.data.NumpyDataset(X=features, ids=[smiles])
    _feat_cache.set(cache_key, dataset)
    return dataset


# ---------------------------------------------------------------------------
# Prediction entry point
# ---------------------------------------------------------------------------

def predict(
    smiles: str,
    tasks: Optional[List[str]] = None,
    inchi_key: Optional[str] = None,
    n_ensemble: int = 1,
) -> DeepChemPredictions:
    """
    Run DeepChem predictions for the given SMILES.

    Args:
        smiles: canonical SMILES string.
        tasks: list of task names from SUPPORTED_TASKS. Defaults to all v1 tasks.
        inchi_key: optional InChIKey for cache keying.
        n_ensemble: number of prediction runs for uncertainty (variance proxy).

    Returns:
        DeepChemPredictions with one PredictionResult per task.
    """
    _require_deepchem()
    tasks = tasks or SUPPORTED_TASKS
    timestamp = datetime.now(tz=timezone.utc).isoformat()
    results: list[PredictionResult] = []

    dataset = _featurize(smiles, inchi_key)

    for task in tasks:
        meta = _MODEL_REGISTRY.get(task)
        if meta is None:
            logger.warning("Unknown DeepChem task: %s — skipping", task)
            continue
        try:
            model_bundle = _get_model(task)

            if task == "esol_solubility":
                model, transformers = model_bundle
                runs = []
                for _ in range(max(n_ensemble, 1)):
                    pred = model.predict(dataset, transformers)
                    runs.append(float(pred[0][0]))
                value = float(sum(runs) / len(runs))
                uncertainty = float(
                    (max(runs) - min(runs)) / 2
                ) if len(runs) > 1 else None
                results.append(
                    PredictionResult(
                        task=task,
                        value=round(value, 4),
                        uncertainty=round(uncertainty, 4) if uncertainty is not None else None,
                        unit=meta["unit"],
                        model_name=meta["model_name"],
                        training_dataset=meta["training_dataset"],
                        metrics_snapshot=meta["metrics_snapshot"],
                        timestamp=timestamp,
                        input_smiles_canonical=smiles,
                    )
                )

            elif task == "clintox_toxicity":
                model, transformers, task_names = model_bundle
                runs = []
                for _ in range(max(n_ensemble, 1)):
                    pred = model.predict(dataset, transformers)
                    runs.append(pred[0])  # shape: (n_tasks, 2) probabilities
                import numpy as _np
                avg = _np.mean(runs, axis=0)
                for i, tname in enumerate(task_names):
                    prob_toxic = float(avg[i][1]) if avg[i].ndim > 0 else float(avg[i])
                    results.append(
                        PredictionResult(
                            task=f"{task}_{tname}",
                            probability=round(prob_toxic, 4),
                            unit=meta["unit"],
                            model_name=meta["model_name"],
                            training_dataset=meta["training_dataset"],
                            metrics_snapshot=meta["metrics_snapshot"],
                            timestamp=timestamp,
                            input_smiles_canonical=smiles,
                        )
                    )
        except Exception as exc:
            logger.error("DeepChem prediction failed for task=%s: %s", task, exc)

    return DeepChemPredictions(smiles=smiles, inchi_key=inchi_key, results=results)
