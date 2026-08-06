# 📐 AI Quant Lab — Master System Architecture & Dataflow Specification

---

## 1. High-Level Decoupled Architecture Flowchart

```mermaid
flowchart TD
    %% Styling
    classDef layer fill:#1e1e2e,stroke:#313244,stroke-width:2px,color:#cdd6f4;
    classDef component fill:#313244,stroke:#45475a,stroke-width:1px,color:#cdd6f4;
    classDef process fill:#f38ba8,stroke:#f38ba8,stroke-width:1px,color:#11111b;
    classDef data fill:#89b4fa,stroke:#89b4fa,stroke-width:1px,color:#11111b;

    %% Data Pipeline Layer
    subgraph DataLayer ["1. Data Pipeline & Ingestion"]
        Parquet[/"Dukascopy H1 Parquet (2018-2026)"/]
        Loader["DataLoader (data_loader/)"]
        FeatGen["FeatureMatrixBuilder (65+ Stationary Features)"]
    end
    class DataLayer layer; class Loader,FeatGen component; class Parquet data;

    %% Primary Strategy & Meta-Labeling Layer
    subgraph SignalLayer ["2. Primary Strategy & Meta-Labeler"]
        PrimaryEng["Primary Strategy Engine (Donchian / Breakout / HMM Filter)"]
        MetaLabeler["Meta-Labeler Ensemble (LightGBM + CatBoost P >= tau)"]
        HMMRegime["3-State HMM Regime Detector (Bear, Range, Bull)"]
    end
    class SignalLayer layer; class PrimaryEng,MetaLabeler,HMMRegime component;

    %% Decoupled AI Context Subsystem
    subgraph AICore ["3. Decoupled AI Market Context Subsystem"]
        FAR["Feature Admission Rule (FAR Gatekeeper)"]
        AI1["AI 1: Macro Context Engine (CB Divergence, Risk Sentiment, News)"]
        AI2["AI 2: Market State Engine (ADX, Vol Squeeze, Liquidity)"]
        Aggregator["Market Context Vector Aggregator (context_engine/)"]
    end
    class AICore layer; class FAR,AI1,AI2,Aggregator component;

    %% Bounded Execution & Risk Policy Layer
    subgraph PolicyLayer ["4. Execution Policy & Risk Management"]
        AI3["AI 3: Execution Policy Engine (execution_policy_engine/)"]
        RiskEngine["Risk Engine & Position Sizer (adaptive_sizer.py)"]
        SimEngine["High-Fidelity Execution Engine (engine.py)"]
    end
    class PolicyLayer layer; class AI3,RiskEngine,SimEngine component;

    %% Presentation & Progress Reporting
    subgraph Presentation ["5. Reporting & UI Dashboard"]
        ProgressMD["backtest_progress_report.md (Auto-Appending Log)"]
        JSONResults["master_institutional_backtest_results.json"]
        UI["Flask UI Dashboard & Streamlit (app.py)"]
    end
    class Presentation layer; class ProgressMD,JSONResults,UI component;

    %% Dataflow Connections
    Parquet --> Loader --> FeatGen
    FeatGen --> PrimaryEng
    PrimaryEng -->|"Candidate Signal S_i in {+1, -1}"| MetaLabeler
    HMMRegime -->|"State 0 Bear Filter"| PrimaryEng

    FAR -->|"Admitted Features (cb_divergence, risk_sentiment)"| AI1
    FeatGen --> AI2
    AI1 & AI2 & MetaLabeler --> Aggregator
    Aggregator -->|"Structured Market State Vector JSON"| AI3

    AI3 -->|"Bounded Policy: 0.50x-1.00x Risk, 1.5R-2.8R TP, Level 1 Event Risk"| RiskEngine
    RiskEngine --> SimEngine
    SimEngine -->|"Closed Trades & DSR / Underwater Metrics"| ProgressMD & JSONResults & UI
```

---

## 2. In-Depth Component Specification

### Phase A: Data Ingestion & Stationary Feature Pipeline
1. **Dukascopy Data Pipeline**: Stores clean 1-hour OHLCV candle data in `/market_data_pipeline/output/`.
2. **DataLoader (`data_loader/`)**: Standardizes timestamps, handles Forex weekend gaps (Friday 21:00 UTC to Sunday 21:00 UTC), and verifies monotonicity.
3. **FeatureMatrixBuilder (`research_engine/`)**: Generates 65+ technical and market features with anti-leakage time shifting (`shift(1)` on higher timeframes).

### Phase B: Primary Strategy & Meta-Labeling Core
1. **Primary Strategy Engine (`strategy_engine/institutional_ai.py`)**:
   - Generates directional setup candidates ($S_i \in \{+1, -1\}$).
   - Integrates 3-State Hidden Markov Model (`feat_hmm_regime`): State 0 (Bear Trend, $-1.83\text{ pips/hr}$ drift), State 1 (Range / Low Vol), State 2 (Bull Trend, $+0.77\text{ pips/hr}$ drift).
   - Applies targeted Bear Regime Filter (`long_ok & ~((feat_hmm_regime == 0) & (pred_prob_long < 0.60))`).
   - Calibrates **independent Long vs Short probability thresholds** (`prob_threshold_long` vs `prob_threshold_short`) to ensure symmetric selection.

### Phase C: Decoupled AI Market Context Subsystem
1. **Permanent Feature Admission Rule Engine (`ai_engine/feature_admission.py`)**:
   - Audits every candidate feature before allowing it into production.
   - Enforces $N_{\text{bucket}} \ge 200$ sample floor, Spearman rank correlation $r_s \ge +0.70$, $\Delta\text{PF} \ge +0.10$, and 2-year rolling walk-forward consistency ($>60.0\%$).
   - Certified Features: `cb_divergence` (Fed vs ECB interest rate divergence, PF Delta $+0.26$, 100% WF) and `risk_sentiment` (Volatility Squeeze & ATR rank, rs $+1.00$, 71.4% WF).
2. **AI 1 — Macro Context Engine (`macro_engine/`)**:
   - Computes certified macro sub-scores and aggregates them into the **Certified Market Context Index ($0-100$)**:
     $$\text{Certified Market Context Index} = 0.60 \cdot \text{cb\_divergence} + 0.40 \cdot \text{risk\_sentiment}$$
3. **AI 2 — Quantitative Market State Engine (`market_state_engine/`)**:
   - Calculates deterministic $0-100$ scores for Trend Strength (ADX), Volatility Squeeze, and Liquidity Density.
4. **Market Context Vector Aggregator (`context_engine/`)**:
   - Combines outputs into a unified JSON state vector passed to AI 3.

### Phase D: Bounded Execution Policy & Simulation Engine
1. **AI 3 — Execution Policy Engine (`execution_policy_engine/`)**:
   - Maps market state vectors into bounded execution multipliers:
     - **Defensive Position Sizing**: $0.50\times - 1.00\times$ base risk.
     - **Level 1 Event Risk Reduction**: When `event_risk >= 80.0` (30–60 mins near NFP/CPI/FOMC), applies $0.50\times$ risk + 6-hour tight exit horizon.
     - **TP Multiple Escalation**: Step escalation ($1.5\text{R} - 2.8\text{R}$).
     - **Audit-Ready Explainability**: Generates structured JSON explainability payloads for trade logging.
2. **Execution Engine (`execution_engine/`)**:
   - Simulates bar-by-bar matching with $1.50\text{ pips}$ transaction cost drag ($1.20\text{ pips}$ spread + $0.30\text{ pips}$ slippage/latency).
   - Computes **Lopez de Prado Deflated Sharpe Ratio (DSR)** and exact underwater drawdown duration.
