import pandas as pd
import numpy as np

df = pd.read_csv('btc_1m_enhanced.csv')
df['timestamp'] = pd.to_datetime(df['timestamp'])
df = df.set_index('timestamp').sort_index()

# Longer EMAs - kam signals
df['ema50']  = df['close'].ewm(span=50).mean()
df['ema200'] = df['close'].ewm(span=200).mean()
df['ema9']   = df['close'].ewm(span=9).mean()
df['vol_avg'] = df['volume'].rolling(50).mean()
df['atr'] = (df['high']-df['low']).ewm(span=14).mean()

# Sirf strong signals
df['signal'] = 0
# LONG: price > ema200, ema50 > ema200, volume spike, momentum positive
long_cond = ((df['close'] > df['ema200']) & 
             (df['ema50'] > df['ema200']) &
             (df['volume'] > df['vol_avg'] * 2.0) &
             (df['close'] > df['ema9']))
# SHORT: price < ema200, ema50 < ema200
short_cond = ((df['close'] < df['ema200']) & 
              (df['ema50'] < df['ema200']) &
              (df['volume'] > df['vol_avg'] * 2.0) &
              (df['close'] < df['ema9']))

df.loc[long_cond, 'signal'] = 1
df.loc[short_cond, 'signal'] = -1

# Hold 10 bars
df['ret_10'] = df['close'].pct_change(10).shift(-10)
df['strategy_ret'] = df['signal'] * df['ret_10']

fee = 0.0004  # round trip
trades = df[df['signal'] != 0].copy()
trades['net_ret'] = trades['strategy_ret'] - fee

total_ret = trades['net_ret'].sum() * 100
win_rate = (trades['net_ret'] > 0).mean() * 100

print(f"Total Trades: {len(trades)}")
print(f"Win Rate: {win_rate:.1f}%")
print(f"Total Return: {total_ret:.2f}%")
print(f"LONG: {(trades['signal']==1).sum()}")
print(f"SHORT: {(trades['signal']==-1).sum()}")
