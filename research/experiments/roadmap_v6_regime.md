# 🏛️ Implementation Plan: Two-Dimensional 9-State Market Regime Architecture

This document presents the detailed technical design to upgrade **Layer 2 Market Regime Classification** from a 1D 3-State Gaussian HMM into a **Two-Dimensional 9-State Interpretable Market Regime Architecture**.

---

## 🎯 Goal & Architecture Overview

Instead of forcing a single complex HMM to discover 9 uninterpretable hidden states, we decompose market regime into **two orthogonal, highly interpretable dimensions**:

```text
                                DIMENSION 2: VOLATILITY REGIME
                                 Low Vol     Normal Vol     High Vol
                              ┌────────────┬─────────────┬────────────┐
                     Bear (0) │  State 0   │   State 1   │  State 2   │
DIMENSION 1:                  ├────────────┼─────────────┼────────────┤
DIRECTIONAL HMM     Range (1) │  State 3   │   State 4   │  State 5   │
                              ├────────────┼─────────────┼────────────┤
                     Bull (2) │  State 6   │   State 7   │  State 8   │
                              └────────────┴─────────────┴────────────┘
```

### Key Benefits
1. **Zero Black-Box Complexity**: Preserves the robust 3-state HMM for directional bias while pairing it with expanding ATR volatility quintiles.
2. **Precision Signal Specialization**: Allows tree models to learn distinct rules for **Low-Vol Bear Consolidation** vs **High-Vol Bear Capitulation**.
3. **Graceful Fallback Safety**: If any of the 9 composite states has limited historical samples ($< 250$ bars), the model automatically falls back to its parent 1D Directional sub-model.

---

## 🚨 User Review Required

> [!IMPORTANT]
> **Proposed State Indexing Encoding**:
> Composite State ID is calculated deterministically as:
> $$\text{Composite State ID} = (\text{Directional HMM State} \times 3) + \text{Volatility Regime Class}$$
> * **Directional HMM State**: `0` = Bear, `1` = Range, `2` = Bull.
> * **Volatility Regime Class**: `0` = Low Vol ($< 33.3\%$), `1` = Normal Vol ($33.3\% - 66.6\%$), `2` = High Vol ($> 66.6\%$).
>
> *Example*: A **Bull Market with High Volatility** receives `Composite State ID = (2 * 3) + 2 = 8`.

> [!NOTE]
> **Expanding Rolling Volatility Percentiles (Zero Lookahead)**:
> Volatility thresholds use an **expanding rolling window percentile rank** (`feat_vol_atr.expanding(min_periods=100).rank(pct=True)`), ensuring **zero future data leakage**.

---

## 🙋 Open Questions

> [!TIP]
> None. The mathematical formulation for the 2D regime matrix is clean, zero-leakage, and fully compatible with existing decision/risk layers.

---

## 🧱 Proposed Changes

---

### 1. Feature Engineering Engine ([`research_and_training_engine/feature_matrix.py`](file:///Users/mahesh.patil/Desktop/Mahesh/ai-quant-lab/research_and_training_engine/feature_matrix.py))

#### [MODIFY] `research_and_training_engine/feature_matrix.py`
* Add `feat_vol_regime` calculation:
  ```python
  # Volatility Regime: 0 = Low Vol (<33.3%), 1 = Normal Vol (33.3%-66.6%), 2 = High Vol (>66.6%)
  vol_pct = df['feat_vol_atr_pct']
  df['feat_vol_regime'] = np.where(vol_pct < 33.33, 0.0, np.where(vol_pct <= 66.66, 1.0, 2.0))
  
  # Composite 2D Regime ID (0 through 8)
  df['feat_composite_regime'] = (df['feat_hmm_regime'] * 3.0) + df['feat_vol_regime']
  ```

---

### 2. AI Model Engine ([`core_machine_learning/ensemble.py`](file:///Users/mahesh.patil/Desktop/Mahesh/ai-quant-lab/core_machine_learning/ensemble.py))

#### [MODIFY] `core_machine_learning/ensemble.py`
* Upgrade `RegimeFusedEnsemble` to fit and manage **9 Specialized Sub-Models** (`sub_models[0.0]` through `sub_models[8.0]`).
* Implement fallback safety: If any composite state has $< 250$ training bars, fit on the parent HMM Directional state.
* Route predictions dynamically based on `X['feat_composite_regime']`.

```python
class RegimeFusedEnsemble:
    def __init__(self, random_state: int = 42):
        self.random_state = random_state
        self.is_fitted = False
        self.sub_models = {} # 0.0 to 8.0 -> (lgb_long, lgb_short)

    def fit(self, X_train: pd.DataFrame, targets: dict, composite_regimes: np.ndarray = None):
        if composite_regimes is None:
            composite_regimes = X_train['feat_composite_regime'].values

        for state in range(9):
            st_val = float(state)
            mask = (composite_regimes == st_val)
            X_state = X_train[mask]
            y_l = targets['dir_long'][mask]
            y_s = targets['dir_short'][mask]

            # Fallback if sparse sample
            if len(X_state) < 250:
                parent_dir = float(state // 3)
                mask_parent = (X_train['feat_hmm_regime'].values == parent_dir)
                X_state = X_train[mask_parent]
                y_l = targets['dir_long'][mask_parent]
                y_s = targets['dir_short'][mask_parent]

            m_long = LGBMClassifier(n_estimators=100, learning_rate=0.03, max_depth=5, min_child_samples=30, random_state=self.random_state, verbose=-1, n_jobs=1)
            m_long.fit(X_state, y_l)

            m_short = LGBMClassifier(n_estimators=100, learning_rate=0.03, max_depth=5, min_child_samples=30, random_state=self.random_state, verbose=-1, n_jobs=1)
            m_short.fit(X_state, y_s)

            self.sub_models[st_val] = (m_long, m_short)

        self.is_fitted = True
        return self
```

---

### 3. Training & Deployment Script ([`scripts/train_and_deploy_regime_fused_ensemble.py`](file:///Users/mahesh.patil/Desktop/Mahesh/ai-quant-lab/scripts/train_and_deploy_regime_fused_ensemble.py))

#### [MODIFY] `scripts/train_and_deploy_regime_fused_ensemble.py`
* Update training pipeline to compute 2D composite regimes and fit all 9 specialized sub-models.
* Save updated joblib weights to `models/production_deployment/model_suite.joblib`.
* Update metadata to `CERTIFIED_2D_REGIME_FUSED_V7`.

---

### 4. Live Signal Engine & Order Manager ([`live_execution_engine/trained_model_artifacts/signal_engine.py`](file:///Users/mahesh.patil/Desktop/Mahesh/ai-quant-lab/live_execution_engine/trained_model_artifacts/signal_engine.py))

#### [MODIFY] `live_execution_engine/trained_model_artifacts/signal_engine.py`
* Update `on_bar_closed` feature processing to include `feat_vol_regime` and `feat_composite_regime`.

---

## 🧪 Verification & Out-of-Sample Testing Plan

### 1. Automated Backtest Benchmark
* Run 8-Fold Expanding Rolling Walk-Forward Out-of-Sample Gauntlet (`2018–2025 EURUSD H1`).
* Verify zero data leakage, Bar `i+1` entry timing, and report 9-State performance breakdown.

### 2. Live Container Re-deployment
* Run `docker-compose restart paper-trading-engine` and check `docker logs ai_quant_paper_trading_engine` to confirm live initialization with `CERTIFIED_2D_REGIME_FUSED_V7`.
