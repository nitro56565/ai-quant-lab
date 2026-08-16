import numpy as np
import pandas as pd
from typing import List, Optional, Tuple
from sklearn.preprocessing import StandardScaler
from hmmlearn.hmm import GaussianHMM
import logging

logger = logging.getLogger("HMMRegimeDetector")

DEFAULT_HMM_FEATURES = [
    "feat_trend_ema50_slope",
    "feat_vol_atr_pct",
    "feat_trend_adx",
    "feat_osc_rsi"
]

class HMMRegimeDetector:
    """
    Gaussian Hidden Markov Model (HMM) for probabilistic market regime detection.
    Models hidden state transitions across market regimes (Chop, Bullish Trend, Bearish Trend / Volatility).
    Uses strict training-set scaling to prevent lookahead leakage.
    """
    def __init__(
        self,
        n_components: int = 3,
        covariance_type: str = "full",
        n_iter: int = 100,
        random_state: int = 42,
        feature_cols: Optional[List[str]] = None
    ) -> None:
        self.n_components = n_components
        self.covariance_type = covariance_type
        self.n_iter = n_iter
        self.random_state = random_state
        self.feature_cols = feature_cols or DEFAULT_HMM_FEATURES
        
        self.scaler = StandardScaler()
        self.model = GaussianHMM(
            n_components=self.n_components,
            covariance_type=self.covariance_type,
            n_iter=self.n_iter,
            random_state=self.random_state
        )
        self.is_fitted = False
        self._state_mapping = None

    def _extract_features(self, df: pd.DataFrame) -> np.ndarray:
        """Extract and sanitize feature matrix for HMM."""
        available_cols = [c for c in self.feature_cols if c in df.columns]
        if not available_cols:
            # Fallback to close returns and ATR if standard features missing
            if 'close' in df.columns:
                returns = df['close'].pct_change().fillna(0.0).values.reshape(-1, 1)
                return returns
            raise ValueError(f"None of the HMM feature columns {self.feature_cols} exist in DataFrame.")
            
        X = df[available_cols].copy()
        X = X.ffill().bfill().fillna(0.0)
        return X.values

    def fit(self, df_train: pd.DataFrame) -> "HMMRegimeDetector":
        """
        Fit the Gaussian HMM model on historical training data.
        """
        X_raw = self._extract_features(df_train)
        X_scaled = self.scaler.fit_transform(X_raw)
        
        self.model.fit(X_scaled)
        self.is_fitted = True
        
        # Sort state IDs deterministically based on feature means (e.g., ADX/ATR magnitude)
        # to ensure state 0 = low vol, state 1 = trend, state 2 = high vol
        state_means = self.model.means_.mean(axis=1)
        self._state_mapping = {old_idx: new_idx for new_idx, old_idx in enumerate(np.argsort(state_means))}
        
        logger.info(f"HMMRegimeDetector successfully fitted with {self.n_components} states.")
        return self

    def predict_proba(self, df: pd.DataFrame) -> np.ndarray:
        """
        Predict posterior state probabilities P(State = k | X_t) for each candle.
        Returns array of shape (N, n_components).
        """
        if not self.is_fitted:
            raise RuntimeError("HMMRegimeDetector must be fitted before calling predict_proba().")
            
        X_raw = self._extract_features(df)
        X_scaled = self.scaler.transform(X_raw)
        
        raw_probs = self.model.predict_proba(X_scaled)
        
        # Re-map columns according to deterministic state ordering
        ordered_probs = np.zeros_like(raw_probs)
        if self._state_mapping:
            for old_k, new_k in self._state_mapping.items():
                ordered_probs[:, new_k] = raw_probs[:, old_k]
        else:
            ordered_probs = raw_probs
            
        return ordered_probs

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """
        Predict the most likely hidden state sequence (Viterbi decoding).
        Returns integer array of shape (N,).
        """
        probs = self.predict_proba(df)
        return np.argmax(probs, axis=1)

    def transform_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Appends 'hmm_state' and 'hmm_prob_0', 'hmm_prob_1', 'hmm_prob_2' to a copy of DataFrame.
        """
        df_out = df.copy()
        probs = self.predict_proba(df)
        
        df_out['hmm_state'] = np.argmax(probs, axis=1)
        for k in range(self.n_components):
            df_out[f'hmm_prob_{k}'] = probs[:, k]
            
        return df_out
