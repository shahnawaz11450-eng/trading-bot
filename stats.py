import pandas as pd
import numpy as np

df = pd.read_csv('btc_5m_real.csv')
close = df['close'].values
mom = pd.Series(close).pct_change(10).fillna(0)
sig = np.where(mom > 0.001, 1, np.where(mom < -0.001, -1, 0))
returns = np.diff(np.log(close), prepend=0)
changes = np.where(np.diff(sig, prepend=0) != 0)[0]
trades = [{'dir': 'BUY' if sig[i]>0 else 'SELL', 'price': round(close[i],2), 'pnl': round(returns[i]*sig[i]*10000,2)} for i in changes if sig[i]!=0]
tdf = pd.DataFrame(trades)
print('Total:', len(tdf))
print('Buy:', (tdf.dir=='BUY').sum())
print('Sell:', (tdf.dir=='SELL').sum())
print('Win:', (tdf.pnl>0).sum(), f"({(tdf.pnl>0).mean()*100:.1f}%)")
print('Loss:', (tdf.pnl<0).sum(), f"({(tdf.pnl<0).mean()*100:.1f}%)")
print('Total PnL:', round(tdf.pnl.sum(),1), 'bps')
print('Avg/trade:', round(tdf.pnl.mean(),2), 'bps')
print('Best:', round(tdf.pnl.max(),2), 'bps')
print('Worst:', round(tdf.pnl.min(),2), 'bps')
