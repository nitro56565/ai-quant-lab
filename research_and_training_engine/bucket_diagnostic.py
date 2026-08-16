import pandas as pd
import numpy as np

def analyze_bucketed_expectancy(df_trades: pd.DataFrame, score_col: str) -> pd.DataFrame:
    """
    Groups trades into score quintiles (0-20, 20-40, 40-60, 60-80, 80-100)
    and computes trade expectancy metrics per bucket.
    """
    if score_col not in df_trades.columns:
        raise ValueError(f"Column '{score_col}' not found in trades dataframe.")
        
    bins = [-0.1, 20.0, 40.0, 60.0, 80.0, 100.1]
    labels = ['0-20', '20-40', '40-60', '60-80', '80-100']
    
    df_trades = df_trades.copy()
    df_trades['bucket'] = pd.cut(df_trades[score_col], bins=bins, labels=labels)
    
    summary_list = []
    
    for label in labels:
        bucket_trades = df_trades[df_trades['bucket'] == label]
        n_trades = len(bucket_trades)
        
        if n_trades == 0:
            summary_list.append({
                'Bucket': label,
                'Trades': 0,
                'Win Rate %': 0.0,
                'Avg Pips': 0.0,
                'Net PnL ($)': 0.0,
                'Profit Factor': 1.00
            })
            continue
            
        wins = bucket_trades[bucket_trades['pnl_pips'] > 0]
        losses = bucket_trades[bucket_trades['pnl_pips'] <= 0]
        
        win_rate = (len(wins) / n_trades) * 100.0
        avg_pips = bucket_trades['pnl_pips'].mean()
        net_pnl = bucket_trades['pnl_usd'].sum()
        
        win_cash = wins['pnl_usd'].sum()
        loss_cash = abs(losses['pnl_usd'].sum())
        pf = win_cash / loss_cash if loss_cash > 0 else 1.0
        
        summary_list.append({
            'Bucket': label,
            'Trades': n_trades,
            'Win Rate %': round(win_rate, 1),
            'Avg Pips': round(avg_pips, 2),
            'Net PnL ($)': round(net_pnl, 2),
            'Profit Factor': round(pf, 2)
        })
        
    return pd.DataFrame(summary_list)
