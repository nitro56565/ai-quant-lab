# Master Institutional Production Environment — AI Quant Lab v5.0

This directory contains the **100% Finalized, Certified, and Frozen Production Infrastructure** for live trading execution, model artifacts, configuration, and canonical backtesting.

---

## 📂 Directory Layout

```text
production/
├── canonical_backtest/
│   ├── run_canonical_production_backtest.py  # Frozen Canonical Backtest Execution Script
│   ├── canonical_production_baseline.md      # Frozen Master Baseline Certificate (v1.0)
│   └── canonical_baseline_ledger.json        # Machine-Readable Baseline Metrics Ledger
├── config/
│   └── production_config.py                  # Live Trading & Pre-Trade Risk Configuration
├── live_engine/
│   ├── run_paper_trading.py                  # Live 24/7 OANDA Paper Trading Daemon Entrypoint
│   └── test_e2e_live_trading_pipeline.py     # Live Pipeline Integration Test Suite
└── README.md                                 # Production Environment Guide (This File)
```

---

## 🔒 Frozen Master Production Benchmark (v3.0 — 3 Concurrent Positions 🏆)

| Specification / Metric | Certified Production Baseline v3.0 Value |
| :--- | :--- |
| **Instrument / Timeframe** | **EURUSD H1** |
| **Out-of-Sample (OOS) Period** | **2018–2025 (8-Fold Walk-Forward)** |
| **Untouched Live Holdout** | **2026 (Jan 1 – Aug 11)** |
| **Ensemble Stacking Ratio** | **Ratio A (50% CatBoost / 25% LightGBM / 25% XGBoost)** |
| **Tree Regularization Depth** | **max_depth = 4 (Grid B Regularization)** |
| **Regime Engine** | **4-State Engine (2-State HMM $\times$ 2-State ATR Volatility Quantile)** |
| **Barrier Multipliers** | **Extended 3.0 ATR Take Profit / 1.5 ATR Stop Loss (36h Max Holding)** |
| **Risk Allocation Tier** | **0.75% Risk per Trade** ($75 risk on $10,000 base) |
| **Max Open Positions** | **3 Concurrent Positions** |
| **Transaction Friction** | **0.3 pips spread on every exit & partial exit + $7/lot commission** |
| **2018–2025 OOS Trades** | **5,651 Trades** |
| **2018–2025 Cumulative Return** | **+11,372.02% Net Return** |
| **CAGR** | **+80.98% / year** |
| **Daily Sharpe Ratio ($\sqrt{252}$)** | **2.29** |
| **Sortino Ratio** | **3.20** |
| **Profit Factor** | **1.47** |
| **Win Rate** | **51.55%** |
| **Mark-to-Market Max Drawdown** | **-21.61% (Daily MtM Peak)** |
| **2026 Holdout Net Return** | **+58.12%** (312 trades, 3.10 Sharpe, 1.52 PF, -6.81% MDD) |

---

## 🚀 Quick Commands

### 1. Verify Frozen Canonical Backtest
```bash
.venv/bin/python3 production/canonical_backtest/run_canonical_production_backtest.py
```

### 2. Run E2E Live Trading Integration Test
```bash
.venv/bin/python3 production/live_engine/test_e2e_live_trading_pipeline.py
```

### 3. Launch 24/7 Live Paper Trading Daemon
```bash
.venv/bin/python3 production/live_engine/run_paper_trading.py
```
