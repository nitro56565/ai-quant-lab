# 🤖 AI Agent Operating Manual (AGENTS.md)

This document is the highest-priority instruction set for any AI Agent working on this repository. Read and follow these directives absolutely.

## 📌 1. What this project is
AI Quant Lab is a fully autonomous, institutional-grade algorithmic trading system for the **EURUSD** forex market. It uses Walk-Forward optimized Machine Learning (LightGBM/CatBoost/XGBoost) combined with a 4-State HMM Regime detector to execute high-conviction trades via the OANDA REST API.

## 📌 2. Current Canonical Production Version
The current master canonical version is **v3.3**. It is strictly **FROZEN**.

## 📌 3. Where Everything Lives (Repository Structure)
* **Where the strategy lives:** `docs/STRATEGY_SPEC.md` (Read this to understand EXACTLY what constitutes a trade).
* **Where backtesting lives:** `research_and_training_engine/` (Offline Walk-Forward optimization and strategy testing).
* **Where live execution lives:** `live_execution_engine/` (Real-time OANDA daemon, Risk Guardian, Order Manager).
* **Stateless Core Libraries:** `core_machine_learning/` and `core_feature_engineering/`.
* **Data Pipelines:** `historical_data_ingestion/` and `realtime_market_streaming/`.
* **Outputs & Ledgers:** `local_data_workspace/`.
* **Agent Documentation:** `docs/` (Contains BACKTEST_PROTOCOL, DATA_SPEC, ML_SPEC, etc.)

## 📌 4. Frozen Files / Parameters
* **Frozen Parameters:** All v3.3 parameters (PAE thresholds 0.38/0.42, 1.5 ATR SL, 0.75% Risk) are locked. **Never silently modify production parameters.**
* **Frozen Files:** The master weights at `trained_model_artifacts/production_deployment/model_suite.joblib` are frozen production assets.

## 🔒 5. OOS & Holdout Rules (Data Sanctity)
* **Never mix OOS (Out-of-Sample) and In-Sample data.**
* **Never modify the 2026 Holdout data during research.** 2026 is strictly reserved for untouched validation.
* **Never use future information.** Lookahead bias is fatal. H4 data must remain shifted by 1 bar before merging with H1.

## 🛑 6. Critical Agent Behavioral Rules
You must strictly obey the following rules when interacting with this repository and the user:
1. **Never invent metrics.** If you do not have the exact number from a ledger or script output, do not guess. Say you need to calculate it.
2. **Never claim a test passed without actually running it.** You must physically run the command and see the success logs before claiming success.
3. **Always inspect existing implementation before proposing changes.** Do not guess how a component works; read the actual code first.
4. **When uncertain, say "I don't know" and investigate.** Do not hallucinate fixes or guess file locations.

## 🛠️ 7. Exact Commands to Run
* **Run Live Trading Daemon:** `python3 production_deployment/live_engine/run_paper_trading.py`
* **Run E2E Sanity Test:** `python3 production_deployment/live_engine/test_e2e_live_trading_pipeline.py`
* **Retrain Frozen Models:** `python3 production_deployment/scripts/train_and_export_baseline_v3.py`
