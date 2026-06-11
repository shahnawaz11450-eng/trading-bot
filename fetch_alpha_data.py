import ccxt
import pandas as pd

exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}  # Futures mode
})

# Funding Rate
print("Fetching funding rates...")
try:
    funding = exchange.fetch_funding_rate_history(
        'BTC/USDT', limit=500
    )
    df_fund = pd.DataFrame(funding)
    df_fund.to_csv('btc_funding.csv', index=False)
    print(f"✅ Funding: {len(df_fund)} records")
except Exception as e:
    print(f"❌ Funding error: {e}")

# OI
print("Fetching Open Interest...")
try:
    oi = exchange.fetch_open_interest_history(
        'BTC/USDT', '1h', limit=500
    )
    df_oi = pd.DataFrame(oi)
    df_oi.to_csv('btc_oi.csv', index=False)
    print(f"✅ OI: {len(df_oi)} records")
except Exception as e:
    print(f"❌ OI error: {e}")

print("Done!")
