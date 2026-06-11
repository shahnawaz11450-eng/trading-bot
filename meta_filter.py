import numpy as np
import lightgbm as lgb
from sklearn.metrics import roc_auc_score

def build_meta_filter(df, feat_cols, train_frac=0.70, purge=12, thresh=0.55):
    """
    Meta-label filter — sig_gated pe lagao
    Returns: meta_mask (array of 0/1, same length as df)
    """
    eps = 1e-9
    df = df.copy()

    # Features
    delta       = df['close'].diff()
    gain        = delta.clip(lower=0).ewm(span=14, adjust=False).mean()
    loss        = (-delta.clip(upper=0)).ewm(span=14, adjust=False).mean()
    df['rsi']   = 100 - 100 / (1 + gain / (loss + eps))
    df['rvol']  = df['volume'] / (df['volume'].rolling(50).mean() + eps)
    df['atr_pct'] = (df['high']-df['low']).ewm(span=14,adjust=False).mean()/(df['close']+eps)
    df['mom_10']  = df['close'].pct_change(10)
    df['mom_5']   = df['close'].pct_change(5)
    df['vol_ratio']= df['volume']/(df['volume'].shift(1)+eps)

    ema_fast = df['close'].ewm(span=10,adjust=False).mean()
    ema_slow = df['close'].ewm(span=30,adjust=False).mean()
    df['ema_spread'] = (ema_fast - ema_slow) / (df['close'] + eps)

    FEATS = ['rsi','rvol','atr_pct','mom_10','mom_5','vol_ratio','ema_spread']
    df['future_ret']  = df['close'].pct_change(12).shift(-12)
    df['meta_label']  = (df['ema_spread'] * df['future_ret'] > 0).astype(int)
    df = df.dropna(subset=FEATS+['future_ret','meta_label'])

    X = df[FEATS].fillna(0)
    y = df['meta_label']

    split   = int(len(X) * train_frac)
    purge_e = split + purge
    X_tr, y_tr = X.iloc[:split], y.iloc[:split]
    X_te       = X.iloc[purge_e:]

    if len(X_tr) < 100 or len(X_te) < 10:
        return np.ones(len(df), dtype=int)  # fallback: sab pass

    pw = (y_tr==0).sum() / max((y_tr==1).sum(), 1)
    model = lgb.LGBMClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.03,
        num_leaves=16, scale_pos_weight=pw,
        subsample=0.8, colsample_bytree=0.8,
        random_state=42, verbose=-1)
    model.fit(X_tr, y_tr)

    probs = model.predict_proba(X_te)[:,1]

    # Full array banao (train portion = 1 by default)
    mask = np.ones(len(df), dtype=int)
    mask[purge_e:] = (probs >= thresh).astype(int)

    print(f"  [META] Trades kept: {mask[purge_e:].mean()*100:.1f}%  "
          f"| Test AUC: {roc_auc_score(y.iloc[purge_e:], probs):.3f}")
    return mask, df.index
