"""
AL-FATH v22 — 10 New Alpha Features
Funding Rate + OI + Volume + RSI Divergence
"""
import pandas as pd
import numpy as np

print("="*50)
print("Building Alpha Features...")
print("="*50)

# ── Load Data ────────────────────────────
df = pd.read_csv('btc_1m.csv')
df['timestamp'] = pd.to_datetime(df['timestamp'])
df = df.set_index('timestamp').sort_index()

df_fund = pd.read_csv('btc_funding.csv')
df_oi   = pd.read_csv('btc_oi.csv')

print(f"OHLCV: {len(df)} bars")
print(f"Funding cols: {list(df_fund.columns)}")
print(f"OI cols: {list(df_oi.columns)}")

# ── Feature 1-3: Funding Rate ─────────────
print("\n[1-3] Funding Rate features...")
try:
    # Timestamp column dhundo
    ts_col = [c for c in df_fund.columns 
              if 'time' in c.lower() or 'ts' in c.lower()][0]
    rate_col = [c for c in df_fund.columns 
                if 'rate' in c.lower() or 'funding' in c.lower()][0]
    
    df_fund[ts_col] = pd.to_datetime(df_fund[ts_col], unit='ms'
                      if df_fund[ts_col].dtype == 'int64' else None)
    df_fund = df_fund.set_index(ts_col).sort_index()
    df_fund = df_fund[[rate_col]].rename(columns={rate_col: 'funding_rate'})
    df_fund = df_fund.resample('1min').ffill()
    
    df['funding_rate']     = df_fund['funding_rate'].reindex(df.index).ffill()
    df['funding_extreme']  = (df['funding_rate'].abs() > 0.001).astype(float)
    df['funding_negative'] = (df['funding_rate'] < -0.0001).astype(float)
    print("    ✅ Funding features added")
except Exception as e:
    print(f"    ⚠️ Funding: {e}")
    df['funding_rate']     = 0.0
    df['funding_extreme']  = 0.0
    df['funding_negative'] = 0.0

# ── Feature 4-5: Open Interest ────────────
print("[4-5] OI features...")
try:
    ts_col2 = [c for c in df_oi.columns 
               if 'time' in c.lower() or 'ts' in c.lower()][0]
    oi_col  = [c for c in df_oi.columns 
               if 'oi' in c.lower() or 'open' in c.lower() 
               or 'interest' in c.lower()][0]
    
    df_oi[ts_col2] = pd.to_datetime(df_oi[ts_col2], unit='ms'
                     if df_oi[ts_col2].dtype == 'int64' else None)
    df_oi = df_oi.set_index(ts_col2).sort_index()
    df_oi = df_oi[[oi_col]].rename(columns={oi_col: 'oi'})
    df_oi = df_oi.resample('1min').ffill()
    
    df['oi']          = df_oi['oi'].reindex(df.index).ffill()
    df['oi_change']   = df['oi'].pct_change(60).fillna(0)  # 1h change
    df['oi_rising']   = (df['oi_change'] > 0.02).astype(float)
    print("    ✅ OI features added")
except Exception as e:
    print(f"    ⚠️ OI: {e}")
    df['oi_change'] = 0.0
    df['oi_rising'] = 0.0

# ── Feature 6-7: RVOL + Breakout ─────────
print("[6-7] RVOL + Breakout features...")
df['rvol']          = df['volume'] / (df['volume'].rolling(100).mean() + 1e-9)
df['vol_breakout']  = (df['rvol'] > 2.5).astype(float)
print("    ✅ RVOL features added")

# ── Feature 8: ATR Expansion ──────────────
print("[8] ATR Expansion...")
tr = pd.concat([
    df['high'] - df['low'],
    (df['high'] - df['close'].shift()).abs(),
    (df['low']  - df['close'].shift()).abs()
], axis=1).max(axis=1)
atr_now  = tr.ewm(alpha=1/14, adjust=False).mean()
atr_slow = tr.ewm(alpha=1/50, adjust=False).mean()
df['atr_expansion'] = (atr_now / (atr_slow + 1e-9)).fillna(1.0)
print("    ✅ ATR Expansion added")

# ── Feature 9-10: RSI Divergence ──────────
print("[9-10] RSI Divergence features...")
# RSI
delta = df['close'].diff()
gain  = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
loss  = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
rsi   = 100 - 100/(1 + gain/(loss + 1e-9))

# Price HH + RSI LH = Bearish Divergence
price_hh = (df['close'] > df['close'].shift(20)) & \
           (df['close'].shift(20) > df['close'].shift(40))
rsi_lh   = (rsi < rsi.shift(20)) & \
           (rsi.shift(20) < rsi.shift(40))
df['bearish_divergence'] = (price_hh & rsi_lh).astype(float)

# Price LL + RSI HL = Bullish Divergence
price_ll = (df['close'] < df['close'].shift(20)) & \
           (df['close'].shift(20) < df['close'].shift(40))
rsi_hl   = (rsi > rsi.shift(20)) & \
           (rsi.shift(20) > rsi.shift(40))
df['bullish_divergence'] = (price_ll & rsi_hl).astype(float)
print("    ✅ RSI Divergence added")

# ── Save ──────────────────────────────────
new_features = [
    'funding_rate', 'funding_extreme', 'funding_negative',
    'oi_change', 'oi_rising',
    'rvol', 'vol_breakout',
    'atr_expansion',
    'bearish_divergence', 'bullish_divergence'
]

df_save = df[new_features].reset_index()
df_save.to_csv('btc_alpha_features.csv', index=False)

print(f"\n{'='*50}")
print(f"✅ 10 Alpha Features Ready!")
for f in new_features:
    non_zero = (df[f] != 0).sum()
    print(f"  {f:<25} non-zero: {non_zero}")
print(f"Saved: btc_alpha_features.csv")
print(f"{'='*50}")
