# 🐛 Known Issues & Caveats

* **Phantom OANDA Fill Bug:** Fixed. The reconciler now properly tracks API vs Local states.
* **Risk Guardian Equity Bug:** Fixed. Now relies on Broker-authoritative balance.
* **MTF Lookahead Leakage:** Verified SAFE. H4 data is successfully shifted by 1 bar and ffill'd, yielding zero leakage.
* **Broker API Rate Limits:** OANDA occasionally throttles if polled > 4 times per second. EventBus handles backoff.
