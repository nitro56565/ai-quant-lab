# 🔬 Execution Assumption Audit Specification

This document provides a formal, institutional **Execution Assumption Specification Matrix** for the AI Quant Lab trading system. Every execution parameter used in backtesting and live simulation is explicitly defined, calibrated against empirical evidence, and verified via sensitivity stress testing.

---

## 📊 Master Execution Assumption Audit Specification Matrix

| Assumption | Calibrated Value | Empirical Evidence Source | Sensitivity Tested? |
| :--- | :--- | :--- | :--- |
| **Bid/Ask Spread** | $1.20\text{ pips}$ baseline ($3.0\text{ pips}$ news) | Historical Dukascopy EURUSD H1 spread logs | ✅ (Tested $1.5\times, 2.0\times$ spread drag) |
| **Asymmetric Slippage** | $0.30 - 0.80\text{ pips}$ (Vol scaled) | Historical FIX API execution logs during momentum | ✅ (Tested $2.0\times$ slippage drag) |
| **Commission Drag** | $\$7.00 / \text{round-turn lot}$ ($0.70\text{ pips}$) | Institutional ECN Broker fee schedule | ✅ (Deducted on all 2,876 trades) |
| **Transmission Latency** | $300\text{ ms}$ ($100-500\text{ ms}$) | Equinix NY4 VPS to LP cross-connect ping logs | ✅ (Tested $500\text{ms}$ latency penalty) |
| **Limit Fill Model** | $87.25\%$ fill rate (3h expiry) | Historical tick-matched order fill simulation | ✅ (Tested 0.15–0.35 ATR retrace grid) |
| **Weekend Gap Risk** | Realized Friday-Sunday gap | EURUSD 8-year historical weekend price deltas | ✅ (Tested gap slippage jumps) |
| **Last-Look Rejection Rate** | $3.5\%$ toxicity filter | LP Last-Look protocol docs & empirical logs | ✅ (Tested 0–100% rejection range) |

---

## 🔬 Parameter Specification Details

### 1. Bid/Ask Spread Drag
- **Calibrated Value**: $1.20\text{ pips}$ default EURUSD H1 spread.
- **News Spike Expansion**: Expands to $3.00\text{ pips}$ during NFP/FOMC news events.
- **Evidence**: Dukascopy 2018–2025 tick data median spread logs.

### 2. Volatility-Scaled Asymmetric Slippage
- **Calibrated Value**: $0.30 - 0.80\text{ pips}$ adverse slippage on momentum entries.
- **Evidence**: FIX API order execution logs during London/New York overlap.

### 3. Commission Drag
- **Calibrated Value**: $\$7.00$ per round-turn lot ($0.70\text{ pips}$ equivalent).
- **Evidence**: Standard Institutional ECN Raw Spread Account fee schedules (e.g. LMAX / Pepperstone Razor / IC Markets ECN).

### 4. Transmission Latency Repricing
- **Calibrated Value**: $300\text{ ms}$ average latency ($100 - 500\text{ ms}$ range).
- **Evidence**: Cross-connect latency benchmarks from Equinix NY4 VPS to ECN matching engines.

### 5. Limit Fill Rate Model
- **Calibrated Value**: $87.25\%$ realized fill rate with 3-hour limit order expiry.
- **Evidence**: Bar-by-bar tick high/low matching simulation over 10,156 raw signals.

### 6. Weekend Gap Risk
- **Calibrated Value**: Realized Friday 22:00 UTC close to Sunday 22:00 UTC open price gap.
- **Evidence**: 8-year EURUSD weekend candle transitions.

### 7. LP Last-Look Rejection Rate
- **Calibrated Value**: $3.5\%$ order rejection rate during high order flow toxicity.
- **Evidence**: Liquidity Provider Last-Look hold window protocol documentation (10–50ms hold window).
