# 🧠 Master ML Prediction Pipeline Architecture (The Heart of the System)

## Executive Overview
The **ML Prediction Pipeline** in `InstitutionalAIStrategy` is a production-grade, multi-stage quantitative Machine Learning system. It combines statistical feature engineering, non-stationary market regime detection, ensemble machine learning (LightGBM + CatBoost), conformal uncertainty estimation, and probability calibration.

---

## 📐 End-to-End Dataflow Architecture

```mermaid
flowchart TD
    A["Raw H1 Price Bars (OHLCV)"] --> B["1. Feature Matrix Builder (63+ Features)"]
    B --> C["2. Future Labeler & Triple Barrier Target Generator"]
    
    subgraph Walk Forward Training Loop (4-Year Train / 1-Year Out-Of-Sample)
        B & C --> D["3. HMM Market Regime Detector (3-State Gaussian)"]
        B --> E["4. Data Drift Detector (PSI Drift Evaluation)"]
        
        D & E & B & C --> F["5. Multi-Target Machine Learning Ensemble"]
        
        subgraph Machine Learning Ensemble Suite (core_machine_learning/ensemble.py)
            F1["LightGBM + CatBoost Classifiers (Calibrated Win Probability P)"]
            F2["LightGBM + CatBoost Quantile Regressors (10%, 50%, 90% MFE & MAE)"]
            F1 & F2 --> F3["Expected Value (EV) Calculator"]
        end
        
        F --> G["6. Universal Conformal Predictor (90% Uncertainty Bounds)"]
        F --> H["7. Probability Calibration Tracker (ECE & Brier Score)"]
        F --> I["8. Model Persistence & Versioning Engine (models/SYMBOL/YEAR/)"]
    end
    
    F3 & G & D & E --> J["9. Dynamic Rolling Quantile Thresholding"]
    J --> K["10. Adaptive Bet Sizer & Bounded Execution Policy Engine"]
    K --> L["11. Bar-by-Bar Trade Matching Simulation Engine"]
```

---

## 🔬 Detailed Component Breakdown

### 1. Feature Matrix Builder (`research_and_training_engine/feature_matrix.py`)
Generates 63+ normalized, stationary features across 5 distinct feature families:
* **Technical Oscillators:** RSI(14), ADX(14), DI Spread ($\text{DI}^+ - \text{DI}^-$), EMA Stack Alignment ($EMA_{20} > EMA_{50} > EMA_{200}$).
* **Fractional Differentiation:** Volatility & Price series transformed via fractional order $d \approx 0.35-0.45$ to preserve long memory while achieving stationarity (adf test $p < 0.01$).
* **Volatility Metrics:** Normalized 14-period ATR ($\text{ATR} / \text{Close}$), ATR Percentile Rank, Bollinger Band Squeeze Ratio ($\text{Width} / \text{MA}$).
* **Liquidity & Microstructure:** Volume Ratio ($\text{Vol} / \text{MA}_{20}$), Body-to-Range ratio ($\frac{|\text{Close} - \text{Open}|}{\text{High} - \text{Low}}$).
* **Session Interaction:** Hour of day, day of week, London/NY session flags.

---

### 2. Future Labeler & Triple Barrier Target Generator (`research_and_training_engine/labeler.py`)
Computes out-of-sample forward-looking targets over a 12-hour holding horizon ($H=12$):
* **Directional Target ($Y_{\text{dir}}$):** $1$ if $Close_{t+12} > Close_t$, else $0$.
* **Maximum Favorable Excursion ($\text{MFE}_{12h}$):** Highest price gain in pips within the next 12 bars:
  $$\text{MFE}_{\text{Long}} = \frac{\max(High_{t+1:t+12}) - Close_t}{\text{Pip Size}}$$
* **Maximum Adverse Excursion ($\text{MAE}_{12h}$):** Worst drawdown in pips within the next 12 bars:
  $$\text{MAE}_{\text{Long}} = \frac{Close_t - \min(Low_{t+1:t+12})}{\text{Pip Size}}$$

---

### 3. HMM Market Regime Detector (`core_machine_learning/hmm_regime.py`)
Fits a 3-State Gaussian Hidden Markov Model (HMM) on log returns and realized volatility:
* **State 0:** Strong Bull Trend ($\mu > 0, \sigma^2 \text{ moderate}$)
* **State 1:** Strong Bear Trend ($\mu < 0, \sigma^2 \text{ moderate}$)
* **State 2:** Choppy Consolidation ($\mu \approx 0, \sigma^2 \text{ high}$)
* **Output:** Soft regime probabilities ($P(\text{Bull}), P(\text{Bear}), P(\text{Chop})$).

---

### 4. Data Drift Detector (`core_machine_learning/drift.py`)
Monitors feature distribution shifts using Population Stability Index (PSI):
$$\text{PSI} = \sum_{k=1}^K (P_k - Q_k) \times \ln\left(\frac{P_k}{Q_k}\right)$$
* **$\text{PSI} < 0.10$:** NO DRIFT
* **$0.10 \le \text{PSI} < 0.25$:** MODERATE DRIFT
* **$\text{PSI} \ge 0.25$:** SEVERE DRIFT $\rightarrow$ Triggers model retraining & position size reduction.

---

### 5. Multi-Target ML Ensemble Suite (`core_machine_learning/ensemble.py`)
The computational core combining LightGBM + CatBoost across 8 specialized models:

```
                               ┌──────────────────────────────────────────────┐
                               │  LightGBM Classifier + CatBoost Classifier   │
                               │  -> Calibrated Win Probability P(Long/Short) │
                               └──────────────────────┬───────────────────────┘
                                                      │
                       ┌──────────────────────────────┴──────────────────────────────┐
                       ▼                                                             ▼
       Quantile Regressors (MFE 10%, 50%, 90%)                       Quantile Regressors (MAE 10%, 50%, 90%)
  • Predicts 50th percentile Median Upside Target (MFE50)        • Predicts 50th percentile Median Downside Risk (MAE50)
```

#### Expected Value (EV) Calculation:
For every candle, the ensemble computes mathematical expectancy:
$$\text{EV}_{\text{Long}} = \left[ P(\text{Win}_{\text{Long}}) \times \text{MFE}_{50,\text{Long}} \right] - \left[ (1 - P(\text{Win}_{\text{Long}})) \times \text{MAE}_{50,\text{Long}} \right] - \text{Spread Drag}$$

---

### 6. Universal Conformal Predictor (`core_machine_learning/conformal.py`)
Calibrated on an 80/20 train/validation split to guarantee finite-sample non-parametric uncertainty coverage ($\alpha = 0.90$):
$$\hat{q} = \text{Quantile}_{0.90}\left( |y_{\text{val}} - \hat{y}_{\text{val}}| \right)$$
* Calculates **Conformal Confidence Score** ($0.0 - 1.0$) based on prediction interval width relative to local volatility ($\text{ATR}$).

---

### 7. Probability Calibration Tracker (`core_machine_learning/calibration.py`)
Evaluates out-of-sample probability calibration accuracy:
* **Expected Calibration Error (ECE):**
  $$\text{ECE} = \sum_{m=1}^M \frac{|B_m|}{N} \left| \text{acc}(B_m) - \text{conf}(B_m) \right|$$
* Ensures $P(\text{Win}) = 60\%$ actually wins 60% of the time in live out-of-sample data.

---

### 8. Dynamic Rolling Quantile Thresholding (`strategy_engine/institutional_ai.py`)
Instead of hardcoding arbitrary pip limits, thresholds adapt dynamically per rolling walk-forward window:
* **EV Threshold ($\tau_{\text{EV}}$):** Top 95th percentile of expected value distribution.
* **Probability Threshold ($\tau_{P}$):** Top 90th percentile of probability distribution (bounded by $\ge 0.52$).

---

### 9. Adaptive Sizer & Bounded Execution Policy (`core_machine_learning/adaptive_sizer.py` & `execution_policy_engine/policy.py`)
Calculates trade risk percentage ($0.25\% - 1.00\%$) and execution parameters ($2.0R - 2.8R$ TP, $6h - 24h$ Time Exit) based on:
$$\text{Risk \%} = \text{Base Risk} \times f(\text{EV}) \times f(\text{Conformal Confidence}) \times f(\text{Ensemble Disagreement}) \times f(\text{Regime}) \times f(\text{Drift})$$

---

## 📊 Summary Table of Pipeline Components

| Stage | Module Name | Primary Class / Function | Main Output |
| :--- | :--- | :--- | :--- |
| **1** | `research_and_training_engine/feature_matrix.py` | `FeatureMatrixBuilder` | 63+ Stationary Feature Matrix |
| **2** | `research_and_training_engine/labeler.py` | `FutureLabeler` | $Y_{\text{dir}}$, $\text{MFE}_{10/50/90}$, $\text{MAE}_{10/50/90}$ |
| **3** | `core_machine_learning/hmm_regime.py` | `HMMRegimeDetector` | Soft Regime Probabilities ($P_{\text{Bull}}, P_{\text{Bear}}, P_{\text{Chop}}$) |
| **4** | `core_machine_learning/drift.py` | `DataDriftDetector` | PSI Score & Drift Flag |
| **5** | `core_machine_learning/ensemble.py` | `LightGBMCatBoostEnsemble` | $P(\text{Win})$, Expected Value ($\text{EV}$) |
| **6** | `core_machine_learning/conformal.py` | `UniversalConformalPredictor` | 90% Confidence Bounds & Uncertainty Score |
| **7** | `core_machine_learning/calibration.py` | `ProbabilityCalibrationTracker` | Expected Calibration Error (ECE) |
| **8** | `strategy_engine/institutional_ai.py` | `InstitutionalAIStrategy` | Signals (`BUY` / `SELL`) |
| **9** | `execution_policy_engine/policy.py` | `ExecutionPolicyEngine` | Bounded Risk \%, TP R-Multiple, Time Exit |
