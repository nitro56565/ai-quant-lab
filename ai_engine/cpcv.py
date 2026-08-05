import numpy as np
import pandas as pd
import itertools
import logging

logger = logging.getLogger("CombinatorialPurgedCV")

class CombinatorialPurgedCV:
    """
    Combinatorial Purged Cross-Validation (CPCV) with Purging & Embargoing
    Ref: Marcos López de Prado, Advances in Financial Machine Learning (Chapter 7).

    Features:
    1. Purging: Removes training labels that overlap with test evaluation windows (horizon H=12).
    2. Embargoing: Applies a post-test embargo gap (e.g., 24 bars) to eliminate serial autocorrelation.
    3. Combinatorial Paths: Evaluates N groups choosing k test groups (C(N, k) paths).
    """
    def __init__(self, n_splits: int = 6, n_test_splits: int = 2, samples_info_sets: pd.Series = None, pct_embargo: float = 0.01) -> None:
        self.n_splits = n_splits
        self.n_test_splits = n_test_splits
        self.samples_info_sets = samples_info_sets
        self.pct_embargo = pct_embargo

    def split(self, X: pd.DataFrame, pred_times: pd.Series = None, eval_times: pd.Series = None):
        """
        Yields (train_indices, test_indices, path_id) for each combinatorial path.
        """
        n_samples = len(X)
        indices = np.arange(n_samples)
        
        # 1. Divide dataset into N equal contiguous blocks
        group_bounds = np.linspace(0, n_samples, self.n_splits + 1, dtype=int)
        groups = [indices[group_bounds[i]:group_bounds[i+1]] for i in range(self.n_splits)]

        # 2. Generate all C(N, k) test combinations
        combo_test_groups = list(itertools.combinations(range(self.n_splits), self.n_test_splits))
        embargo_offset = int(n_samples * self.pct_embargo)

        for path_id, test_group_ids in enumerate(combo_test_groups):
            test_indices = np.concatenate([groups[g_id] for g_id in test_group_ids])
            train_indices_raw = np.concatenate([groups[g_id] for g_id in range(self.n_splits) if g_id not in test_group_ids])

            # 3. Purging & Embargoing
            purged_train_indices = []
            
            test_start_idx = test_indices.min()
            test_end_idx = test_indices.max()
            
            # Post-test embargo window
            embargo_end_idx = test_end_idx + embargo_offset

            for tr_idx in train_indices_raw:
                # Purging: Check if train label overlaps with test window
                if pred_times is not None and eval_times is not None:
                    t_init = pred_times.iloc[tr_idx]
                    t_end = eval_times.iloc[tr_idx]
                    test_init = pred_times.iloc[test_start_idx]
                    test_end = eval_times.iloc[min(test_end_idx, len(eval_times)-1)]
                    
                    if (t_init <= test_end) and (t_end >= test_init):
                        continue  # Purged
                
                # Embargoing: Exclude training bars right after test window
                if test_end_idx < tr_idx <= embargo_end_idx:
                    continue  # Embargoed

                purged_train_indices.append(tr_idx)

            yield np.array(purged_train_indices), test_indices, path_id
