import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.metrics import accuracy_score,precision_score,recall_score,roc_auc_score
import ast
HOLD_BARS=6;VI_WINDOW=10;VI_THRESH=0.62
META_THRESH=0.50;TRAIN_FRAC=0.70;PURGE_GAP=6
ANNUALIZE=np.sqrt(105120);eps=1e-9
print("Loading 5m data...")
df=pd.read_csv('btc_5m.csv',parse_dates=['timestamp'])
df=df.set_index('timestamp').sort_index()
print(f"  5m rows: {len(df):,} | {df.index[0]} to {df.index[-1]}")
dff=pd.read_csv('btc_funding.csv')
def parse_fr(row):
    try: return float(ast.literal_eval(row['info']).get('fundingRate',0))
    except: return float(row.get('fundingRate',0))
dff['fr']=dff.apply(parse_fr,axis=1)
dff['dt']=pd.to_datetime(dff['datetime'],utc=True).dt.tz_localize(None)
dff=dff.set_index('dt')[['fr']].sort_index()
df=df.merge(dff,left_index=True,right_index=True,how='left')
df['fr']=df['fr'].ffill().fillna(0)
df['bar_dir']=np.where(df['close']>=df['open'],1,-1)
df['buy_vol']=np.where(df['bar_dir']==1,df['volume'],0.0)
df['sell_vol']=np.where(df['bar_dir']==-1,df['volume'],0.0)
rb=df['buy_vol'].rolling(VI_WINDOW).sum()
rt=rb+df['sell_vol'].rolling(VI_WINDOW).sum()+eps
df['vi_ratio']=rb/rt
df['vi_imb']=df['vi_ratio']-0.50
df['price_ma']=df['close'].rolling(20).mean()
df['above_ma']=(df['close']>df['price_ma']).astype(int)
df['trend_score']=df['above_ma'].rolling(20).mean()
df['atr']=(df['high']-df['low']).ewm(span=14,adjust=False).mean()
df['atr_pct']=df['atr']/(df['close']+eps)
df['fr_z']=(df['fr']-df['fr'].rolling(50).mean())/(df['fr'].rolling(50).std()+eps)
cl=(df['vi_ratio']>VI_THRESH)&(df['trend_score']>0.60)&(df['fr_z']<0.5)
cs=(df['vi_ratio']<(1-VI_THRESH))&(df['trend_score']<0.40)&(df['fr_z']>-0.5)
df['primary_signal']=np.where(cl,1,np.where(cs,-1,0))
sn=(df['primary_signal']!=0).sum()
print(f"  Signals: {sn:,} ({sn/len(df)*100:.1f}%)")
df['future_ret']=df['close'].pct_change(HOLD_BARS).shift(-HOLD_BARS)
df['meta_label']=(df['primary_signal']*df['future_ret']>0).astype(int)
delta=df['close'].diff()
gain=delta.clip(lower=0).ewm(span=14,adjust=False).mean()
loss=(-delta.clip(upper=0)).ewm(span=14,adjust=False).mean()
df['rsi']=100-100/(1+gain/(loss+eps))
df['rvol']=df['volume']/(df['volume'].rolling(30).mean()+eps)
df['vol_ratio']=df['volume']/(df['volume'].shift(1)+eps)
df['mom_3']=df['close'].pct_change(3)
df['mom_12']=df['close'].pct_change(12)
df['vi_slope']=df['vi_imb'].diff(3)
df['vi_std']=df['vi_imb'].rolling(10).std()
df['trend_str']=(df['trend_score']-0.5).abs()*2
df['spread']=(df['high']-df['low'])/(df['close']+eps)
FC=['rsi','rvol','vol_ratio','mom_3','mom_12','vi_ratio','vi_imb','vi_slope','vi_std','fr','fr_z','atr_pct','trend_str','spread']
df=df.dropna(subset=FC+['future_ret','meta_label'])
ds=df[df['primary_signal']!=0].copy()
print(f"  Clean signals: {len(ds):,} | Labels 1:{(ds['meta_label']==1).sum()} 0:{(ds['meta_label']==0).sum()}")
X=ds[FC].fillna(0);y=ds['meta_label']
si=int(len(X)*TRAIN_FRAC);pe=si+PURGE_GAP
Xtr,ytr=X.iloc[:si],y.iloc[:si]
Xte,yte=X.iloc[pe:],y.iloc[pe:]
print(f"  Train:{len(Xtr):,} Test:{len(Xte):,}")
pw=(ytr==0).sum()/max((ytr==1).sum(),1)
m=lgb.LGBMClassifier(n_estimators=300,max_depth=5,learning_rate=0.02,num_leaves=20,
    scale_pos_weight=pw,subsample=0.8,colsample_bytree=0.8,min_child_samples=30,random_state=42,verbose=-1)
m.fit(Xtr,ytr,eval_set=[(Xte,yte)],callbacks=[lgb.early_stopping(30,verbose=False)])
pr=m.predict_proba(Xte)[:,1];mp=(pr>=META_THRESH).astype(int)
acc=accuracy_score(yte,mp);prec=precision_score(yte,mp,zero_division=0)
rec=recall_score(yte,mp,zero_division=0);auc=roc_auc_score(yte,pr)
pt=ds['primary_signal'].iloc[pe:].values;rr=ds['future_ret'].iloc[pe:].values
rt2=np.sign(pt)*rr;mt=pt*mp*rr
def sh(r):
    a=r[r!=0]; return a.mean()/(a.std()+eps)*ANNUALIZE if len(a)>1 else np.nan
def wr(r):
    a=r[r!=0]; return (a>0).mean() if len(a)>0 else 0.0
fi=pd.Series(m.feature_importances_,index=FC).sort_values(ascending=False)
print(f"\n{'='*50}\n  5m VI + FUNDING RESULTS\n{'='*50}")
print(f"  Primary WR    : {wr(rt2)*100:.1f}%")
print(f"  Meta accuracy : {acc*100:.1f}% | AUC: {auc:.3f}")
print(f"  Precision     : {prec*100:.1f}% | Recall: {rec*100:.1f}%")
print(f"  Signals       : {len(rt2):,} -> {(mt!=0).sum():,} ({(mp==1).mean()*100:.1f}% kept)")
print(f"  WR raw/meta   : {wr(rt2)*100:.1f}% / {wr(mt)*100:.1f}%")
print(f"  Sharpe r/m    : {sh(rt2):.3f} / {sh(mt):.3f}")
if (mt!=0).sum()>0: print(f"  Avg ret r/m   : {rt2[rt2!=0].mean()*100:.4f}% / {mt[mt!=0].mean()*100:.4f}%")
print(f"\n  Top Features:")
for f,i in fi.head(6).items(): print(f"    {'#'*int(i/fi.max()*20)} {f}")
cks=[("WR>50%",wr(mt)>0.50),("Sharpe>0",not np.isnan(sh(mt)) and sh(mt)>0),
    ("AUC>0.52",auc>0.52),("Kept 20-80%",0.20<(mp==1).mean()<0.80),
    ("AvgRet>0",(mt!=0).sum()>0 and mt[mt!=0].mean()>0)]
print(f"\n  CHECKS:")
for n,p in cks: print(f"    {'OK' if p else 'XX'} {n}")
print(f"  [{sum(p for _,p in cks)}/{len(cks)}] Score\n{'='*50}")
