# 🔴 Master Red-Team & Adversarial Stress Test Report — Combo #271

## Operational Compliance Checklist
- [x] Production code (`run_production_baseline_v2_combo271.py`) frozen and unmodified
- [x] Baseline Control reproduced bit-identically (2,267 trades / +918.07% Net Return / 2.33 Sharpe / 1.40 PF / -12.71% MDD)
- [x] Category 1 & 2 tested environmental & data degradation ONLY (Zero strategy changes)
- [x] Deterministic random seed (42) applied across all stochastic attacks
- [x] Executed 100% offline

## Unified Adversarial Scorecard Matrix

| Category | Attack Vector | Parameter / Intensity | Trades | CAGR | Sharpe | PF | MDD | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CONTROL | Certified Baseline v2.0 | Spread 0.3p, Comm $7, Base | 2267 | +33.68% | 2.33 | 1.40 | -12.71% | 🟢 ROBUST |
| Category 1 | Spread Expansion | 0.5 pips | 2267 | +30.23% | 2.12 | 1.36 | -14.61% | 🟡 DEGRADED |
| Category 1 | Spread Expansion | 1.0 pips | 2267 | +21.93% | 1.59 | 1.25 | -19.30% | 🟠 STRESSED |
| Category 1 | Spread Expansion | 2.0 pips | 2267 | +6.88% | 0.56 | 1.07 | -27.77% | 🔴 BROKEN |
| Category 1 | Spread Expansion | 3.0 pips | 2267 | +-6.23% | -0.42 | 0.94 | -59.34% | 🔴 BROKEN |
| Category 1 | Spread Expansion | 5.0 pips | 2267 | +-27.56% | -2.14 | 0.73 | -93.10% | 🔴 BROKEN |
| Category 1 | Adverse Slippage | 0.5 pips | 2267 | +25.18% | 1.80 | 1.29 | -17.43% | 🟠 STRESSED |
| Category 1 | Adverse Slippage | 1.0 pips | 2267 | +17.27% | 1.28 | 1.19 | -21.94% | 🔴 BROKEN |
| Category 1 | Adverse Slippage | 2.0 pips | 2267 | +2.73% | 0.26 | 1.03 | -34.42% | 🔴 BROKEN |
| Category 1 | Adverse Slippage | 5.0 pips | 2267 | +-30.52% | -2.38 | 0.71 | -94.76% | 🔴 BROKEN |
| Category 1 | Commission Inflation | $15/lot | 2267 | +24.33% | 1.76 | 1.29 | -17.45% | 🟠 STRESSED |
| Category 1 | Commission Inflation | $30/lot | 2267 | +8.43% | 0.69 | 1.09 | -25.69% | 🔴 BROKEN |
| Category 1 | Commission Inflation | $50/lot | 2267 | +-9.48% | -0.72 | 0.90 | -66.54% | 🔴 BROKEN |
| Category 1 | Execution Latency | 1 Bar (1h) | 2426 | +17.54% | 1.27 | 1.20 | -16.28% | 🟠 STRESSED |
| Category 1 | Execution Latency | 2 Bar (2h) | 2459 | +8.02% | 0.63 | 1.08 | -26.31% | 🔴 BROKEN |
| Category 1 | Execution Latency | 3 Bar (3h) | 2532 | +6.37% | 0.51 | 1.06 | -29.30% | 🔴 BROKEN |
| Category 1 | Dropped Limit Orders | 5% Missed Fills | 2240 | +30.60% | 2.16 | 1.37 | -13.41% | 🟡 DEGRADED |
| Category 1 | Dropped Limit Orders | 10% Missed Fills | 2196 | +31.37% | 2.26 | 1.40 | -13.16% | 🟡 DEGRADED |
| Category 1 | Dropped Limit Orders | 20% Missed Fills | 2149 | +24.34% | 1.78 | 1.30 | -13.80% | 🟡 DEGRADED |
| Category 1 | Dropped Limit Orders | 30% Missed Fills | 2039 | +18.43% | 1.44 | 1.23 | -16.95% | 🟠 STRESSED |
| Category 1 | Combined Execution Shock | Spread 3p + Slip 2p + Comm $30 + 1h Lat + 20% Missed | 2265 | +-82.24% | -0.26 | 0.50 | -105.06% | 🔴 BROKEN |
| Category 2 | HMM State Corruption | 10% Random State Flip | 2483 | +34.20% | 2.22 | 1.39 | -15.10% | 🟠 STRESSED |
| Category 2 | HMM State Corruption | 20% Random State Flip | 2619 | +31.35% | 2.02 | 1.32 | -17.04% | 🟠 STRESSED |
| Category 2 | HMM State Corruption | 30% Random State Flip | 2694 | +28.99% | 1.87 | 1.29 | -18.02% | 🟠 STRESSED |
| Category 2 | HMM State Corruption | 50% Random State Flip | 2790 | +31.73% | 1.99 | 1.31 | -16.93% | 🟠 STRESSED |
| Category 2 | PAE Noise Injection | N(0, 0.05) Noise | 3625 | +28.75% | 1.71 | 1.23 | -14.47% | 🟡 DEGRADED |
| Category 2 | PAE Noise Injection | N(0, 0.10) Noise | 5195 | +41.71% | 2.12 | 1.26 | -10.59% | 🟡 DEGRADED |
| Category 2 | PAE Noise Injection | N(0, 0.20) Noise | 6543 | +35.34% | 1.79 | 1.17 | -20.06% | 🔴 BROKEN |
| Category 2 | PAE Noise Injection | N(0, 0.30) Noise | 6945 | +33.71% | 1.69 | 1.17 | -20.22% | 🔴 BROKEN |
| Category 2 | Stale Feature Lag | 1 Bar Data Lag | 2394 | +16.70% | 1.23 | 1.19 | -15.99% | 🟠 STRESSED |
| Category 2 | Stale Feature Lag | 2 Bar Data Lag | 2458 | +13.25% | 0.98 | 1.13 | -22.90% | 🔴 BROKEN |
| Category 2 | Stale Feature Lag | 3 Bar Data Lag | 2501 | +4.23% | 0.37 | 1.04 | -35.34% | 🔴 BROKEN |
| Category 2 | Black Swan Vol Shock | 1% Bars @ 5x ATR | 2291 | +34.73% | 2.38 | 1.42 | -13.13% | 🟡 DEGRADED |
| Category 2 | Black Swan Vol Shock | 5% Bars @ 5x ATR | 2335 | +30.73% | 2.18 | 1.39 | -13.53% | 🟡 DEGRADED |
| Category 2 | Black Swan Vol Shock | 5% Bars @ 10x ATR | 2364 | +31.20% | 2.36 | 1.47 | -17.56% | 🟠 STRESSED |
| Category 3 | TP Target Reduction | TP 2.5 ATR | 2403 | +32.00% | 2.20 | 1.36 | -14.43% | 🟡 DEGRADED |
| Category 3 | TP Target Reduction | TP 2.0 ATR | 2621 | +33.54% | 2.27 | 1.37 | -17.87% | 🟠 STRESSED |
| Category 3 | TP Target Reduction | TP 1.5 ATR | 2888 | +33.01% | 2.39 | 1.35 | -15.76% | 🟠 STRESSED |
| Category 3 | TP Target Reduction | TP 1.0 ATR | 3335 | +22.09% | 1.88 | 1.26 | -16.42% | 🟠 STRESSED |
| Category 3 | SL Distance Expansion | SL 2.0 ATR | 2084 | +27.81% | 2.23 | 1.41 | -9.82% | 🟢 ROBUST |
| Category 3 | SL Distance Expansion | SL 2.5 ATR | 1964 | +24.88% | 2.35 | 1.47 | -7.22% | 🟢 ROBUST |
| Category 3 | SL Distance Expansion | SL 3.0 ATR | 1865 | +21.19% | 2.36 | 1.49 | -7.21% | 🟢 ROBUST |
| Category 3 | Holding Window Truncation | 24 Hours Max | 2300 | +32.70% | 2.27 | 1.38 | -13.35% | 🟡 DEGRADED |
| Category 3 | Holding Window Truncation | 18 Hours Max | 2375 | +32.79% | 2.25 | 1.37 | -15.09% | 🟠 STRESSED |
| Category 3 | Holding Window Truncation | 12 Hours Max | 2529 | +32.75% | 2.26 | 1.39 | -9.22% | 🟢 ROBUST |
| Category 3 | Holding Window Truncation | 6 Hours Max | 2924 | +31.94% | 2.24 | 1.34 | -13.34% | 🟡 DEGRADED |
| Category 3 | PAE Hurdle Shift | Bull 0.50 / Bear 0.45 | 646 | +17.71% | 2.29 | 1.84 | -5.95% | 🟢 ROBUST |
| Category 3 | PAE Hurdle Shift | Bull 0.35 / Bear 0.30 | 4839 | +29.27% | 1.56 | 1.13 | -18.31% | 🟠 STRESSED |
| Category 3 | PAE Hurdle Shift | Bull 0.20 / Bear 0.20 | 5994 | +1.74% | 0.17 | 1.01 | -53.27% | 🔴 BROKEN |
| Category 3 | Parameter Perturbation | -30% ATR Scaling | 2895 | +32.72% | 1.97 | 1.28 | -12.61% | 🟡 DEGRADED |
| Category 3 | Parameter Perturbation | -19% ATR Scaling | 2629 | +33.05% | 2.08 | 1.30 | -16.48% | 🟠 STRESSED |
| Category 3 | Parameter Perturbation | -9% ATR Scaling | 2423 | +33.66% | 2.22 | 1.35 | -15.91% | 🟠 STRESSED |
| Category 3 | Parameter Perturbation | +10% ATR Scaling | 2121 | +31.42% | 2.30 | 1.40 | -12.14% | 🟢 ROBUST |
| Category 3 | Parameter Perturbation | +19% ATR Scaling | 2009 | +31.99% | 2.47 | 1.45 | -9.16% | 🟢 ROBUST |
| Category 3 | Parameter Perturbation | +30% ATR Scaling | 1927 | +27.16% | 2.22 | 1.42 | -9.33% | 🟢 ROBUST |

## ⚠️ Failure Threshold Summary (Point of Breakdown)
- **Category 1 — Spread Expansion (2.0 pips)**: Broke strategy with +6.88% CAGR, 0.56 Sharpe, 1.07 PF, -27.77% MDD
- **Category 1 — Spread Expansion (3.0 pips)**: Broke strategy with +-6.23% CAGR, -0.42 Sharpe, 0.94 PF, -59.34% MDD
- **Category 1 — Spread Expansion (5.0 pips)**: Broke strategy with +-27.56% CAGR, -2.14 Sharpe, 0.73 PF, -93.10% MDD
- **Category 1 — Adverse Slippage (1.0 pips)**: Broke strategy with +17.27% CAGR, 1.28 Sharpe, 1.19 PF, -21.94% MDD
- **Category 1 — Adverse Slippage (2.0 pips)**: Broke strategy with +2.73% CAGR, 0.26 Sharpe, 1.03 PF, -34.42% MDD
- **Category 1 — Adverse Slippage (5.0 pips)**: Broke strategy with +-30.52% CAGR, -2.38 Sharpe, 0.71 PF, -94.76% MDD
- **Category 1 — Commission Inflation ($30/lot)**: Broke strategy with +8.43% CAGR, 0.69 Sharpe, 1.09 PF, -25.69% MDD
- **Category 1 — Commission Inflation ($50/lot)**: Broke strategy with +-9.48% CAGR, -0.72 Sharpe, 0.90 PF, -66.54% MDD
- **Category 1 — Execution Latency (2 Bar (2h))**: Broke strategy with +8.02% CAGR, 0.63 Sharpe, 1.08 PF, -26.31% MDD
- **Category 1 — Execution Latency (3 Bar (3h))**: Broke strategy with +6.37% CAGR, 0.51 Sharpe, 1.06 PF, -29.30% MDD
- **Category 1 — Combined Execution Shock (Spread 3p + Slip 2p + Comm $30 + 1h Lat + 20% Missed)**: Broke strategy with +-82.24% CAGR, -0.26 Sharpe, 0.50 PF, -105.06% MDD
- **Category 2 — PAE Noise Injection (N(0, 0.20) Noise)**: Broke strategy with +35.34% CAGR, 1.79 Sharpe, 1.17 PF, -20.06% MDD
- **Category 2 — PAE Noise Injection (N(0, 0.30) Noise)**: Broke strategy with +33.71% CAGR, 1.69 Sharpe, 1.17 PF, -20.22% MDD
- **Category 2 — Stale Feature Lag (2 Bar Data Lag)**: Broke strategy with +13.25% CAGR, 0.98 Sharpe, 1.13 PF, -22.90% MDD
- **Category 2 — Stale Feature Lag (3 Bar Data Lag)**: Broke strategy with +4.23% CAGR, 0.37 Sharpe, 1.04 PF, -35.34% MDD
- **Category 3 — PAE Hurdle Shift (Bull 0.20 / Bear 0.20)**: Broke strategy with +1.74% CAGR, 0.17 Sharpe, 1.01 PF, -53.27% MDD
