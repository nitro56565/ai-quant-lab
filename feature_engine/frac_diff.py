import numpy as np
import pandas as pd
from typing import Optional

class FractionalDifferentiation:
    """
    Fixed-Width Window Fractional Differentiation (De Prado).
    Preserves maximum price memory (autocorrelation) while achieving stationarity.
    """
    @staticmethod
    def get_weights(d: float, size: int, weight_threshold: float = 1e-4) -> np.ndarray:
        """Calculate fractional weights w_k until absolute weight falls below threshold."""
        w = [1.0]
        for k in range(1, size):
            w_k = -w[-1] / k * (d - k + 1)
            if abs(w_k) < weight_threshold:
                break
            w.append(w_k)
        return np.array(w[::-1])  # Reverse for convolution

    @staticmethod
    def frac_diff_fixed_width(series: pd.Series, d: float = 0.40, weight_threshold: float = 1e-4) -> pd.Series:
        """
        Applies Fixed-Width Window Fractional Differentiation to a pandas Series.
        """
        n = len(series)
        w = FractionalDifferentiation.get_weights(d, n, weight_threshold)
        width = len(w)
        
        if width > n:
            return pd.Series(index=series.index, data=np.nan)

        vals = series.values
        res = np.full(n, np.nan)

        for i in range(width - 1, n):
            res[i] = np.dot(w, vals[i - width + 1 : i + 1])

        out = pd.Series(res, index=series.index)
        return out.ffill().bfill().fillna(0.0)
