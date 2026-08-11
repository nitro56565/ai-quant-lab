# 🚀 AI Quant Lab - Master Certified Production Engine (`TRIPLE_STACKING_ENSEMBLE_V1`)

Welcome to **AI Quant Lab**, an institutional-grade, multi-regime quantitative machine learning framework for automated foreign exchange (FX) trading.

---

## 🏛️ Master Certified Production Architecture

```
                          ┌────────────────────────────────────────────────────────┐
                          │   MASTER CERTIFIED PRODUCTION ARCHITECTURE (V16.0)     │
                          └────────────────────────────────────────────────────────┘
                                                       │
         ┌─────────────────────────────────────────────┼─────────────────────────────────────────────┐
         ▼                                             ▼                                             ▼
 ┌───────────────┐                             ┌───────────────┐                             ┌───────────────┐
 │ FEATURE MATRIX│                             │ REGIME ENGINE │                             │ MODEL ENSEMBLE│
 ├───────────────┤                             ├───────────────┤                             ├───────────────┤
 │ 14 Technical  │                             │ 9 Discretized │                             │ Equal Weight  │
 │ Indicators    │                             │ Regimes (3 HMM│                             │ Triple Stack  │
 │ (RSI, ATR, BB │                             │  Directional  │                             │ (LGBM 33.33%  │
 │ ADX, MACD)    │                             │  x 3 Vol-Rank)│                             │  Cat  33.33%  │
 └───────────────┘                             └───────────────┘                             │  XGB  33.33%) │
                                                       │                                     └───────────────┘
                                                       ▼                                             │
                                               ┌───────────────┐                                     │
                                               │ PROBABILITY   │◄────────────────────────────────────┘
                                               │ THRESHOLDS    │
                                               ├───────────────┤
                                               │ Raw Prob.     │
                                               │ P >= 0.42 (R1)│
                                               │ P >= 0.36(0/2)│
                                               └───────────────┘
                                                       │
                                                       ▼
                                               ┌───────────────┐
                                               │ EXECUTION     │
                                               ├───────────────┤
                                               │ 0.25 ATR Limit│
                                               │ 12H Exit Limit│
                                               │ 50% @ +1.5R   │
                                               └───────────────┘
```

---

## 📁 Clean Repository Structure

```text
ai-quant-lab/
├── ai_engine/                                # Directional HMM Regime Detector & ML Stacking Engine
├── data_loader/                              # High-performance Parquet Multi-Timeframe Data Loader
├── execution_engine/                         # Limit Retrace Entry, Partial Exit & Order Management Engine
├── market_data_pipeline/                     # Multi-Asset Data Ingestion, HistData Parser & Storage
├── research_engine/                          # 14 Technical Feature Matrix Builder & Triple Barrier Labeler
├── position_sizer/                           # Risk-Adjusted Dynamic Volatility Lot Size Calculator
├── risk_engine/                              # Portfolio Risk & Drawdown Limit Control
│
├── docs/                                     # Official System Governance & Documentation
│   └── approved_components_ledger.md         # 📜 Master Approved Components Repository Ledger
│
├── Advance ML Combination and Permutation Test/  # 🧪 16-Stage Controlled ML Laboratory Framework
│   ├── INDEX.md                              # Stage Guide (Stages 1 through 16)
│   ├── run_stage1_ablation.py to run_stage16_*.py
│
├── scripts/                                  # 🚀 Core Operational Scripts
│   ├── run_master_certified_production_backtest.py  # Definitive EURUSD Master Backtest Runner
│   ├── download_all_fx_histdata.py           # High-Speed Multi-Asset HistData Ingestion Pipeline
│   ├── run_paper_trading.py                  # Live Paper Trading Execution Engine
│   └── archive_experiments/                  # Archive of historical research/ablation experiments
│
├── app.py                                    # Interactive Streamlit Trading Laboratory UI
└── README.md                                 # Master Repository Documentation (This File)
```

---

## ⚡ Quick Start & Key Execution Commands

### 1. Run the Definitive Master Production Backtest (EURUSD ONLY - 0.75% Risk)
```bash
.venv/bin/python3 -u scripts/run_master_certified_production_backtest.py
```

### 2. Run High-Speed Multi-Asset HistData Ingestion Pipeline (2014-2025)
```bash
.venv/bin/python3 -u scripts/download_all_fx_histdata.py
```

### 3. Run the Complete 16-Stage Controlled ML Laboratory Suite
```bash
.venv/bin/python3 -u "Advance ML Combination and Permutation Test/run_stage14_final_production_certification.py"
.venv/bin/python3 -u "Advance ML Combination and Permutation Test/run_stage16_portfolio_risk_and_correlation_stress.py"
```

---

## 🏆 Key Master Backtest Results (EURUSD 0.75% Risk Allocation)

* **8-Year Walk-Forward OOS Gauntlet (2018–2025 EURUSD H1)**:
  - Starting Capital: **$10,000.00** $\longrightarrow$ Ending Equity: **$102,724.83** (**+927.25% Cumulative Net Return**)
  - **Annualized Sharpe Ratio**: **6.67**
  - **Max Drawdown (MDD)**: **14.54%**
  - **Profit Factor (PF)**: **1.15**
  - **Win Rate**: **52.51%** (4,020 trades)

* **100% Untouched Live 2026 Holdout Verification (Jan 1 – Aug 11, 2026)**:
  - Starting Capital: **$10,000.00** $\longrightarrow$ Ending Equity: **$13,499.07** (**+34.99% Net Return in 7.5 months**)
  - **2026 Sharpe Ratio**: **14.33**
  - **2026 Max Drawdown**: **4.99%**
  - **2026 Profit Factor**: **1.51** (234 trades)

---

## 📜 Master Approved Components Ledger

For a full historical track of every single stage experiment, p-value permutation test, and user-approved component, refer to [`docs/approved_components_ledger.md`](file:///Users/mahesh.patil/Desktop/Mahesh/ai-quant-lab/docs/approved_components_ledger.md).