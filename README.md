# 🤖 AI Quant Lab — Institutional Forex Algorithmic Trading Platform

An institutional-grade quantitative machine learning backtesting and trading platform built for mid-frequency Forex algorithmic trading (H1 horizon).

---

## 📂 Repository Structure

```
ai-quant-lab/
├── README.md                           # Main repository documentation & guide
├── .gitignore
│
├── docs/                               # Quantitative Architecture & Research Papers
│   ├── ml_prediction_pipeline_architecture.md   # Master ML Prediction Pipeline (CPCV, Conformal, Ensemble)
│   ├── project_architecture.md         # Full System Modular Design Specification
│   ├── extracted_docx_research.txt     # Extracted Solo Automated Forex Research Notes
│   └── Solo Automated Forex Trading System.docx # Core Master Research Document
│
├── ai_engine/                          # AI Core (Classifiers, Quantile Regressors, Conformal, CPCV, Drift)
│   ├── ensemble.py                     # LightGBM + CatBoost Multi-Model Ensemble
│   ├── conformal.py                    # Universal Conformal Predictor (90% Confidence Intervals)
│   ├── cpcv.py                         # Combinatorial Purged Cross-Validation (Purging & Embargoing)
│   ├── calibration.py                  # Expected Calibration Error (ECE) Tracker
│   ├── drift.py                        # Population Stability Index (PSI) Data Drift Detector
│   ├── hmm_regime.py                   # 3-State Gaussian Hidden Markov Model Regime Detector
│   ├── persistor.py                    # Fitted Model Persistence & Versioning (models/SYMBOL/YEAR/)
│   └── adaptive_sizer.py               # Volatility-Weighted & Drift-Calibrated Bet Sizer
│
├── macro_engine/                       # AI 1: Macro Context Engine (FOMC, CPI, NFP, COT)
├── market_state_engine/                # AI 2: Quantitative Market State Engine & Execution Context
├── context_engine/                     # Market State Vector Aggregator & Edge Confidence Score
├── execution_policy_engine/            # AI 3: Bounded Execution Policy Engine (Dynamic R:R & Time Exits)
│
├── core engines:
│   ├── data_loader/                    # Data Ingestion & Metadata Handler
│   ├── market_data_pipeline/           # Dukascopy H1 Downloader & Preprocessor
│   ├── indicator_engine/               # Technical Indicator Calculations (RSI, ADX, EMA, ATR)
│   ├── feature_engine/                 # Stationary Feature Matrix Generator & Fractional Diff (d = 0.35-0.45)
│   ├── risk_engine/                    # Risk Engine, Order Management & Dynamic SL/TP
│   ├── execution_engine/               # High-Fidelity Bar-by-Bar Simulation Engine
│   └── strategy_engine/                # InstitutionalAIStrategy, VolatilityBreakout, MLConsensus Strategy
│
├── research/                           # Research Engine, Labelers & Diagnostic Tools
│   └── research_engine/                # FeatureMatrixBuilder & Triple Barrier Labeler
│
├── scripts/                            # Master Execution Runners & Backtest Gauntlets
│   ├── run_master_institutional_backtest.py      # Master 8-Year Walk-Forward Institutional Backtest
│   ├── run_permutation_optimization_gauntlet.py  # 64-Permutation Parameter Optimization Gauntlet
│   ├── run_controlled_ab_testing_suite.py         # Component-Level Controlled A/B Testing Suite
│   ├── run_2d_interaction_and_policy_labeler.py  # 2D Trend x Volatility Interaction Matrix & AI 3 Predictor
│   └── run_market_state_engine_backtest.py       # Quantitative Market State Engine Runner
│
├── reports/                            # Generated Backtest JSON Results & HTML Dashboards
│   ├── master_institutional_backtest_results.json
│   ├── robustness_gauntlet_results.json
│   └── simulator_dashboard.html
│
├── models/                             # Saved Fitted Models (models/SYMBOL/YEAR/)
├── tests/                              # Unit & Integration Test Suite
└── app.py                              # Streamlit Interactive Quantitative Dashboard UI
```

---

## 🚀 Quick Start & Usage

### 1. Run Master Institutional Strategy Backtest (2018–2025)
```bash
python3 scripts/run_master_institutional_backtest.py
```

### 2. Run Permutation & Combination Optimization Gauntlet
```bash
python3 scripts/run_permutation_optimization_gauntlet.py
```

### 3. Run Controlled Component A/B Testing Suite
```bash
python3 scripts/run_controlled_ab_testing_suite.py
```

### 4. Run Interactive Quantitative Web Dashboard
```bash
streamlit run app.py
```

---

## 📊 Key Champion Results (2018–2025)

* **Net Return:** **+36.17%** (**+$3,617 Net Profit on $10,000 capital**)
* **Profit Factor (PF):** **1.29**
* **Sharpe Ratio:** **1.15**
* **Max Drawdown:** **11.09%**
* **Recovery Factor:** **3.21**
* **Capital Preservation:** **0.00% Drawdown in 2021 (Sat out 100% of low-edge chop)**