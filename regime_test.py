import pandas as pd, numpy as np, sys
sys.path.insert(0, '/root/al_fath_v21')
from al_fath_v21 import CoreEngine, LabelEngine
from lightgbm import LGBMClassifier
from sklearn.metrics import f1_score
import warnings; warnings.filterwarnings('ignore')

df_raw = pd.read_csv('btc_5m_real.csv')
engine = CoreEngine()
df_feat = engine.generate_features(df_raw, df_raw, horizon=24)
label_engine = LabelEngine(horizon=24)
labels_df = label_engine.generate_labels(df_feat)
df_feat = df_feat.join(labels_df[['label']], how='left')
valid = df_feat.dropna(subset=['label']).reset_index(drop=True)
y = valid['label'].astype(int)

valid['regime_bearish'] = (valid['close'].pct_change(200) < -0.05).astype(int)
n = len(valid)
fold_size = n // 5

FULL_20 = ['rsi_14','macd_hist','bb_pct','atr_pct','obv_momentum',
           'vwap_dist','stoch_k','stoch_d','williams_r','cci_20',
           'momentum_10','vol_momentum','hl_range','close_position',
           'funding_rate','funding_extreme','oi_change',
           'rvol','vol_breakout','atr_expansion']

model = LGBMClassifier(n_estimators=100, max_depth=4,
                       class_weight='balanced', random_state=42, verbose=-1)

print(f"{'Fold':<6} {'Regime':<12} {'F1_all':>8} {'F1_bull_only':>13}")
print("-"*45)

X = valid[FULL_20].fillna(0).values

for i in range(1, 5):
    train_end = i * fold_size
    test_end  = min((i+1)*fold_size, n)
    print(f"W{i+1}: training on {train_end} bars...", flush=True)
    model.fit(X[:train_end], y[:train_end])
    preds_all = model.predict(X[train_end:test_end])
    f1_all = f1_score(y[train_end:test_end], preds_all,
                      labels=[1], average='macro', zero_division=0)

    test_slice = valid.iloc[train_end:test_end]
    bull_mask = test_slice['regime_bearish'].values == 0
    f1_bull = 0.0
    if bull_mask.sum() > 100:
        preds_bull = model.predict(X[train_end:test_end][bull_mask])
        f1_bull = f1_score(y[train_end:test_end][bull_mask], preds_bull,
                           labels=[1], average='macro', zero_division=0)

    bear_pct = test_slice['regime_bearish'].mean() * 100
    print(f"W{i+1:<5} {bear_pct:.0f}% bear    {f1_all:>8.3f} {f1_bull:>13.3f}")

print("Done.")
