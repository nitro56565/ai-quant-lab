# 🚀 AI Quant Lab - Master Certified Production Engine (`TRIPLE_STACKING_ENSEMBLE_v3.2`)

Welcome to **AI Quant Lab**, an institutional-grade, multi-regime quantitative machine learning framework for automated foreign exchange (FX) trading.

---

## 🏛️ Master Certified Production Architecture

```text
                          ┌────────────────────────────────────────────────────────┐
                          │   MASTER CERTIFIED PRODUCTION ARCHITECTURE (v3.2)      │
                          └────────────────────────────────────────────────────────┘
                                                       │
         ┌─────────────────────────────────────────────┼─────────────────────────────────────────────┐
         ▼                                             ▼                                             ▼
 ┌───────────────┐                             ┌───────────────┐                             ┌───────────────┐
 │ FEATURE MATRIX│                             │ REGIME ENGINE │                             │ MODEL ENSEMBLE│
 ├───────────────┤                             ├───────────────┤                             ├───────────────┤
 │ 70+ Technical │                             │ 4 Discretized │                             │ Weighted      │
 │ Indicators    │                             │ Regimes (2 HMM│                             │ Triple Stack  │
 │ (RSI, ATR, BB │                             │  Directional  │                             │ (Cat  50%     │
 │ ADX, MACD)    │                             │  x 2 Vol-Rank)│                             │  LGBM 25%     │
 └───────────────┘                             └───────────────┘                             │  XGB  25%)    │
                                                       │                                     └───────────────┘
                                                       ▼                                             │
                                               ┌───────────────┐                                     │
                                               │ PROBABILITY   │◄────────────────────────────────────┘
                                               │ THRESHOLDS    │
                                               ├───────────────┤
                                               │ Range: P>=0.42│
                                               │ Trend: P>=0.38│
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
├── core_machine_learning/                                # Directional HMM Regime Detector & ML Stacking Engine
├── historical_data_ingestion/                              # High-performance Parquet Multi-Timeframe Data Loader
├── execution_engine/                         # Limit Retrace Entry, Partial Exit & Order Management Engine
├── realtime_market_streaming/                     # Multi-Asset Data Ingestion, HistData Parser & Storage
├── research_and_training_engine/                          # 14 Technical Feature Matrix Builder & Triple Barrier Labeler
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

## 🏆 Frozen Master Canonical Production Benchmark (EURUSD 0.75% Risk Allocation)

* **MASTER CANONICAL PRODUCTION BACKTEST — v3.2 (FROZEN 🔒)**:
  - **8-Year Walk-Forward OOS Gauntlet (2018–2025 EURUSD H1)**:
    - **CAGR**: **+66.71%**
    - **Daily Sharpe Ratio ($\sqrt{252}$)**: **2.12**
    - **Daily Mark-to-Market MDD**: **22.34%**
    - **Profit Factor (PF)**: **1.72**
    - **Trades**: 2,458 completed trades

  - **100% Untouched Live 2026 Holdout Verification (Jan 1 – Aug 11, 2026)**:
    - **Return**: **+59.13%**
    - **2026 Daily Sharpe Ratio ($\sqrt{252}$)**: **4.32**
    - **2026 Mark-to-Market MDD**: **7.22%**
    - **2026 Profit Factor**: **3.19** 
    - **Trades**: 109 completed trades

---

## 📜 Master Approved Components Ledger

For a full historical track of every single stage experiment, p-value permutation test, and user-approved component, refer to [`docs/approved_components_ledger.md`](file:///Users/mahesh.patil/Desktop/Mahesh/ai-quant-lab/documentation_and_ledgers/approved_components_ledger.md).