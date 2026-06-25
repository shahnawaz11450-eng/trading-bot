import pandas as pd
import numpy as np

df = pd.read_csv('btc_1m_enhanced.csv')
df = df.set_index('timestamp').sort_index()

# RSI
delta = df['close'].diff()
gain = delta.clip(lower=0).ewm(span=14).mean()
loss = (-delta.clip(upper=0)).ewm(span=14).mean()
df['rsi'] = 100 - 100/(1 + gain/loss)

# Oversold/Overbought strategy
df['signal'] = 0
df.loc[df['rsi'] < 25, 'signal'] = 1   # Oversold - BUY
df.loc[df['rsi'] > 75, 'signal'] = -1  # Overbought - SELL

# Hold 5 bars
df['ret_5'] = df['close'].pct_change(5).shift(-5)
df['strategy_ret'] = df['signal'] * df['ret_5']

fee = 0.0004
trades = df[df['signal'] != 0].copy()
trades['net_ret'] = trades['strategy_ret'] - fee

print(f"Total Trades: {len(trades)}")
print(f"Win Rate: {(trades['net_ret']>0).mean()*100:.1f}%")
print(f"Total Return: {trades['net_ret'].sum()*100:.2f}%")
print(f"Avg Return per trade: {trades['net_ret'].mean()*100:.3f}%")
