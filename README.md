# 🤖 AI Quant Lab — Institutional Forex Algorithmic Trading Platform

An institutional-grade, decoupled quantitative machine learning backtesting and production-ready trading engine built for Forex algorithmic trading on the H1 execution horizon.

---

## 🚀 Executive Summary & Current Champion Performance (2018–2025)

The platform evaluates an 8-year rolling walk-forward out-of-sample backtest across **49,000 clean H1 candles** (EURUSD) using a **Decoupled 3-AI Architecture**, **Combinatorial Purged Cross-Validation (CPCV)**, **3-State Gaussian Hidden Markov Model (HMM) Regime Filtering**, and the **Permanent Feature Admission Rule (FAR)**.

### 📊 Master Institutional Baseline Results (2018–2025)
* **Cumulative Net Return**: **+85.13%** (**+$8,513.09 Net Profit** on $10,000 capital)
* **Compound Annual Growth Rate (CAGR)**: **+8.01% / year**
* **Total Executed Trades**: **2,162 trades** (270 trades / year; 904 Long / 1,258 Short)
* **Profit Factor (PF)**: **1.24**
* **Sharpe Ratio (Annualized)**: **1.06**
* **Sortino Ratio (Downside Risk)**: **1.25**
* **Probabilistic Sharpe Ratio (PSR)**: **0.9999** (100% statistical confidence)
* **Deflated Sharpe Ratio (DSR)**: **0.0354 ($K=10$ conservative) / 0.1510 ($K_{eff}$ correlation-adjusted)**
* **Max Peak-to-Trough Drawdown**: **10.72%**
* **Multi-Year Consistency**: **7 out of 8 Years Profitable** (2019, 2020, 2021, 2022, 2023, 2024, 2025)

---

## 🏛️ System Architecture Highlights

### 1. 🛡️ Institutional Separation Principle
> **The AI Subsystems NEVER Generate BUY/SELL Signals.**
> Candidate entry signals ($S_i \in \{+1, -1\}$) are generated exclusively by the **Primary Strategy Engine** and filtered by the **Meta-Labeling Ensemble**. The AI Subsystems only adjust risk multipliers, profit target multiples, time horizons, and execution parameters.

### 2. 🤖 Decoupled 3-AI Subsystem Core
* **AI 1 — Macro Context Engine (`macro_engine/`)**: Evaluates Central Bank Policy Rate Divergence (Fed vs ECB) and Risk Sentiment metrics.
* **AI 2 — Quantitative Market State Engine (`market_state_engine/`)**: Computes normalized $0-100$ scores for Trend Strength (ADX), Volatility Squeeze, and Liquidity Density.
* **AI 3 — Execution Policy Engine (`execution_policy_engine/`)**: Maps market state vectors into bounded execution multipliers ($0.50\times - 1.00\times$ defensive risk scaling, $1.5\text{R} - 2.8\text{R}$ TP targets, $6\text{h} - 24\text{h}$ time exits, Level 1 event risk reduction, and audit-ready JSON explainability payloads).

### 3. 🔬 Permanent Feature Admission Rule (FAR Gatekeeper) (`ai_engine/feature_admission.py`)
No feature, sub-score, or indicator is permitted into production unless it empirically satisfies four strict criteria:
1. **Sample Floor**: $N_{\text{bucket}} \ge 200$ executed trades per evaluation bucket.
2. **Monotonicity**: Spearman rank correlation $r_s \ge +0.70$ between feature tertiles and out-of-sample trade quality.
3. **Uplift**: Top tertile Profit Factor exceeds bottom tertile by $\Delta\text{PF} \ge +0.10$.
4. **Walk-Forward Stability**: Feature maintains positive slope in $\ge 60\%$ of 2-year rolling walk-forward blocks.
* **Certified Features**: `cb_divergence` (PF Delta $+0.26$, 100% WF) and `risk_sentiment` (rs $+1.00$, 71.4% WF).
* **Pruned Noise Features**: `trend_macro`, `cot_score`, and `liquidity` were empirically rejected and completely removed from production.

---

## 📂 Repository Structure

```
ai-quant-lab/
├── README.md                           # Master Repository Guide & Production Specification
├── .gitignore
│
├── docs/                               # Quantitative Architecture & Specifications
│   ├── project_architecture.md         # Full System Modular Design & Flowchart Specification
│   ├── ml_prediction_pipeline_architecture.md # Master ML Prediction Pipeline (CPCV, Conformal, Ensemble)
│   └── work-update.md                  # Comprehensive Session Development Log & Audit Progress
│
├── ai_engine/                          # AI Core (Classifiers, Conformal, CPCV, Drift, FAR)
│   ├── feature_admission.py            # Permanent Feature Admission Rule (FAR) Gatekeeper
│   ├── ensemble.py                     # LightGBM + CatBoost Multi-Model Ensemble
│   ├── conformal.py                    # Universal Conformal Predictor (90% Confidence Intervals)
│   ├── cpcv.py                         # Combinatorial Purged Cross-Validation (Purging & Embargoing)
│   ├── calibration.py                  # Expected Calibration Error (ECE) Tracker
│   ├── drift.py                        # Population Stability Index (PSI) Data Drift Detector
│   ├── hmm_regime.py                   # 3-State Gaussian Hidden Markov Model Regime Detector
│   ├── persistor.py                    # Fitted Model Persistence & Versioning (models/SYMBOL/YEAR/)
│   └── adaptive_sizer.py               # Volatility-Weighted & Drift-Calibrated Bet Sizer
│
├── macro_engine/                       # AI 1: Macro Context Engine (FAR-Certified CB Divergence & Risk Sentiment)
│   ├── parser.py                       # Main MacroContextEngine Entry Point
│   ├── scores.py                       # Certified Sub-Score Calculators (cb_divergence, risk_sentiment, event_risk)
│   └── context_index.py                # Configurable Market Context Index Aggregator
│
├── market_state_engine/                # AI 2: Quantitative Market State Engine (Trend, Volatility, Liquidity)
│   └── state_calculator.py             # MarketStateEngine Normalized Score Calculator (0-100)
│
├── context_engine/                     # Market State Vector JSON Aggregator & Edge Confidence Score
│   └── aggregator.py                   # MarketContextAggregator Core
│
├── execution_policy_engine/            # AI 3: Bounded Execution Policy Engine (Dynamic R:R & Explainability)
│   └── policy.py                       # ExecutionPolicyEngine (Level 1 Event Risk & Defensive Scaling)
│
├── core engines:
│   ├── data_loader/                    # Data Ingestion & Metadata Handler
│   ├── market_data_pipeline/           # Dukascopy H1 Downloader & Preprocessor
│   ├── indicator_engine/               # Technical Indicator Calculations (RSI, ADX, EMA, ATR)
│   ├── feature_engine/                 # Stationary Feature Matrix Generator & Fractional Diff (d = 0.35-0.45)
│   ├── risk_engine/                    # Order Management, Risk Engine & Dynamic SL/TP
│   ├── execution_engine/               # High-Fidelity Bar-by-Bar Simulation Engine (DSR & Underwater Duration)
│   └── strategy_engine/                # InstitutionalAIStrategy, VolatilityBreakout, MLConsensus Strategy
│
├── research/                           # Research Engine, Labelers & Diagnostic Tools
│   └── research_engine/                # FeatureMatrixBuilder & Triple Barrier Labeler
│
├── scripts/                            # Master Execution Runners & Diagnostics
│   ├── run_master_institutional_backtest.py      # Master 8-Year Walk-Forward Institutional Diagnostic Runner
│   ├── run_permutation_optimization_gauntlet.py  # Parameter Optimization Gauntlet
│   ├── run_controlled_ab_testing_suite.py         # Component-Level Controlled A/B Testing Suite
│   └── run_market_state_engine_backtest.py       # Quantitative Market State Engine Backtester
│
├── reports/                            # Generated Progress Reports, Results JSON & Dashboards
│   ├── backtest_progress_report.md     # Auto-Appending Master Backtest Execution Log
│   ├── ai_implementation.md            # Decoupled AI Context Architecture Specification
│   ├── master_institutional_backtest_results.json # Full Diagnostic Metrics JSON
│   └── simulator_dashboard.html        # Interactive Frontend Visualization Dashboard
│
├── models/                             # Saved Fitted Models (models/SYMBOL/YEAR/)
├── tests/                              # Unit & Integration Test Suite
│   ├── test_feature_admission.py       # Unit Tests for Feature Admission Gatekeeper
│   └── test_macro_ablation.py          # Unit Tests for Macro Context & Execution Policy Engine
│
└── app.py                              # Streamlit Interactive Quantitative Dashboard UI
```

---

## 🚀 Quick Start & Diagnostic Commands

### 1. Execute Master Institutional Strategy Backtest (2018–2025)
```bash
python3 scripts/run_master_institutional_backtest.py --note "Your custom run note"
```
*(Auto-appends run results directly to `reports/backtest_progress_report.md`)*

### 2. Run Feature Admission Rule (FAR) Unit Tests
```bash
PYTHONPATH=. python3 tests/test_feature_admission.py
```

### 3. Run Macro Engine & Policy Engine Ablation Tests
```bash
PYTHONPATH=. python3 tests/test_macro_ablation.py
```

### 4. Launch Interactive Web Dashboard
```bash
streamlit run app.py
```

---

## 📅 Year-over-Year (YoY) Performance Matrix (2018–2025)

| Year | Return (%) | Net PnL ($) | Max DD (%) | Trades | Win Rate (%) | Profit Factor | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **2018** | -6.64% | -$663.83 | 10.72% | 363 | 30.9% | 0.89 | Drawdown Year |
| **2019** | **+3.12%** | **+$291.10** | 2.69% | 183 | 39.3% | 1.12 | 🟢 Profitable |
| **2020** | **+1.54%** | **+$148.47** | 4.55% | 386 | 33.7% | 1.02 | 🟢 Profitable |
| **2021** | **+0.57%** | **+$55.49** | 0.91% | 25 | 32.0% | 1.21 | 🟢 Profitable |
| **2022** | **+23.88%** | **+$2,347.72** | 3.34% | 331 | 39.3% | 1.54 | 🟢 Profitable |
| **2023** | **+21.93%** | **+$2,670.45** | 4.84% | 350 | 38.3% | 1.51 | 🟢 Profitable |
| **2024** | **+10.92%** | **+$1,622.29** | 2.21% | 141 | 38.3% | 1.65 | 🟢 Profitable |
| **2025** | **+12.39%** | **+$2,041.40** | 3.07% | 383 | 35.8% | 1.26 | 🟢 Profitable |