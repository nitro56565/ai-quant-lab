# 🏛️ Architecture Specification

The system is strictly segmented to ensure isolation between research and production.

### Data Flow Pipeline
1. `Data` -> `Feature Engineering`
2. `H4 Macro Context` (Shifted by 1 bar to prevent leakage) -> `H1 Features`
3. `LightGBM/CatBoost/XGBoost` -> `Ensemble`
4. `HMM Regime` (4 States)
5. `PAE Decision Guard` (Probability Approval Engine)
6. `Decision Engine` (EV Calculation)
7. `Risk Guardian` (Position Sizing)
8. `Order Manager`
9. `OANDA Broker`

### Component Responsibilities
* **core_feature_engineering:** Only calculates indicators. Has no concept of trades.
* **core_machine_learning:** Only predicts probabilities. Has no concept of money.
* **live_execution_engine:** Only manages state and risk. Never recalculates features.
