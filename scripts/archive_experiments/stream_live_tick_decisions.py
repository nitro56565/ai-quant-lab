#!/usr/bin/env python3
"""
Real-Time Live Tick-by-Tick ML Decision Streamer CLI (IST / UTC).
Streams live OANDA tick predictions, win probabilities, expected values, outcomes (SKIP / EXECUTE), and reasons.
"""

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import time
import requests
import json
from datetime import datetime, timezone, timedelta

def main():
    print("====================================================================================================")
    print("  🌐 REAL-TIME SECOND-BY-SECOND LIVE TICK DECISION MONITOR — (IST & UTC)")
    print("  Listening to live OANDA ticks & ML Signal Engine predictions on http://localhost:5006/...")
    print("====================================================================================================")
    print(f"{'TIMESTAMP (IST / UTC)':<35} | {'SYMBOL':<6} | {'OUTCOME':<9} | {'LONG PROB':<10} | {'LONG EV':<10} | {'DECISION REASON'}")
    print("-" * 105)

    seen_ids = set()
    url = "http://localhost:5006/api/v2/decisions?limit=20"

    while True:
        try:
            resp = requests.get(url, timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                decisions = data.get("decisions", [])
                
                # Print in chronological order (oldest to newest)
                for d in reversed(decisions):
                    t_id = d.get("trace_id")
                    if t_id and t_id not in seen_ids:
                        seen_ids.add(t_id)
                        
                        raw_ts = d.get("timestamp", "")
                        # Parse timestamp to convert to IST
                        try:
                            clean_ts = raw_ts.replace(" UTC", "")
                            dt = datetime.strptime(clean_ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                            ist_dt = dt.astimezone(timezone(timedelta(hours=5, minutes=30)))
                            ts_disp = f"{ist_dt.strftime('%H:%M:%S IST')} [{dt.strftime('%H:%M:%S UTC')}]"
                        except Exception:
                            ts_disp = raw_ts

                        symbol = d.get("symbol", "EURUSD")
                        outcome = d.get("outcome", "SKIP")
                        outcome_disp = "🟢 EXECUTE" if outcome == "EXECUTE" else "🛡️ SKIP"
                        
                        p_long = d.get("prob_long", 0.0) * 100.0
                        ev_long = d.get("ev_long", 0.0)
                        reason = d.get("reason", "")

                        print(f"{ts_disp:<35} | {symbol:<6} | {outcome_disp:<9} | {p_long:6.2f}%    | {ev_long:+6.2f}p    | {reason}")
                        sys.stdout.flush()
        except Exception:
            pass
            
        time.sleep(1.0)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Streamer stopped by user.")
