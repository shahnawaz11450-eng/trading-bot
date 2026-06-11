"""
AL-FATH Meta-Labeling
Primary Signal: Trend Breakout
Secondary ML: Trade lena hai ya skip?
"""
import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.model_selection import train_test_split

# Load data
print("Loading data...")
df = pd.read_csv('btc_1m.csv')
df['timestamp'] = pd.to_datetime(df['timestamp'])
df = df.set_index('timestamp').sort_index()

# Primary Signal: EMA Crossover Breakout
df['ema_fast'] = df['close'].ewm(span=10).mean()
df['ema_slow'] = df['close'].ewm(span=30).mean()
df['primary_signal'] = np.where(
    df['ema_fast'] > df['ema_slow'], 1, -1
)

# Future return
df['future_ret'] = df['close'].pct_change(12).shift(-12)

# Meta Label: Primary signal sahi tha?
df['meta_label'] = (
    df['primary_signal'] * df['future_ret'] > 0
).astype(int)

# Features
df['rsi'] = 100 - 100/(1 + 
    df['close'].diff().clip(lower=0).ewm(span=14).mean() /
    (-df['close'].diff().clip(upper=0)).ewm(span=14).mean())
df['rvol'] = df['volume'] / df['volume'].rolling(50).mean()
df['atr'] = (df['high']-df['low']).ewm(span=14).mean()
df['momentum'] = df['close'].pct_change(10)
df['vol_ratio'] = df['volume'] / df['volume'].shift(1)

feat_cols = ['rsi','rvol','atr','momentum','vol_ratio']
df = df.dropna()

# Only train on primary signal bars
mask = df['primary_signal'] != 0
df_train = df[mask].copy()

X = df_train[feat_cols].fillna(0)
y = df_train['meta_label']

# Split
X_tr, X_te, y_tr, y_te = train_test_split(
    X, y, test_size=0.2, shuffle=False
)

# Train
model = lgb.LGBMClassifier(
    n_estimators=100, max_depth=4,
    learning_rate=0.05, random_state=42,
    verbose=-1
)
model.fit(X_tr, y_tr)

# Evaluate
acc = model.score(X_te, y_te)
probs = model.predict_proba(X_te)[:,1]

# Meta signal
meta_signal = np.where(probs > 0.52, 1, 0)
primary = df_train['primary_signal'].iloc[-len(y_te):].values
final_signal = primary * meta_signal

# Results
raw_ret = df_train['future_ret'].iloc[-len(y_te):].values
meta_ret = raw_ret * (final_signal != 0)

print(f"\n{'='*50}")
print(f"META-LABELING RESULTS")
print(f"{'='*50}")
print(f"Primary accuracy:     {(primary * raw_ret > 0).mean()*100:.1f}%")
print(f"Meta filter accuracy: {acc*100:.1f}%")
print(f"Trades kept:          {(meta_signal==1).mean()*100:.1f}%")
print(f"Raw Sharpe:           {np.mean(raw_ret)/np.std(raw_ret)*np.sqrt(525600):.3f}")
print(f"Meta Sharpe:          {np.mean(meta_ret)/np.std(meta_ret)*np.sqrt(525600):.3f}")
print(f"{'='*50}")
