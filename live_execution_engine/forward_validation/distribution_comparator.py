"""
Forward Validation Distribution Comparator & Statistical Parity Engine.
Evaluates continuous live-demo execution against historical backtest expectations:
- Win Rate & Profit Factor Parity
- Realized R Distribution Kolmogorov-Smirnov (KS-test)
- Execution Slippage & Latency Profiling
- Structural Alpha Drift Early Warning System
"""

import numpy as np
from scipy import stats
from typing import Dict, Any, List, Tuple, Optional

class DistributionComparator:
    def __init__(
        self,
        expected_win_rate: float = 0.525, # 52.5% historical win rate
        expected_pf: float = 1.15,         # 1.15 historical profit factor
        expected_avg_r: float = 0.16,      # +0.16R historical average R
        max_allowed_slippage_pips: float = 0.50
    ):
        self.expected_win_rate = expected_win_rate
        self.expected_pf = expected_pf
        self.expected_avg_r = expected_avg_r
        self.max_allowed_slippage_pips = max_allowed_slippage_pips

    def evaluate_live_distribution(
        self,
        live_telemetry: List[Dict[str, Any]],
        historical_r_returns: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """
        Evaluates live trades against historical backtest distribution.
        """
        n_trades = len(live_telemetry)
        if n_trades == 0:
            return {
                'status': 'INSUFFICIENT_SAMPLE_SIZE',
                'n_trades': 0,
                'verdict': 'AWAITING_MORE_TRADES'
            }

        realized_rs = [t.get('realized_r', 0.0) for t in live_telemetry]
        wins = [r for r in realized_rs if r > 0]
        losses = [r for r in realized_rs if r < 0]

        win_rate = len(wins) / max(1, n_trades)
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 1.0)
        avg_r = float(np.mean(realized_rs))

        slippages = [abs(t.get('slippage_pips', 0.0)) for t in live_telemetry]
        latencies = [t.get('fill_latency_ms', 0.0) for t in live_telemetry]

        mean_slippage = float(np.mean(slippages)) if slippages else 0.0
        p95_slippage = float(np.percentile(slippages, 95)) if slippages else 0.0
        mean_latency = float(np.mean(latencies)) if latencies else 0.0

        # KS-Test against historical distribution (if provided)
        ks_stat = 0.0
        ks_pvalue = 1.0
        if historical_r_returns and len(historical_r_returns) > 10 and n_trades >= 10:
            ks_res = stats.ks_2samp(realized_rs, historical_r_returns)
            ks_stat = float(ks_res.statistic)
            ks_pvalue = float(ks_res.pvalue)

        # Alpha Drift Classification
        # Do NOT judge on short-term 20-50 trade PnL noise! Judge on distribution match.
        if n_trades < 30:
            verdict = "FORWARD_PARITY_MONITORING_SAMPLE_BUILDING"
            status = "SAMPLE_BUILDING"
        elif win_rate >= 0.48 and profit_factor >= 1.05 and avg_r >= 0.08:
            verdict = "🟢 STABLE_ALPHA_EDGE_CONFIRMED"
            status = "HEALTHY"
        elif win_rate >= 0.45 and avg_r >= 0.0:
            verdict = "🟡 EXPECTED_DRAWDOWN_NOISE_WITHIN_BOUNDS"
            status = "MONITORING"
        else:
            verdict = "🚨 STRUCTURAL_ALPHA_DRIFT_WARNING"
            status = "WARNING"

        return {
            'n_trades': n_trades,
            'live_win_rate': round(win_rate, 4),
            'expected_win_rate': self.expected_win_rate,
            'live_profit_factor': round(profit_factor, 4),
            'expected_pf': self.expected_pf,
            'live_avg_r': round(avg_r, 4),
            'expected_avg_r': self.expected_avg_r,
            'mean_slippage_pips': round(mean_slippage, 4),
            'p95_slippage_pips': round(p95_slippage, 4),
            'mean_latency_ms': round(mean_latency, 2),
            'ks_pvalue': round(ks_pvalue, 4),
            'ks_consistent': (ks_pvalue > 0.05),
            'status': status,
            'verdict': verdict
        }
