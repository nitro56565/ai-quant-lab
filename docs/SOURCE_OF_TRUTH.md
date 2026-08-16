# 💎 SOURCE_OF_TRUTH.md

**CRITICAL RULE:** If a claim or metric conflicts with this document, inspect the code and reproduce the result. Do not choose whichever number appears most recently in a conversation or an old report.

---

## CURRENT PRODUCTION:
*   **Version:** v3.3 (Master Canonical)
*   **Instrument:** EURUSD
*   **Timeframe:** H1 (Alpha Generation) + 1m High-Fidelity Execution Simulator. Note: System uses Aggressive Market Execution. 0.25 ATR pending limit logic was proven mathematically inferior and deprecated.
*   **Risk:** 0.75% Fixed-Fractional (Note: Live forward testing explicitly hardcodes a $10k base capital for 1-to-1 backtest parity, but production architecture dynamically compounds equity.)
*   **Max positions:** 3
*   **Spread/Slippage:** Modeled explicitly in execution engine
*   **Commission:** $7 per lot

## CANONICAL BACKTEST (OOS High-Fidelity Market Execution):
*   **Period:** 2018–2025 (8 Years)
*   **Trades:** 3,062
*   **CAGR:** +72.21%
*   **Sharpe Ratio:** 2.06 (Daily)
*   **Profit Factor (PF):** 1.71
*   **Maximum Drawdown (MDD):** 27.05%

## 2026 UNTOUCHED HOLDOUT (Market Execution):
*   **Period:** Jan 1, 2026 – Aug 11, 2026
*   **Trades:** 129
*   **Return:** +70.83%
*   **Sharpe Ratio:** 4.48 (Daily)
*   **Profit Factor (PF):** 3.22
*   **Maximum Drawdown (MDD):** 5.99%

## CURRENT CHALLENGER:
*   **None.** v3.3 is the undisputed master. No challenger is currently being actively tested.

---

## 🚫 DO NOT TRUST:
*   Old JSON reports in `docs/archived_reports/`
*   Any legacy Markdown reports stating +927% or +841% returns.
*   Any obsolete experiments or superseded metrics found in old `.txt` files.
*   Any claims that conflict with the numbers in this document.
