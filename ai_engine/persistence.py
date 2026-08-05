import os
import json
import joblib
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger("ModelPersistor")

class ModelPersistor:
    """
    Model Persistence & Versioning Engine:
    Saves and loads serialized model artifacts to models/SYMBOL/YEAR/
    with full reproducibility metadata (training dates, feature list, hyperparams, metrics, git commit).
    """
    def __init__(self, base_dir: str = "models") -> None:
        self.base_dir = Path(base_dir)

    def _get_git_commit(self) -> str:
        try:
            res = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL)
            return res.decode("utf-8").strip()
        except Exception:
            return "unknown_commit"

    def save_model(
        self,
        model_suite: Any,
        symbol: str,
        year: int,
        start_date: str,
        end_date: str,
        feature_cols: list,
        best_params: dict,
        metrics: dict
    ) -> Path:
        target_dir = self.base_dir / symbol / str(year)
        target_dir.mkdir(parents=True, exist_ok=True)

        model_file = target_dir / "model_suite.joblib"
        metadata_file = target_dir / "metadata.json"

        # Serialize model object
        joblib.dump(model_suite, model_file, compress=3)

        metadata = {
            "symbol": symbol,
            "roll_year": year,
            "train_start": start_date,
            "train_end": end_date,
            "feature_count": len(feature_cols),
            "feature_columns": feature_cols,
            "best_hyperparams": best_params,
            "metrics": metrics,
            "git_commit": self._get_git_commit()
        }

        with open(metadata_file, "w") as f:
            json.dump(metadata, f, indent=2)

        logger.info(f"Persisted model and metadata to {target_dir}")
        return target_dir

    def load_model(self, symbol: str, year: int) -> Optional[Tuple[Any, dict]]:
        target_dir = self.base_dir / symbol / str(year)
        model_file = target_dir / "model_suite.joblib"
        metadata_file = target_dir / "metadata.json"

        if not model_file.exists() or not metadata_file.exists():
            return None

        model_suite = joblib.load(model_file)
        with open(metadata_file, "r") as f:
            metadata = json.load(f)

        return model_suite, metadata
