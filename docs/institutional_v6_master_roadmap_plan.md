# 🏛️ Master Architecture & Governance Roadmap Plan — AI Quant Lab v6.0

## 🎯 Executive Summary & User Directive

> [!IMPORTANT]
> **BACKTESTING-FIRST ISOLATION PROTOCOL**:
> Per your explicit instruction, **all 11 architectural phases will be developed, benchmarked, and validated strictly in BACKTESTING MODE FIRST** using the historical 12-year EURUSD H1 dataset (`2014–2026`) via `execution_engine/engine.py` and `scripts/run_master_institutional_backtest.py`.
> 
> **ZERO CHANGES** will touch the active paper trading daemon, Docker containers, or live OANDA gateway until you review the backtest benchmark scorecards and explicitly grant permission to promote to paper trading.

---

## 🔒 3-Tier Promotion Governance Pipeline

```mermaid
graph TD
    subgraph Tier 1: Backtesting & Research Isolation (ACTIVE STAGE)
        A1["1. Build Feature / Architecture in Research Engine"]
        A2["2. Run 12-Year Backtest (2014-2026)"]
        A3["3. Run 15-Path CPCV & Out-of-Sample Audit"]
        A4["4. Present Backtest Scorecard (PF, Sharpe, MDD, EV) to User"]
    end

    subgraph Tier 2: User Permission Gate (MANDATORY BARRIER)
        B1{"User Review & Approval?"}
    end

    subgraph Tier 3: Paper Trading & Live Promotion (LOCKED)
        C1["5. Deploy to Shadow Mode / Paper Trading Daemon"]
        C2["6. Run 300-500 Paper Trades Audit"]
        C3["7. Live OANDA Execution"]
    end

    Tier 1 --> Tier 2
    Tier 2 -- "Explicit User Permission Granted" --> Tier 3
    Tier 2 -- "Rejection / Tweaks Requested" --> Tier 1
```

---

## 🏛️ 11-Phase Backtest Implementation Roadmap

### Phase 1: Canonical `TradeDefinition` (Backtest Geometry Alignment)
* **Goal**: Unify trade geometry definitions across `research_engine/labeler.py`, `execution_engine/engine.py`, and `scripts/forensic_decision_replay.py`.
* **Backtest Verification**: Run 12-year backtest verifying that triple barrier labeler and backtest execution simulator use identical dynamic ATR SL/TP formulas.

---

### Phase 2: Data Integrity & Feed Validation Layer (Backtest Data Cleanliness)
* **Goal**: Validate historical dataset (`EURUSD_H1_2014_2026.parquet`) for missing bars, duplicate timestamps, weekend gaps, out-of-order bars, and spread anomalies prior to model training.
* **Component**: `live_trading_engine/data/data_validator.py`
* **Backtest Verification**: Run `DataIntegrityValidator` over 105,000+ historical H1 bars and generate a clean Data Health Report.

---

### Phase 3: Model & Experiment Governance Registries (Backtest Auditability)
* **Goal**: Wire `ModelRegistry` and `ExperimentRegistry` to log every backtest experiment (Model ID, Version, SHA256, Dataset Hash, Feature Schema, Hyperparameters, PSR, DSR, Git Commit).
* **Component**: `research_engine/governance.py` & `reports/backtest_governance_ledger.db`
* **Backtest Verification**: Query backtest governance database to trace any backtest trade back to its exact model binary and feature vector.

---

### Phase 4: Macro Intelligence Layer (104 Tech + 35 Macro = 139 Features in Backtest)
* **Goal**: Construct 35 historical Macro features (Central bank interest rate differentials $\Delta r$, CPI/NFP surprise deltas, VIX, DXY, Yield Curve slope) and benchmark LightGBM + CatBoost backtest performance.
* **Component**: `research_engine/macro_features.py`
* **Backtest AB Testing Harness**:
  * **Track A (Baseline)**: 104 Technical Features
  * **Track B (Macro-Enhanced)**: 139 Technical + Macro Features
* **Output**: Compare Profit Factor, Sharpe, Win Rate, and Max Drawdown side-by-side for user review.

---

### Phase 5: Market Regime Engine (`MarketState` in Backtest)
* **Goal**: Classify historical bars into 5-vector `MarketState` (Trend, Volatility, Liquidity, Macro Regime, Risk Sentiment) to condition ML predictions.
* **Component**: `research_engine/market_state.py`
* **Backtest Verification**: Evaluate backtest performance sliced across each individual market regime.

---

### Phase 6: Thesis Engine (Hourly Rationale Re-Evaluation in Backtest)
* **Goal**: Test dynamic hourly hypothesis validity scoring ($\text{Thesis Score} \in [0, 1]$) in backtesting.
* **Component**: `research_engine/thesis_engine.py`
* **Backtest AB Testing Harness**:
  * **Baseline**: Fixed PnL exits (TP at $+2.5\text{ATR}$, SL at $-2.0\text{ATR}$).
  * **Thesis Engine Exits**: Exiting early when $\text{Thesis Score} < 0.45$.
* **Output**: Compare Sharpe Ratio and Max Drawdown reduction in backtesting.

---

### Phase 7: Controlled Adaptive Position Management (Backtest Bounded Rules)
* **Goal**: Test bounded SL tightening, breakeven moves, and partial exits in backtesting.
* **Component**: `research_engine/adaptive_position_backtest.py`
* **Backtest Verification**: Verify zero portfolio risk inflation while quantifying trade holding time reduction.

---

### Phase 8: Portfolio Intelligence & Multi-Asset Risk Guardian (Multi-Pair Backtest)
* **Goal**: Run multi-pair correlation and factor exposure backtests across EURUSD, GBPUSD, USDJPY, and XAUUSD.
* **Component**: `research_engine/portfolio_backtest.py`
* **Backtest Verification**: Verify portfolio correlation caps prevent cluster losses in backtest history.

---

### Phase 9: Shadow Mode Engine (Silent Candidate Model Backtest)
* **Goal**: Benchmark candidate models against production certified models across historical out-of-sample walk-forward folds (2022–2026).
* **Component**: `research_engine/shadow_backtest.py`

---

### Phase 10: Extended 25-Gate Deterministic Adaptive Forensic Replay
* **Goal**: Extend backtest forensic replay to 25 gates validating macro feature parity, thesis score parity, and adaptive exit parity.
* **Component**: `scripts/forensic_decision_replay.py`

---

### Phase 11: Production Governance & Maturity Matrix
* **Goal**: Tag backtest research outputs with explicit maturity levels (`v6.0-Research-Backtest`).

---

## 🏆 Backtest Implementation Order

```text
===================================================================================================
PRIORITY LEVEL | BACKTEST MODULE                       | RESEARCH & BACKTESTING GOAL
===================================================================================================
1. ⭐⭐⭐⭐⭐   | Canonical TradeDefinition             | Unified backtest geometry across labeler & engine
2. ⭐⭐⭐⭐⭐   | Data Integrity & Feed Validator       | Validate 12-year EURUSD H1 dataset (2014-2026)
3. ⭐⭐⭐⭐⭐   | Model & Experiment Governance         | Log backtest metrics & dataset SHA256 hashes
4. ⭐⭐⭐⭐☆   | Macro Intelligence Adapter            | AB Test 104 Tech vs 139 Tech+Macro features
5. ⭐⭐⭐⭐☆   | Market Regime Engine                  | Evaluate backtest performance per MarketState
6. ⭐⭐⭐⭐☆   | Thesis Engine                         | Compare static PnL exits vs Thesis Score exits
7. ⭐⭐⭐☆☆   | Adaptive Position Management          | Test bounded SL tightening & breakeven moves
8. ⭐⭐⭐☆☆   | Portfolio Intelligence                | Multi-pair correlation backtest (EUR/GBP/JPY/Gold)
9. ⭐⭐⭐☆☆   | Shadow Mode Engine                    | Benchmark candidate models in out-of-sample backtest
10. ⭐⭐☆☆☆   | Extended 25-Gate Forensic Replay      | 100% deterministic backtest trade replay
11. ⭐⭐☆☆☆   | Governance Maturity Matrix            | Enforce v6.0-Research-Backtest maturity tagging
===================================================================================================
```

---

## 🧪 Verification & Backtest Benchmark Metrics

After each backtest phase is executed, a detailed **Backtest Performance Scorecard** will be presented to you:

$$\begin{array}{|l|c|c|c|}
\hline
\textbf{Metric} & \textbf{v5.0 Certified Baseline} & \textbf{v6.0 Backtest Candidate} & \textbf{Delta / Status} \\
\hline
\text{Cumulative Net PnL} & +\$43,257.58 & \text{Backtest Result} & \text{Evaluated} \\
\text{CAGR (\% / year)} & +23.26\% & \text{Backtest Result} & \text{Evaluated} \\
\text{Profit Factor (PF)} & 1.61 & \text{Backtest Result} & \text{Evaluated} \\
\text{Sharpe Ratio} & 2.29 & \text{Backtest Result} & \text{Evaluated} \\
\text{Max Drawdown (\%)} & 5.76\% & \text{Backtest Result} & \text{Evaluated} \\
\text{Expected Value (EV)} & +\$15.12/\text{trade} & \text{Backtest Result} & \text{Evaluated} \\
\hline
\end{array}$$

---

## 👤 User Review & Permission Protocol

> [!IMPORTANT]
> **BACKTEST ISOLATION GUARANTEE**:
> All work will be performed strictly inside `research_engine/` and `scripts/run_v6_backtest_suite.py`. No changes will be deployed to Paper Trading or Docker until you review the backtest scorecard above and give explicit permission.
