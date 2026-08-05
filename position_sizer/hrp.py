import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage
from scipy.spatial.distance import squareform
from typing import List, Dict

class HierarchicalRiskParity:
    """
    Hierarchical Risk Parity (HRP) Portfolio Allocation (De Prado).
    Computes robust, invertible portfolio weights across asset universe
    using graph theory and hierarchical clustering.
    """
    @staticmethod
    def get_quasi_diag(link: np.ndarray) -> List[int]:
        """Quasi-diagonalization: Reorder items according to dendrogram clusters."""
        link = link.astype(int)
        sort_ix = [link[-1, 0], link[-1, 1]]
        num_items = link[-1, 3]
        
        while max(sort_ix) >= num_items:
            sort_ix_tmp = []
            for item in sort_ix:
                if item >= num_items:
                    sort_ix_tmp.append(link[item - num_items, 0])
                    sort_ix_tmp.append(link[item - num_items, 1])
                else:
                    sort_ix_tmp.append(item)
            sort_ix = sort_ix_tmp
        return sort_ix

    @staticmethod
    def get_cluster_var(cov: np.ndarray, c_items: List[int]) -> float:
        """Calculate variance of a cluster under inverse-variance weighting."""
        cov_slice = cov[np.ix_(c_items, c_items)]
        iv = 1.0 / np.diag(cov_slice)
        iv /= iv.sum()
        w = iv.reshape(-1, 1)
        c_var = np.dot(np.dot(w.T, cov_slice), w)[0, 0]
        return float(c_var)

    @staticmethod
    def get_rec_bisection(cov: np.ndarray, sort_ix: List[int]) -> pd.Series:
        """Recursive bisection weight allocation."""
        w = pd.Series(1.0, index=sort_ix)
        c_items = [sort_ix]
        
        while len(c_items) > 0:
            c_items = [i[j:k] for i in c_items for j, k in ((0, len(i) // 2), (len(i) // 2, len(i))) if len(i) > 1]
            for i in range(0, len(c_items), 2):
                c_items0 = c_items[i]
                c_items1 = c_items[i + 1]
                v0 = HierarchicalRiskParity.get_cluster_var(cov, c_items0)
                v1 = HierarchicalRiskParity.get_cluster_var(cov, c_items1)
                alpha = 1.0 - v0 / (v0 + v1)
                w[c_items0] *= alpha
                w[c_items1] *= 1.0 - alpha
        return w

    @classmethod
    def calculate_hrp_weights(cls, returns_df: pd.DataFrame) -> pd.Series:
        """
        Main HRP Pipeline:
        Input: DataFrame of asset returns (N_samples x N_assets)
        Output: Series of portfolio weights summing to 1.0
        """
        cov = returns_df.cov().values
        corr = returns_df.corr().values
        
        dist = np.sqrt(np.clip(0.5 * (1.0 - corr), 0.0, 1.0))
        dist_compressed = squareform(dist, checks=False)
        
        link = linkage(dist_compressed, method='single')
        sort_ix = cls.get_quasi_diag(link)
        
        weights = cls.get_rec_bisection(cov, sort_ix)
        weights.index = returns_df.columns[sort_ix]
        return weights.sort_index()
