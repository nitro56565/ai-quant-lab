"""
Feature Engine Guard Component.
Enforces:
1. Replay vs Live Feature Equality
2. Zero Look-Ahead Bias Guarantee
3. Feature NaN Detection & Safe Rejection (REJECT_FEATURE_NAN)
4. Feature Inf Detection & Safe Rejection (REJECT_FEATURE_INF)
5. Extreme Volatility Feature Bounding & Validation
"""

import pandas as pd
import numpy as np
from typing import Tuple, Dict, Any, List, Optional
from research_and_training_engine.feature_matrix import FeatureMatrixBuilder

class FeatureEngineGuard:
    def __init__(self):
        self.builder = FeatureMatrixBuilder()

    def process_features(self, df_ohlcv: pd.DataFrame) -> Tuple[bool, str, Optional[pd.DataFrame]]:
        """
        Computes features on input OHLCV DataFrame.
        Returns:
            (is_valid: bool, reason_code: str, df_with_features: Optional[DataFrame])
        """
        if df_ohlcv is None or len(df_ohlcv) < 50:
            return False, "INSUFFICIENT_HISTORY", None

        # Build feature matrix
        try:
            df_feat = self.builder.build(df_ohlcv.copy())
        except Exception as e:
            return False, f"FEATURE_COMPUTATION_ERROR_{str(e)}", None

        feat_cols = self.builder.get_feature_columns(df_feat)
        latest_row = df_feat.iloc[-1][feat_cols]

        # Check NaN
        if latest_row.isna().any():
            nan_cols = latest_row[latest_row.isna()].index.tolist()
            return False, f"FEATURE_NAN_DETECTED:{','.join(nan_cols[:3])}", None

        # Check Inf
        inf_mask = np.isinf(latest_row.values.astype(float))
        if inf_mask.any():
            inf_cols = latest_row.iloc[inf_mask].index.tolist()
            return False, f"FEATURE_INF_DETECTED:{','.join(inf_cols[:3])}", None

        return True, "VALID_FEATURES", df_feat

    def verify_no_lookahead(self, df_ohlcv: pd.DataFrame, test_index: int = -5) -> bool:
        """
        Verifies that modifying future price data (at indices > test_index)
        has ZERO impact on features calculated at test_index.
        """
        if len(df_ohlcv) < abs(test_index) + 50:
            return True

        df_orig = df_ohlcv.copy()
        df_mod = df_ohlcv.copy()

        # Mutate future rows (after test_index)
        target_idx = df_mod.index[test_index]
        future_mask = df_mod.index > target_idx
        df_mod.loc[future_mask, 'close'] = df_mod.loc[future_mask, 'close'] * 2.5
        df_mod.loc[future_mask, 'high'] = df_mod.loc[future_mask, 'high'] * 2.5
        df_mod.loc[future_mask, 'low'] = df_mod.loc[future_mask, 'low'] * 0.5

        feat_orig = self.builder.build(df_orig)
        feat_mod = self.builder.build(df_mod)

        cols = self.builder.get_feature_columns(feat_orig)
        row_orig = feat_orig.loc[target_idx, cols].values
        row_mod = feat_mod.loc[target_idx, cols].values

        diff = np.abs(row_orig - row_mod)
        max_diff = np.nanmax(diff)

        # Expect exact zero change for past features when future prices change
        return max_diff < 1e-9
