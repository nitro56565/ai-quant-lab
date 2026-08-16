# 🎯 Strategy Specification

This document defines the exact mathematical trading logic for v3.2.

* **Entry Conditions:** 
  * HMM State must be favorable (Trend or Range).
  * Ensemble Probability must exceed PAE Thresholds.
* **PAE Thresholds:** 0.38 for Trend Regime, 0.42 for Range Regime.
* **Ensemble Weighting:** 50% CatBoost, 25% LightGBM, 25% XGBoost.
* **Risk/Reward:**
  * Stop Loss (SL): 1.5 ATR (14-period).
  * Take Profit (TP): 3.0 ATR (14-period) [Unused if EV exit triggers].
* **Position Sizing:** Fixed Fractional 0.75% risk per trade.
* **Capacity:** Maximum 3 open positions simultaneously.
* **Holding Period:** Maximum 36 hours.
* **Exit Conditions:** Stop Loss hit, Take Profit hit, Time stop (36h), or Opposite signal generated.
