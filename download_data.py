import ccxt
import pandas as pd
import time

exchange = ccxt.binance({'enableRateLimit': True})

symbol   = 'BTC/USDT'
tf       = '5m'
since    = exchange.parse8601('2023-01-01T00:00:00Z')
all_data = []

print("Downloading BTC/USDT 5m data...")

while True:
    batch = exchange.fetch_ohlcv(symbol, tf, since=since, limit=1000)
    if not batch:
        break
    all_data.extend(batch)
    since = batch[-1][0] + (5 * 60 * 1000)
    if since > exchange.milliseconds():
        break
    print(f"  Fetched: {len(all_data)} candles...", end='\r')
    time.sleep(0.3)

df = pd.DataFrame(all_data,
     columns=['timestamp','open','high','low','close','volume'])
df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
df = df.drop_duplicates('timestamp').sort_values('timestamp')
df.to_csv('btc_5m.csv', index=False)
print(f"\nDone! {len(df)} candles saved → btc_5m.csv")
