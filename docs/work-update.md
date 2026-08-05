# July 23, 2026 - 18:10:37 (UTC+05:30)

## Summary of Last Project Developments

This document provides a record of the developments completed during the last session on the **AI Quant Lab** quantitative backtesting and research platform.

---

### 1. 🔬 ML Consensus & Expected Value (EV) Strategy
We designed and implemented the [MLConsensusStrategy](file:///Users/mahesh.patil/Desktop/Mahesh/ai-quant-lab/strategy_engine/ml_consensus.py):
* **Feature Generation:** Computes over 65 market features on H1 bar data using the feature matrix builder.
* **Rolling Forward-Walk Prediction:** Simulates a rolling out-of-sample prediction workflow by training models on a rolling 4-year window to predict outcomes for the subsequent year.
* **Multi-Target Prediction:**
  * **Classifier:** Predicts the probability $P(\text{HIGH})$ of a high-quality directional Long setup.
  * **Regressors:** Predicts the Expected Maximum Favorable Excursion (MFE) and Expected Maximum Adverse Excursion (MAE).
* **Expected Value Sizing:** Computes expected value (EV) in pips: 
  $$EV = P(\text{HIGH}) \times MFE - (1 - P(\text{HIGH})) \times MAE$$
* **Entry Filters:** Enters LONG trades when the predicted EV exceeds a threshold (dynamically calibrated to the top 1% of predicted EV) and filters out hours within the high-chop NY session overlap (13:00 to 16:00 UTC).

### 2. 🛡️ The Quant Gauntlet Research Suite
We built [run_quant_gauntlet.py](file:///Users/mahesh.patil/Desktop/Mahesh/ai-quant-lab/run_quant_gauntlet.py) to run a rigorous evaluation protocol to stress-test the model's out-of-sample edge:
* **Out-of-Sample splits:** Segmented tests across 4 years (Split 1: 2022, Split 2: 2023, Split 3: 2024, Split 4: 2025-26).
* **Probability Calibration:** Analyzed predicted probabilities in confidence bins (0.0 to 1.0) against actual win rates. High confidence signals ($>60\%$) correlated with positive expected outcomes.
* **Multi-Model Robustness:** Trained five models (Random Forest, HistGradient Boosting, Extra Trees, Logistic Regression, Ridge) to identify consensus features. Volatility measures (`feat_vol_atr_pct`, `feat_vol_atr_ratio`) were discovered as the primary predictive signals across all models.
* **Session Effect & NY Overlap Validation:** Confirmed that the NY London session overlap hours (13:00 to 16:00 UTC) suffer from lower out-of-sample win rates and negative average returns due to dual-direction liquidity sweeps.

### 3. ⚙️ Execution Engine & Dashboard Integration
* **Dynamic Target Sizing:** Updated [ExecutionEngine](file:///Users/mahesh.patil/Desktop/Mahesh/ai-quant-lab/execution_engine/engine.py#L80) to set stop losses (SL) and take profits (TP) dynamically using the ML model's predicted MAE and MFE values.
* **Time-Based Exit:** Configured a hard close of positions after 12 hours (matching the model's prediction horizon).
* **Dashboard Support:** Wired `MLConsensusStrategy` into the main application runner in [app.py](file:///Users/mahesh.patil/Desktop/Mahesh/ai-quant-lab/app.py) so it can be evaluated dynamically through the simulator dashboard.

### 4. 📊 Analysis & Audit Documentation
Two main research reports were produced during the pipeline audit:
* [pipeline_audit_report.md](file:///Users/mahesh.patil/.gemini/antigravity-cli/brain/622a334f-7130-426c-8af3-6b2a1931e25c/pipeline_audit_report.md) — Audited execution constraints, confirming that the backtester rejects many raw signals due to the single active position limit (blocking momentum clusters).
* [quant_gauntlet_results.md](file:///Users/mahesh.patil/.gemini/antigravity-cli/brain/622a334f-7130-426c-8af3-6b2a1931e25c/quant_gauntlet_results.md) — Recorded rolling walk performance (ranging from 63.6% to 67.2% out-of-sample classifier accuracy) and validated capital allocation sizing.
