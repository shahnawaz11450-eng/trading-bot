import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score

DATA_FILE='btc_1m.csv'; HOLD_BARS=15; VI_WINDOW=20; VI_THRESH=0.60
REGIME_WINDOW=50; ATR_PERIOD=14; META_THRESH=0.55
TRAIN_FRAC=0.70; PURGE_GAP=15; ANNUALIZE=np.sqrt(525600); eps=1e-9

print("Loading data...")
df=pd.read_csv(DATA_FILE,parse_dates=["timestamp"])
df=df.set_index("timestamp").sort_index()
print(f"  Rows: {len(df):,} | {df.index[0]} to {df.index[-1]}")

df["bar_dir"]=np.where(df["close"]>=df["open"],1,-1)
df["buy_vol"]=np.where(df["bar_dir"]==1,df["volume"],0.0)
df["sell_vol"]=np.where(df["bar_dir"]==-1,df["volume"],0.0)
roll_buy=df["buy_vol"].rolling(VI_WINDOW).sum()
roll_total=roll_buy+df["sell_vol"].rolling(VI_WINDOW).sum()+eps
df["vi_ratio"]=roll_buy/roll_total
df["vi_imb"]=df["vi_ratio"]-0.50

df["price_ma"]=df["close"].rolling(REGIME_WINDOW).mean()
df["atr"]=(df["high"]-df["low"]).ewm(span=ATR_PERIOD,adjust=False).mean()
df["atr_pct"]=df["atr"]/(df["close"]+eps)
df["above_ma"]=(df["close"]>df["price_ma"]).astype(int)
df["trend_score"]=df["above_ma"].rolling(REGIME_WINDOW).mean()
df["regime_trending"]=((df["trend_score"]>0.65)|(df["trend_score"]<0.35)).astype(int)
print(f"  Trending bars: {df['regime_trending'].sum():,} ({df['regime_trending'].mean()*100:.1f}%)")

df["primary_signal"]=np.where(
    (df["vi_ratio"]>VI_THRESH)&(df["trend_score"]>0.65)&(df["regime_trending"]==1),1,
    np.where(
    (df["vi_ratio"]<(1-VI_THRESH))&(df["trend_score"]<0.35)&(df["regime_trending"]==1),-1,0))

sig_count=(df["primary_signal"]!=0).sum()
print(f"  Signals: {sig_count:,} ({sig_count/len(df)*100:.2f}%)")

df["future_ret"]=df["close"].pct_change(HOLD_BARS).shift(-HOLD_BARS)
df["meta_label"]=(df["primary_signal"]*df["future_ret"]>0).astype(int)

delta=df["close"].diff()
gain=delta.clip(lower=0).ewm(span=14,adjust=False).mean()
loss=(-delta.clip(upper=0)).ewm(span=14,adjust=False).mean()
df["rsi"]=100-100/(1+gain/(loss+eps))
df["rvol"]=df["volume"]/(df["volume"].rolling(50).mean()+eps)
df["vol_ratio"]=df["volume"]/(df["volume"].shift(1)+eps)
df["vol_std"]=df["volume"].rolling(20).std()/(df["volume"].rolling(20).mean()+eps)
df["mom_5"]=df["close"].pct_change(5)
df["mom_15"]=df["close"].pct_change(15)
df["mom_60"]=df["close"].pct_change(60)
df["vi_slope"]=df["vi_imb"].diff(5)
df["vi_std"]=df["vi_imb"].rolling(20).std()
df["trend_str"]=(df["trend_score"]-0.5).abs()*2

FEAT_COLS=["rsi","rvol","vol_ratio","vol_std","mom_5","mom_15","mom_60","vi_ratio","vi_imb","vi_slope","vi_std","atr_pct","trend_str"]
df=df.dropna(subset=FEAT_COLS+["future_ret","meta_label"])
df_sig=df[df["primary_signal"]!=0].copy()
print(f"  Signal bars clean: {len(df_sig):,}")

X=df_sig[FEAT_COLS].fillna(0); y=df_sig["meta_label"]
split_idx=int(len(X)*TRAIN_FRAC); purge_end=split_idx+PURGE_GAP
X_tr,y_tr=X.iloc[:split_idx],y.iloc[:split_idx]
X_te,y_te=X.iloc[purge_end:],y.iloc[purge_end:]
print(f"  Train:{len(X_tr):,} Test:{len(X_te):,}")

pw=(y_tr==0).sum()/max((y_tr==1).sum(),1)
model=lgb.LGBMClassifier(n_estimators=300,max_depth=5,learning_rate=0.02,
    num_leaves=24,scale_pos_weight=pw,subsample=0.8,colsample_bytree=0.8,
    min_child_samples=50,random_state=42,verbose=-1)
model.fit(X_tr,y_tr,eval_set=[(X_te,y_te)],callbacks=[lgb.early_stopping(30,verbose=False)])

probs=model.predict_proba(X_te)[:,1]
meta_pred=(probs>=META_THRESH).astype(int)
acc=accuracy_score(y_te,meta_pred)
prec=precision_score(y_te,meta_pred,zero_division=0)
rec=recall_score(y_te,meta_pred,zero_division=0)
auc=roc_auc_score(y_te,probs)

primary_te=df_sig["primary_signal"].iloc[purge_end:].values
raw_ret=df_sig["future_ret"].iloc[purge_end:].values
raw_trade=np.sign(primary_te)*raw_ret
meta_trade=primary_te*meta_pred*raw_ret

def sharpe(r):
    a=r[r!=0]
    return a.mean()/(a.std()+eps)*ANNUALIZE if len(a)>1 else np.nan
def wr(r):
    a=r[r!=0]; return (a>0).mean() if len(a)>0 else 0.0

fi=pd.Series(model.feature_importances_,index=FEAT_COLS).sort_values(ascending=False)

print(f"\n{'='*52}")
print(f"  VOLUME IMBALANCE RESULTS")
print(f"{'='*52}")
print(f"  Primary win rate  : {wr(raw_trade)*100:.1f}%")
print(f"  Meta accuracy     : {acc*100:.1f}%")
print(f"  AUC-ROC           : {auc:.3f}")
print(f"  Precision/Recall  : {prec*100:.1f}% / {rec*100:.1f}%")
print(f"  Signals raw/meta  : {len(raw_trade):,} / {(meta_trade!=0).sum():,}")
print(f"  Trades kept       : {(meta_pred==1).mean()*100:.1f}%")
print(f"  Win rate raw/meta : {wr(raw_trade)*100:.1f}% / {wr(meta_trade)*100:.1f}%")
print(f"  Sharpe raw/meta   : {sharpe(raw_trade):.3f} / {sharpe(meta_trade):.3f}")
print(f"  Avg ret/trade     : {raw_trade[raw_trade!=0].mean()*100:.4f}% / {meta_trade[meta_trade!=0].mean()*100:.4f}%")
print(f"\n  Top Features:")
for f,i in fi.head(6).items():
    print(f"    {'#'*int(i/fi.max()*20)} {f} {i:.0f}")
print(f"\n  CHECKS:")
checks=[("Win rate>50%",wr(meta_trade)>0.50),("Sharpe>0",sharpe(meta_trade)>0),
    ("AUC>0.52",auc>0.52),("Kept 20-80%",0.20<(meta_pred==1).mean()<0.80),
    ("Avg ret>0",meta_trade[meta_trade!=0].mean()>0)]
for n,p in checks: print(f"    {'OK' if p else 'XX'} {n}")
print(f"  [{sum(p for _,p in checks)}/{len(checks)}] Score")
print(f"{'='*52}")
