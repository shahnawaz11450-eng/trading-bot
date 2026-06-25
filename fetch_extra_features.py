"""
AL-FATH Extra Features Fetcher
Real funding rate + liquidation proxy + market microstructure
"""
import pandas as pd
import numpy as np
import requests
import json
from datetime import datetime, timezone

def fetch_funding_rates(symbol="BTCUSDT", limit=1000):
    """Binance se real funding rates fetch karo"""
    try:
        url = f"https://fapi.binance.com/fapi/v1/fundingRate"
        params = {"symbol": symbol, "limit": limit}
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        df = pd.DataFrame(data)
        df['timestamp'] = pd.to_datetime(df['fundingTime'], unit='ms')
        df['funding_rate'] = df['fundingRate'].astype(float)
        df = df[['timestamp', 'funding_rate']].set_index('timestamp')
        print(f"Funding rates fetched: {len(df)} records")
        return df
    except Exception as e:
        print(f"Funding fetch failed: {e}")
        return None

def add_microstructure_features(df):
    """Price action se microstructure features"""
    eps = 1e-9
    
    # 1. Buying pressure proxy
    df['buy_pressure'] = (df['close'] - df['low']) / (df['high'] - df['low'] + eps)
    
    # 2. Volume weighted momentum
    df['vwm_5']  = (df['close'].diff(5)  * df['volume']).rolling(5).sum()  / (df['volume'].rolling(5).sum() + eps)
    df['vwm_20'] = (df['close'].diff(20) * df['volume']).rolling(20).sum() / (df['volume'].rolling(20).sum() + eps)
    
    # 3. Liquidation proxy (volume spike + big candle)
    vol_med = df['volume'].rolling(100).median()
    atr = (df['high'] - df['low']).ewm(span=14).mean()
    df['liq_proxy'] = ((df['volume'] > vol_med * 5) & 
                       ((df['high']-df['low']) > atr * 2)).astype(float)
    
    # 4. Trend strength
    ema20 = df['close'].ewm(span=20).mean()
    ema50 = df['close'].ewm(span=50).mean()
    ema200 = df['close'].ewm(span=200).mean()
    df['trend_alignment'] = (
        ((df['close'] > ema20).astype(int) + 
         (ema20 > ema50).astype(int) + 
         (ema50 > ema200).astype(int)) / 3.0
    )
    
    # 5. Volatility regime
    log_ret = np.log(df['close']/df['close'].shift(1))
    df['vol_20']  = log_ret.rolling(20).std()
    df['vol_100'] = log_ret.rolling(100).std()
    df['vol_regime'] = df['vol_20'] / (df['vol_100'] + eps)
    
    # 6. Smart money index proxy
    first30 = df['close'].rolling(30).mean()
    last30  = df['close'].shift(30).rolling(30).mean()
    df['smi_proxy'] = (last30 - first30) / (df['close'] + eps)
    
    return df

def main():
    print("Loading BTC 1m data...")
    df = pd.read_csv('sol_1m.csv')
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.set_index('timestamp').sort_index()
    print(f"Data loaded: {len(df)} bars from {df.index[0]} to {df.index[-1]}")
    
    # Microstructure features
    print("Adding microstructure features...")
    df = add_microstructure_features(df)
    
    # Funding rates
    print("Fetching real funding rates...")
    funding = fetch_funding_rates()
    if funding is not None:
        df = df.merge(funding, left_index=True, right_index=True, how='left')
        df['funding_rate'] = df['funding_rate'].ffill().fillna(0)
        print(f"Funding rate merged: {df['funding_rate'].notna().sum()} bars")
    
    # Save
    df.to_csv('sol_enhanced.csv')
    print(f"Saved: sol_enhanced.csv ({len(df)} rows)")
    
    # Stats
    new_cols = ['buy_pressure','vwm_5','vwm_20','liq_proxy',
                'trend_alignment','vol_regime','smi_proxy']
    print("\nNew features stats:")
    for col in new_cols:
        if col in df.columns:
            print(f"  {col}: mean={df[col].mean():.4f} std={df[col].std():.4f}")

if __name__ == "__main__":
    main()
