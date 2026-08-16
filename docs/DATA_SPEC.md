# 🗄️ Data Specification

### Data Sources
* **Assets:** EURUSD
* **Timeframes:** H1 (Primary), H4 (Macro Context).

### Timestamp Convention
* **Indexing:** Timestamps always represent the **START** of the candle.
* **Timezone:** UTC.

### MTF Leakage Prevention (The H4 -> H1 Alignment Law)
* **Invariant:** No feature may use information unavailable at the decision timestamp.
* **Implementation:** H4 features are calculated, then explicitly shifted forward by 1 row (`shift(1)`) before being forward-filled (`ffill`) onto the H1 index. This guarantees an H1 candle closing at 04:00 only sees the H4 candle that closed at 00:00 (a 4-hour pessimistic delay).
