import numpy as np
import pandas as pd
from typing import Dict, Any, List
import shap
import logging

logger = logging.getLogger("SignalExplainer")

class SignalExplainer:
    """
    TreeSHAP Explainability Engine for institutional model attribution.
    Computes exact Shapley values to interpret trade signal decisions.
    """
    def __init__(self, model: Any) -> None:
        self.model = model
        self.explainer = None
        self._init_explainer()

    def _init_explainer(self) -> None:
        """Initialize TreeSHAP explainer for LightGBM/Tree estimator."""
        target_model = self.model
        # If wrapped in CalibratedClassifierCV, unwrap first estimator
        if hasattr(self.model, 'calibrated_classifiers_'):
            target_model = self.model.calibrated_classifiers_[0].estimator

        try:
            self.explainer = shap.TreeExplainer(target_model)
        except Exception as e:
            logger.warning(f"Could not initialize TreeExplainer: {e}. Falling back to Explainer.")
            self.explainer = shap.Explainer(target_model)

    def explain_instance(self, X_instance: pd.DataFrame, top_k: int = 5) -> Dict[str, Any]:
        """
        Explain a single trade candle instance.
        Returns dictionary containing top positive and negative SHAP feature attributions.
        """
        if self.explainer is None:
            return {"error": "Explainer not initialized."}
            
        shap_values = self.explainer.shap_values(X_instance)
        
        # Format binary classification SHAP matrix if multi-class output
        if isinstance(shap_values, list):
            sv = shap_values[1][0] if len(shap_values) > 1 else shap_values[0][0]
        elif isinstance(shap_values, np.ndarray) and shap_values.ndim == 2:
            sv = shap_values[0]
        else:
            sv = np.array(shap_values).flatten()

        feature_names = X_instance.columns.tolist()
        feature_values = X_instance.iloc[0].values
        
        attributions = [
            {
                "feature": feature_names[i],
                "value": float(feature_values[i]),
                "shap_value": float(sv[i])
            }
            for i in range(len(feature_names))
        ]
        
        # Sort by absolute SHAP contribution magnitude
        attributions_sorted = sorted(attributions, key=lambda x: abs(x["shap_value"]), reverse=True)
        top_features = attributions_sorted[:top_k]
        
        return {
            "top_attributions": top_features,
            "base_value": float(getattr(self.explainer, 'expected_value', 0.0) if not isinstance(getattr(self.explainer, 'expected_value', 0.0), np.ndarray) else getattr(self.explainer, 'expected_value', [0.0])[0])
        }
