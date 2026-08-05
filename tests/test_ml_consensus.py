"""
Comprehensive MLConsensusStrategy Backtest Runner
Tests the strategy across multiple date ranges and collects detailed metrics.
"""
import requests
import json
import time
import sys

API_URL = "http://127.0.0.1:5000/api/backtest"

# Define test periods - various market conditions
TEST_PERIODS = [
    # Full year tests
    {"label": "2018 Full Year", "start": "2018-01-01", "end": "2018-12-31"},
    {"label": "2019 Full Year", "start": "2019-01-01", "end": "2019-12-31"},
    {"label": "2020 Full Year (COVID)", "start": "2020-01-01", "end": "2020-12-31"},
    {"label": "2021 Full Year", "start": "2021-01-01", "end": "2021-12-31"},
    {"label": "2022 Full Year", "start": "2022-01-01", "end": "2022-12-31"},
    {"label": "2023 Full Year", "start": "2023-01-01", "end": "2023-12-31"},
    {"label": "2024 Full Year", "start": "2024-01-01", "end": "2024-12-31"},
    {"label": "2025 Full Year", "start": "2025-01-01", "end": "2025-12-31"},
    # Multi-year tests
    {"label": "2018-2020 (3yr)", "start": "2018-01-01", "end": "2020-12-31"},
    {"label": "2021-2023 (3yr)", "start": "2021-01-01", "end": "2023-12-31"},
    {"label": "2018-2025 (Full)", "start": "2018-01-01", "end": "2025-12-31"},
    # Specific market regime tests
    {"label": "2020 Q1 (COVID Crash)", "start": "2020-01-01", "end": "2020-03-31"},
    {"label": "2020 Q2-Q3 (Recovery)", "start": "2020-04-01", "end": "2020-09-30"},
    {"label": "2022 H1 (USD Rally)", "start": "2022-01-01", "end": "2022-06-30"},
    {"label": "2022 H2", "start": "2022-07-01", "end": "2022-12-31"},
    {"label": "2023 H1", "start": "2023-01-01", "end": "2023-06-30"},
    {"label": "2024 H1", "start": "2024-01-01", "end": "2024-06-30"},
]

def run_backtest(label, start_date, end_date, strategy="MLConsensusStrategy", initial_capital=10000.0):
    """Run a single backtest and return the results."""
    payload = {
        "strategies": [strategy],
        "symbol": "EURUSD",
        "start_date": start_date,
        "end_date": end_date,
        "initial_capital": initial_capital
    }
    try:
        resp = requests.post(API_URL, json=payload, timeout=300)
        if resp.status_code != 200:
            return {"label": label, "error": resp.text}
        return {"label": label, "start": start_date, "end": end_date, "data": resp.json()}
    except Exception as e:
        return {"label": label, "error": str(e)}

def extract_metrics(result):
    """Extract key metrics from a backtest result."""
    if "error" in result:
        return {
            "label": result["label"],
            "error": result["error"]
        }
    
    data = result["data"]
    summary = data.get("summary", {})
    strategy_breakdown = data.get("strategy_breakdown", {})
    ml_breakdown = strategy_breakdown.get("MLConsensusStrategy", {})
    trades = data.get("trades", [])
    equity_curve = data.get("equity_curve", [])
    monthly_perf = data.get("monthly_performance", [])
    
    # Calculate additional metrics from trades
    winning_trades = [t for t in trades if t["pnl_pips"] > 0]
    losing_trades = [t for t in trades if t["pnl_pips"] <= 0]
    
    # Exit reason breakdown
    exit_reasons = {}
    for t in trades:
        reason = t.get("exit_reason", "unknown")
        exit_reasons[reason] = exit_reasons.get(reason, 0) + 1
    
    # Largest win / loss
    largest_win_pips = max((t["pnl_pips"] for t in trades), default=0)
    largest_loss_pips = min((t["pnl_pips"] for t in trades), default=0)
    largest_win_usd = max((t["pnl_usd"] for t in trades), default=0)
    largest_loss_usd = min((t["pnl_usd"] for t in trades), default=0)
    
    # Total USD P&L
    total_pnl_usd = sum(t["pnl_usd"] for t in trades)
    
    # Average win / loss in USD
    avg_win_usd = sum(t["pnl_usd"] for t in winning_trades) / len(winning_trades) if winning_trades else 0
    avg_loss_usd = sum(t["pnl_usd"] for t in losing_trades) / len(losing_trades) if losing_trades else 0
    
    # Monthly consistency
    profitable_months = sum(1 for m in monthly_perf if m.get("profit", 0) > 0)
    losing_months = sum(1 for m in monthly_perf if m.get("profit", 0) < 0)
    active_months = sum(1 for m in monthly_perf if m.get("trades", 0) > 0)
    
    # Trades per month average
    total_trades = summary.get("total_trades", 0)
    
    return {
        "label": result["label"],
        "start": result["start"],
        "end": result["end"],
        "total_trades": total_trades,
        "winning_trades": len(winning_trades),
        "losing_trades": len(losing_trades),
        "win_rate": summary.get("win_rate", 0),
        "total_pips": summary.get("total_pips", 0),
        "total_pnl_usd": round(total_pnl_usd, 2),
        "avg_pips_per_trade": summary.get("avg_pips", 0),
        "avg_win_pips": summary.get("avg_win_pips", 0),
        "avg_loss_pips": summary.get("avg_loss_pips", 0),
        "avg_win_usd": round(avg_win_usd, 2),
        "avg_loss_usd": round(avg_loss_usd, 2),
        "risk_reward_ratio": summary.get("risk_reward_ratio", 0),
        "expectancy_pips": summary.get("expectancy_pips", 0),
        "profit_factor": summary.get("profit_factor", 0),
        "sharpe_ratio": summary.get("sharpe_ratio", 0),
        "max_drawdown_pct": summary.get("max_drawdown", 0),
        "cagr": summary.get("cagr", 0),
        "recovery_factor": summary.get("recovery_factor", 0),
        "final_equity": summary.get("final_equity", 0),
        "best_trade_pips": summary.get("best_trade_pips", 0),
        "worst_trade_pips": summary.get("worst_trade_pips", 0),
        "largest_win_usd": largest_win_usd,
        "largest_loss_usd": largest_loss_usd,
        "consec_wins": summary.get("consec_wins", 0),
        "consec_losses": summary.get("consec_losses", 0),
        "best_day_pips": summary.get("best_day_pips", 0),
        "worst_day_pips": summary.get("worst_day_pips", 0),
        "profitable_days": summary.get("profitable_days", 0),
        "losing_days": summary.get("losing_days", 0),
        "avg_duration": summary.get("avg_duration", "N/A"),
        "profitable_months": profitable_months,
        "losing_months": losing_months,
        "active_months": active_months,
        "exit_reasons": exit_reasons,
        "strategy_pf": ml_breakdown.get("pf", 0),
        "strategy_sharpe": ml_breakdown.get("sharpe", 0),
        "strategy_max_dd": ml_breakdown.get("max_dd", 0),
        "sanity_warnings": ml_breakdown.get("sanity_warnings", []),
    }

def print_report(all_metrics):
    """Print a comprehensive comparison report."""
    
    print("\n" + "=" * 120)
    print("  ML CONSENSUS STRATEGY - COMPREHENSIVE PERFORMANCE REPORT")
    print("=" * 120)
    
    # ---- SUMMARY TABLE ----
    print("\n┌─────────────────────────────┬────────┬────────┬──────────┬───────────┬─────────┬─────────┬───────────┬────────────┐")
    print("│ Period                      │ Trades │ WinRate│ Tot Pips │  PnL USD  │  PF     │ Sharpe  │ Max DD %  │ Final Eq   │")
    print("├─────────────────────────────┼────────┼────────┼──────────┼───────────┼─────────┼─────────┼───────────┼────────────┤")
    
    for m in all_metrics:
        if "error" in m:
            print(f"│ {m['label']:<27} │ ERROR: {m['error'][:70]}")
            continue
        print(f"│ {m['label']:<27} │ {m['total_trades']:>6} │ {m['win_rate']:>5.1f}% │ {m['total_pips']:>8.1f} │ ${m['total_pnl_usd']:>8.2f} │ {m['profit_factor']:>7.2f} │ {m['sharpe_ratio']:>7.2f} │ {m['max_drawdown_pct']:>8.2f}% │ ${m['final_equity']:>9.2f} │")
    
    print("└─────────────────────────────┴────────┴────────┴──────────┴───────────┴─────────┴─────────┴───────────┴────────────┘")
    
    # ---- DETAILED PER-PERIOD STATS ----
    print("\n" + "=" * 120)
    print("  DETAILED METRICS PER PERIOD")
    print("=" * 120)
    
    for m in all_metrics:
        if "error" in m:
            continue
        
        print(f"\n{'─' * 80}")
        print(f"  📊 {m['label']}  ({m['start']} → {m['end']})")
        print(f"{'─' * 80}")
        
        print(f"  Trade Statistics:")
        print(f"    Total Trades:     {m['total_trades']}")
        print(f"    Winning Trades:   {m['winning_trades']}")
        print(f"    Losing Trades:    {m['losing_trades']}")
        print(f"    Win Rate:         {m['win_rate']:.2f}%")
        print(f"    Avg Duration:     {m['avg_duration']}")
        
        print(f"\n  Profit / Loss:")
        print(f"    Total Pips:       {m['total_pips']:.2f}")
        print(f"    Total PnL USD:    ${m['total_pnl_usd']:.2f}")
        print(f"    Avg Pips/Trade:   {m['avg_pips_per_trade']:.2f}")
        print(f"    Avg Win (pips):   {m['avg_win_pips']:.2f}")
        print(f"    Avg Loss (pips):  {m['avg_loss_pips']:.2f}")
        print(f"    Avg Win (USD):    ${m['avg_win_usd']:.2f}")
        print(f"    Avg Loss (USD):   ${m['avg_loss_usd']:.2f}")
        print(f"    Risk:Reward:      {m['risk_reward_ratio']:.2f}")
        print(f"    Expectancy:       {m['expectancy_pips']:.2f} pips")
        
        print(f"\n  Risk Metrics:")
        print(f"    Profit Factor:    {m['profit_factor']:.2f}")
        print(f"    Sharpe Ratio:     {m['sharpe_ratio']:.2f}")
        print(f"    Max Drawdown:     {m['max_drawdown_pct']:.2f}%")
        print(f"    CAGR:             {m['cagr']:.2f}%")
        print(f"    Recovery Factor:  {m['recovery_factor']:.2f}")
        
        print(f"\n  Extremes:")
        print(f"    Best Trade:       {m['best_trade_pips']:.2f} pips (${m['largest_win_usd']:.2f})")
        print(f"    Worst Trade:      {m['worst_trade_pips']:.2f} pips (${m['largest_loss_usd']:.2f})")
        print(f"    Max Consec Wins:  {m['consec_wins']}")
        print(f"    Max Consec Loss:  {m['consec_losses']}")
        print(f"    Best Day:         {m['best_day_pips']:.2f} pips")
        print(f"    Worst Day:        {m['worst_day_pips']:.2f} pips")
        
        print(f"\n  Consistency:")
        print(f"    Profitable Days:  {m['profitable_days']}")
        print(f"    Losing Days:      {m['losing_days']}")
        print(f"    Profitable Months:{m['profitable_months']}")
        print(f"    Losing Months:    {m['losing_months']}")
        print(f"    Active Months:    {m['active_months']}")
        
        print(f"\n  Exit Reasons:")
        for reason, count in m['exit_reasons'].items():
            pct = (count / m['total_trades'] * 100) if m['total_trades'] > 0 else 0
            print(f"    {reason:<20} {count:>4} ({pct:.1f}%)")
        
        if m['sanity_warnings']:
            print(f"\n  ⚠️  Sanity Warnings:")
            for w in m['sanity_warnings']:
                print(f"    - {w}")
    
    # ---- CROSS-PERIOD ANALYSIS ----
    valid = [m for m in all_metrics if "error" not in m]
    # Filter to only include years where we actually had trades (exclude untrained years)
    yearly = [m for m in valid if "Full Year" in m["label"] and m["total_trades"] > 0]
    
    if yearly:
        print("\n" + "=" * 120)
        print("  CROSS-YEAR ANALYSIS (Full Year periods only)")
        print("=" * 120)
        
        avg_trades = sum(m["total_trades"] for m in yearly) / len(yearly)
        avg_wr = sum(m["win_rate"] for m in yearly) / len(yearly)
        avg_pf = sum(m["profit_factor"] for m in yearly) / len(yearly)
        avg_sharpe = sum(m["sharpe_ratio"] for m in yearly) / len(yearly)
        avg_dd = sum(m["max_drawdown_pct"] for m in yearly) / len(yearly)
        avg_pips = sum(m["total_pips"] for m in yearly) / len(yearly)
        avg_pnl = sum(m["total_pnl_usd"] for m in yearly) / len(yearly)
        
        profitable_years = sum(1 for m in yearly if m["total_pnl_usd"] > 0)
        losing_years = sum(1 for m in yearly if m["total_pnl_usd"] <= 0)
        
        best_year = max(yearly, key=lambda m: m["total_pnl_usd"])
        worst_year = min(yearly, key=lambda m: m["total_pnl_usd"])
        
        print(f"\n  Averages Across {len(yearly)} Years:")
        print(f"    Avg Trades/Year:    {avg_trades:.1f}")
        print(f"    Avg Win Rate:       {avg_wr:.2f}%")
        print(f"    Avg Profit Factor:  {avg_pf:.2f}")
        print(f"    Avg Sharpe:         {avg_sharpe:.2f}")
        print(f"    Avg Max DD:         {avg_dd:.2f}%")
        print(f"    Avg Pips/Year:      {avg_pips:.2f}")
        print(f"    Avg PnL/Year:       ${avg_pnl:.2f}")
        
        print(f"\n  Year-over-Year:")
        print(f"    Profitable Years:   {profitable_years} / {len(yearly)}")
        print(f"    Losing Years:       {losing_years} / {len(yearly)}")
        print(f"    Best Year:          {best_year['label']} (${best_year['total_pnl_usd']:.2f})")
        print(f"    Worst Year:         {worst_year['label']} (${worst_year['total_pnl_usd']:.2f})")
        
        # Consistency score
        consistency = profitable_years / len(yearly) * 100
        print(f"    Consistency Score:  {consistency:.0f}%")
        
        # Win rate stability
        wr_values = [m["win_rate"] for m in yearly]
        wr_std = (sum((w - avg_wr) ** 2 for w in wr_values) / len(wr_values)) ** 0.5
        print(f"    Win Rate Std Dev:   {wr_std:.2f}%")
        
    # ---- OVERALL VERDICT ----
    print("\n" + "=" * 120)
    print("  OVERALL STRATEGY VERDICT")
    print("=" * 120)
    
    if yearly:
        scores = []
        # Win rate score (50-70% is good)
        wr_score = min(max((avg_wr - 40) / 30 * 100, 0), 100)
        scores.append(("Win Rate", wr_score))
        
        # Profit Factor (1.0-3.0, >1.5 good)
        pf_score = min(max((avg_pf - 0.5) / 2.0 * 100, 0), 100)
        scores.append(("Profit Factor", pf_score))
        
        # Sharpe (0-3, >1.0 good)
        sh_score = min(max(avg_sharpe / 2.0 * 100, 0), 100)
        scores.append(("Sharpe Ratio", sh_score))
        
        # Max DD (lower is better, <10% excellent)
        dd_score = min(max((20 - avg_dd) / 20 * 100, 0), 100)
        scores.append(("Max Drawdown", dd_score))
        
        # Consistency
        cons_score = consistency
        scores.append(("Consistency", cons_score))
        
        # Trade frequency (>20 trades/year is good)
        freq_score = min(max(avg_trades / 50 * 100, 0), 100)
        scores.append(("Trade Frequency", freq_score))
        
        overall = sum(s[1] for s in scores) / len(scores)
        
        print(f"\n  Scoring (0-100):")
        for name, score in scores:
            bar = "█" * int(score / 5) + "░" * (20 - int(score / 5))
            print(f"    {name:<20} {bar} {score:.0f}/100")
        
        print(f"\n    {'─' * 40}")
        overall_bar = "█" * int(overall / 5) + "░" * (20 - int(overall / 5))
        print(f"    {'OVERALL SCORE':<20} {overall_bar} {overall:.0f}/100")
        
        if overall >= 75:
            verdict = "🟢 EXCELLENT - Strategy shows strong, consistent edge"
        elif overall >= 60:
            verdict = "🟡 GOOD - Strategy is profitable but has room for improvement"
        elif overall >= 45:
            verdict = "🟠 MEDIOCRE - Strategy needs significant enhancements"
        else:
            verdict = "🔴 POOR - Strategy needs fundamental redesign"
        
        print(f"\n  Verdict: {verdict}")
    
    print("\n" + "=" * 120)


def save_results_json(all_metrics, filepath):
    """Save raw metrics to JSON for further analysis."""
    # Make it JSON serializable
    serializable = []
    for m in all_metrics:
        s = dict(m)
        serializable.append(s)
    
    with open(filepath, 'w') as f:
        json.dump(serializable, f, indent=2, default=str)
    print(f"\n📁 Raw results saved to: {filepath}")


if __name__ == "__main__":
    print("🚀 Starting ML Consensus Strategy Comprehensive Backtest...")
    print(f"   Testing {len(TEST_PERIODS)} date ranges against EURUSD")
    print(f"   Initial Capital: $10,000")
    print()
    
    all_results = []
    all_metrics = []
    
    for i, period in enumerate(TEST_PERIODS):
        label = period["label"]
        start = period["start"]
        end = period["end"]
        print(f"  [{i+1}/{len(TEST_PERIODS)}] Running: {label} ({start} → {end})...", end=" ", flush=True)
        
        t0 = time.time()
        result = run_backtest(label, start, end)
        elapsed = time.time() - t0
        
        if "error" in result:
            print(f"❌ Error ({elapsed:.1f}s): {result['error'][:80]}")
        else:
            trades = result["data"].get("summary", {}).get("total_trades", 0)
            pnl = result["data"].get("summary", {}).get("total_pips", 0)
            print(f"✅ {trades} trades, {pnl:.1f} pips ({elapsed:.1f}s)")
        
        metrics = extract_metrics(result)
        all_results.append(result)
        all_metrics.append(metrics)
    
    # Print the full report
    print_report(all_metrics)
    
    # Save raw data
    save_results_json(all_metrics, "ml_consensus_backtest_results.json")
    
    print("\n✅ All backtests complete!")
