# 📜 Backtest Protocol

**No experiment is considered valid unless it follows this protocol.**

### Periods
* **Training/Optimization:** 2014-2017
* **Out-Of-Sample (OOS):** 2018-2025 (8-Year Walk-Forward)
* **Untouched Holdout:** 2026 (Jan-Aug)

### Friction Assumptions
* **Commission:** $3 per lot per side.
* **Spread/Slippage:** 0.5 to 1.0 pips modeled via entry degradation.

### Metrics
* All decisions must optimize for **Sortino Ratio** first, **Max Drawdown (MDD)** second, and **CAGR** third.
