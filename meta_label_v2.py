import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.model_selection import train_test_split

print("Loading data...")
df = pd.read_csv('btc_1m.csv')
df['timestamp'] = pd.to_datetime(df['timestamp'])
df = df.set_index('timestamp').sort_index()

# Better Primary Signal: Volume Breakout + ATR
df['rvol'] = df['volume'] / df['volume'].rolling(100).mean()
df['atr']  = (df['high'] - df['low']).ewm(span=14).mean()
df['atr_expand'] = df['atr'] / df['atr'].rolling(50).mean()

# Primary: High volume + ATR expansion = breakout
df['primary_signal'] = np.where(
    (df['rvol'] > 1.5) & (df['atr_expand'] > 1.2) &
    (df['close'] > df['close'].shift(1)), 1,
    np.where(
    (df['rvol'] > 1.5) & (df['atr_expand'] > 1.2) &
    (df['close'] < df['close'].shift(1)), -1, 0)
)

# Future return 30 bars
df['future_ret'] = df['close'].pct_change(30).shift(-30)

# Meta label
df['meta_label'] = (
    df['primary_signal'] * df['future_ret'] > 0
).astype(int)

# Features
df['rsi'] = 100 - 100/(1 +
    df['close'].diff().clip(lower=0).ewm(span=14).mean() /
    (-df['close'].diff().clip(upper=0)).ewm(span=14).mean())
df['momentum'] = df['close'].pct_change(10)
df['vol_ratio'] = df['volume'] / df['volume'].shift(1)
df['bb_pos'] = (df['close'] - df['close'].rolling(20).mean()) / \
               (df['close'].rolling(20).std() + 1e-9)
df['funding'] = df['close'].pct_change(60).rolling(8).mean()

feat_cols = ['rsi','rvol','atr_expand','momentum',
             'vol_ratio','bb_pos','funding']

# Only breakout bars
mask = df['primary_signal'] != 0
df_t = df[mask].dropna()
print(f"Breakout bars: {len(df_t)}")

X = df_t[feat_cols].fillna(0)
y = df_t['meta_label']
print(f"Label dist: {dict(y.value_counts())}")

X_tr, X_te, y_tr, y_te = train_test_split(
    X, y, test_size=0.2, shuffle=False
)

model = lgb.LGBMClassifier(
    n_estimators=200, max_depth=4,
    learning_rate=0.03, random_state=42,
    verbose=-1, class_weight='balanced'
)
model.fit(X_tr, y_tr)

acc   = model.score(X_te, y_te)
probs = model.predict_proba(X_te)[:,1]
meta  = np.where(probs > 0.52, 1, 0)
prim  = df_t['primary_signal'].iloc[-len(y_te):].values
final = prim * meta
raw_r = df_t['future_ret'].iloc[-len(y_te):].values
meta_r = raw_r * (final != 0)

print(f"\n{'='*50}")
print(f"META-LABELING v2 RESULTS")
print(f"{'='*50}")
print(f"Breakout accuracy:    {(prim*raw_r>0).mean()*100:.1f}%")
print(f"Meta accuracy:        {acc*100:.1f}%")
print(f"Trades kept:          {(meta==1).mean()*100:.1f}%")
print(f"Raw Sharpe:    {np.mean(raw_r)/(np.std(raw_r)+1e-9)*np.sqrt(525600):.3f}")
print(f"Meta Sharpe:   {np.mean(meta_r)/(np.std(meta_r)+1e-9)*np.sqrt(525600):.3f}")
print(f"Win Rate:      {(meta_r>0).mean()*100:.1f}%")
print(f"{'='*50}")
