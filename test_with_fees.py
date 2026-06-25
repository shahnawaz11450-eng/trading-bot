import pandas as pd
import numpy as np

df = pd.read_csv('btc_1m_enhanced.csv')
df['timestamp'] = pd.to_datetime(df['timestamp'])
df = df.set_index('timestamp').sort_index()

df['ema20'] = df['close'].ewm(span=20).mean()
df['ema50'] = df['close'].ewm(span=50).mean()
df['vol_avg'] = df['volume'].rolling(20).mean()

df['signal'] = 0
df.loc[(df['close'] > df['ema20']) & (df['ema20'] > df['ema50']) & (df['volume'] > df['vol_avg'] * 1.5), 'signal'] = 1
df.loc[(df['close'] < df['ema20']) & (df['ema20'] < df['ema50']), 'signal'] = -1

df['ret'] = df['close'].pct_change().shift(-1)
df['strategy_ret'] = df['signal'] * df['ret']

# Fees: 0.02% per trade
fee = 0.0002
trades_mask = df['signal'] != 0
df.loc[trades_mask, 'strategy_ret'] -= fee

total_ret = df['strategy_ret'].sum() * 100
trades = df[trades_mask]
win_rate = (trades['strategy_ret'] > 0).mean() * 100

print(f"Total Return (after fees): {total_ret:.2f}%")
print(f"Win Rate: {win_rate:.1f}%")
print(f"Total Trades: {len(trades)}")
