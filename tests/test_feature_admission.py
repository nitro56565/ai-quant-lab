import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import unittest
import pandas as pd
import numpy as np
from data_loader import DataLoader
from strategy_engine.institutional_ai import InstitutionalAIStrategy
from macro_engine.parser import MacroContextEngine
from execution_engine import ExecutionEngine
from ai_engine.feature_admission import FeatureAdmissionEngine

class TestFeatureAdmissionRule(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        loader = DataLoader()
        symbol = "EURUSD"
        start_date = "2018-01-01"
        end_date = "2025-12-31"

        strat = InstitutionalAIStrategy()
        df_signals = strat.prepare_data(loader, symbol, start_date, end_date)
        n_rows = len(df_signals)

        signals = np.full(n_rows, None, dtype=object)
        if 'signal' in df_signals.columns:
            signals = df_signals['signal'].values
        else:
            signals[df_signals['entry_signal'].values] = 'BUY'

        macro_engine = MacroContextEngine()
        score_names = ['trend_macro', 'risk_sentiment', 'cb_divergence', 'event_risk', 'cot_score', 'liquidity']
        score_data = {name: np.zeros(n_rows) for name in score_names}

        for i in range(n_rows):
            ts = df_signals.index[i]
            ctx = macro_engine.get_macro_context(symbol, ts, df_signals, i)
            for name in score_names:
                score_data[name][i] = ctx[name]

        pip_size = loader.get_symbol_metadata(symbol).get('pip_size', 0.0001)
        config = {'sl_multiplier': 2.0, 'tp_multiplier': 3.6, 'trail_multiplier': None}
        exec_engine = ExecutionEngine(initial_capital=10000.0, default_pip_value=10.0)

        trades = exec_engine.run_simulation(df=df_signals, signals=signals, config=config, symbol=symbol, pip_size=pip_size, strategy_name="InstitutionalAIStrategy")
        closed_trades = [t for t in trades if t['status'] == 'closed']
        df_closed = pd.DataFrame(closed_trades)

        entry_indices = [df_signals.index.get_loc(t['entry_time']) for t in closed_trades]
        vol_rank = df_signals['feat_vol_atr_pct'].values if 'feat_vol_atr_pct' in df_signals.columns else np.full(n_rows, 50.0)
        v_rank_sub = vol_rank[entry_indices]
        tp_mults = np.where(v_rank_sub >= 60, 2.4 / 1.8, 1.0)
        df_closed['pnl_pips'] = np.where(df_closed['pnl_pips'] > 0, df_closed['pnl_pips'] * tp_mults, df_closed['pnl_pips'])
        df_closed['pnl_usd'] = np.where(df_closed['pnl_usd'] > 0, df_closed['pnl_usd'] * tp_mults, df_closed['pnl_usd'])

        for name in score_names:
            df_closed[name] = score_data[name][entry_indices]

        cls.df_closed = df_closed
        cls.far_engine = FeatureAdmissionEngine(min_samples_per_bucket=200, min_pf_uplift=0.10, min_spearman_rs=0.70)

    def test_cb_divergence_admission(self):
        res = self.far_engine.evaluate_feature_admission(self.df_closed, 'cb_divergence')
        print(f"\n[FAR GATEKEEPER] cb_divergence: {res['status']} ({res['reason']})")
        self.assertEqual(res['status'], "ADMITTED")

    def test_risk_sentiment_admission(self):
        res = self.far_engine.evaluate_feature_admission(self.df_closed, 'risk_sentiment')
        print(f"[FAR GATEKEEPER] risk_sentiment: {res['status']} ({res['reason']})")
        self.assertEqual(res['status'], "ADMITTED")

    def test_trend_macro_rejection(self):
        res = self.far_engine.evaluate_feature_admission(self.df_closed, 'trend_macro')
        print(f"[FAR GATEKEEPER] trend_macro: {res['status']} ({res['reason']})")
        self.assertEqual(res['status'], "REJECTED")

    def test_cot_score_rejection(self):
        res = self.far_engine.evaluate_feature_admission(self.df_closed, 'cot_score')
        print(f"[FAR GATEKEEPER] cot_score: {res['status']} ({res['reason']})")
        self.assertEqual(res['status'], "REJECTED")

    def test_liquidity_rejection(self):
        res = self.far_engine.evaluate_feature_admission(self.df_closed, 'liquidity')
        print(f"[FAR GATEKEEPER] liquidity: {res['status']} ({res['reason']})\n")
        self.assertEqual(res['status'], "REJECTED")

if __name__ == '__main__':
    unittest.main()
