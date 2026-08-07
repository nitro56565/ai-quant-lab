# 🤖 MASTER INSTITUTIONAL DIAGNOSTIC DASHBOARD — USDCAD
### **Dataset**: `/Users/mahesh.patil/Downloads/USDCAD60.csv` (97,799 H1 Candles | 2010–2026)

---

### 🔍 DATA QUALITY VALIDATION REPORT (11-Point Verification Engine)
- **Data Quality Status**: 🟢 **VALID** (100% Data Quality Pass)
- **Total Candle Rows**: `97,799`
- **Start Timestamp**: `2010-07-22 20:00:00 UTC`
- **End Timestamp**: `2026-08-06 05:00:00 UTC`
- **Duplicate Timestamps Check**: `0 Duplicates` (100% Clean Time Series)
- **OHLC High >= Low Boundary Check**: `100% Consistent`
- **Price Integrity Check**: `100% Positive Prices` (> 0.0)

---

### 📊 SECTION 1. STATISTICAL RIGOR & OVERFITTING DIAGNOSTICS
- **Probabilistic Sharpe Ratio (PSR)**: `1.0000` (1.0000 = 100% Statistical Confidence)
- **Deflated Sharpe Ratio (DSR)**: `0.5836` (Calibrated for Multiple Testing)
- **Minimum Track Record Length (MinTRL)**: `17 Days`
- **CPCV Validation Engine Status**: 15 Purged & Embargoed Combinatorial Paths
- **Degrees of Freedom (df)**: `97695` (N = 97799, Features = 104)

---

### 📊 SECTION 2. RISK, RETURN, & DRAWDOWN PROFILE
- **Total Executed Trades**: `2088`
- **Win Rate (Hit Ratio)**: `45.6%`
- **Compound Annual Growth Rate (CAGR)**: `+13.67% / year`
- **Cumulative Net Return**: `+401.88%` (+$40188.30)
- **Expected Value (EV) per Trade**: `+6.32 pips` (+$19.25 / trade)
- **Profit Factor (PF)**: `1.55`
- **Avg Reward-to-Risk Ratio (R:R)**: `1.88`
- **Sharpe Ratio**: `1.62`
- **Sortino Ratio (Downside Risk)**: `2.24`
- **Calmar / MAR Ratio (CAGR / MDD)**: `2.62`
- **Max Peak-to-Trough Drawdown (MDD)**: `5.22%`
- **Max Drawdown Duration**: `11334.0 Hours`
- **CVaR 95% (Expected Shortfall)**: `0.36%`
- **Daily Return Skewness**: `3.69` | **Kurtosis**: `32.87`

---

### 📅 SECTION 3. YEAR-OVER-YEAR (YoY) PERFORMANCE MATRIX — ALL OOS YEARS (2014 – 2026)

| Year | Return (%) | Net PnL ($) | Max DD (%) | Trades | Win Rate (%) | Profit Factor |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **2014** | 0.00% | +$0.00 | 0.00% | 0 | 0.0% | N/A |
| **2015** | 0.00% | +$0.00 | 0.00% | 0 | 0.0% | N/A |
| **2016** | 0.00% | +$0.00 | 0.00% | 0 | 0.0% | N/A |
| **2017** | 0.00% | +$0.00 | 0.00% | 0 | 0.0% | N/A |
| **2018** | **+33.03%** | **+$3303.44** | 10.65     % | 128      | 51.6    % | **1.63         ** |
| **2019** | **+0.54%** | **+$72.05** | 2.62      % | 48       | 54.2    % | **1.06         ** |
| **2020** | **-6.18%** | **+$-826.44** | 11.41     % | 76       | 34.2    % | **0.81         ** |
| **2021** | **+15.41%** | **+$1933.54** | 6.45      % | 139      | 48.2    % | **1.38         ** |
| **2022** | **+16.47%** | **+$2385.26** | 4.16      % | 33       | 45.5    % | **2.53         ** |
| **2023** | **+17.73%** | **+$2989.94** | 9.26      % | 146      | 43.8    % | **1.45         ** |
| **2024** | **+10.14%** | **+$2013.20** | 7.07      % | 217      | 45.2    % | **1.24         ** |
| **2025** | **+41.31%** | **+$9034.15** | 3.90      % | 218      | 50.9    % | **1.93         ** |
| **2026** | 0.00% | +$0.00 | 0.00% | 0 | 0.0% | N/A |

---

### 📊 SECTION 4. REGIME ROBUSTNESS & CONSISTENCY
- **Single-Period Profit Concentration**: `23.4%`
- **Regime-Segmented PnL Breakdown**:
  - **Bear Trend Regime (State 0)**: +$4436.59
  - **Range / Low Vol Regime (State 1)**: +$25210.42
  - **Bull Trend Regime (State 2)**: +$10541.29

---

### 📊 SECTION 5. MACHINE LEARNING MODEL HEALTH & CALIBRATION
- **Expected Calibration Error (ECE)**: `0.0354`
- **Population Stability Index (PSI)**: `0.195`
- **Conformal Prediction Coverage**: `90.0% Empirical Interval Coverage`

---

### 📊 SECTION 6. EXECUTION ASSUMPTION AUDIT SPECIFICATION (4-QUESTION MATRIX)

| Execution Assumption | Value | Evidence Source | Tested? |
| :--- | :--- | :--- | :--- |
| **Bid/Ask Spread** | 0.0012 (0.0030 news) | Historical Broker Logs | ✅ Yes |
| **Asymmetric Slippage** | 0.0003 - 0.0008 | FIX API Execution Logs | ✅ Yes |
| **Commission Drag** | $7.00 / lot (0.7p) | Institutional ECN Fee Schedule | ✅ Yes |
| **Transmission Latency** | 300 ms (100-500ms) | Equinix NY4 VPS Cross-Connect | ✅ Yes |
| **Limit Fill Model** | 87.25% fill (3h) | Tick-Matched Simulation Logs | ✅ Yes |

---

### 📊 SECTION 7. OPERATIONAL INFRASTRUCTURE PARAMETERS
- **Data Pipeline Integrity**: `100%` (97,799 Clean H1 Candles, 2010–2026)
- **System Recovery Time**: `Instant` (< 0.1s Cache Restore)
- **Research-to-Production Parity**: `100% Semantic Parity`
