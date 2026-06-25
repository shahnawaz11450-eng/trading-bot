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

trades = df[df['signal'] != 0]
wins = (trades['strategy_ret'] > 0).sum()
total = len(trades)

print(f"Total Trades: {total}")
print(f"Win Rate: {wins/total*100:.1f}%")
print(f"Total Return: {df['strategy_ret'].sum()*100:.2f}%")
print(f"LONG: {(trades['signal']==1).sum()}")
print(f"SHORT: {(trades['signal']==-1).sum()}")
