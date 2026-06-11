import re

with open('al_fath_v21.py','r') as f:
    content=f.read()

inject_code='''
    # —— L4.5 VI+FUNDING META FILTER ——————————————————
    try:
        import ast, lightgbm as lgb
        from sklearn.metrics import roc_auc_score
        _eps=1e-9
        _df=df_feat.copy()
        _df['bar_dir']=(_df['close']>=_df['open']).astype(int)*2-1
        _df['buy_vol']=(_df['volume']*(_df['bar_dir']==1))
        _df['sell_vol']=(_df['volume']*(_df['bar_dir']==-1))
        _rb=_df['buy_vol'].rolling(10).sum()
        _rt=_rb+_df['sell_vol'].rolling(10).sum()+_eps
        _df['vi_ratio']=_rb/_rt
        _df['vi_imb']=_df['vi_ratio']-0.50
        _df['above_ma']=(_df['close']>_df['close'].rolling(20).mean()).astype(int)
        _df['trend_score']=_df['above_ma'].rolling(20).mean()
        _df['atr_pct']=(_df['high']-_df['low']).ewm(span=14,adjust=False).mean()/(_df['close']+_eps)
        _dff=pd.read_csv('btc_funding.csv')
        def _pfr(r):
            try: return float(ast.literal_eval(r['info']).get('fundingRate',0))
            except: return 0.0
        _dff['fr']=_dff.apply(_pfr,axis=1)
        _dff['dt']=pd.to_datetime(_dff['datetime'],utc=True).dt.tz_localize(None)
        _dff=_dff.set_index('dt')[['fr']].sort_index()
        _df=_df.merge(_dff,left_index=True,right_index=True,how='left')
        _df['fr']=_df['fr'].ffill().fillna(0)
        _df['fr_z']=(_df['fr']-_df['fr'].rolling(50).mean())/(_df['fr'].rolling(50).std()+_eps)
        _d=_df['close'].diff()
        _g=_d.clip(lower=0).ewm(span=14,adjust=False).mean()
        _l=(-_d.clip(upper=0)).ewm(span=14,adjust=False).mean()
        _df['rsi']=100-100/(1+_g/(_l+_eps))
        _df['rvol']=_df['volume']/(_df['volume'].rolling(30).mean()+_eps)
        _df['vol_ratio']=_df['volume']/(_df['volume'].shift(1)+_eps)
        _df['mom_3']=_df['close'].pct_change(3)
        _df['mom_12']=_df['close'].pct_change(12)
        _df['vi_slope']=_df['vi_imb'].diff(3)
        _df['vi_std']=_df['vi_imb'].rolling(10).std()
        _df['trend_str']=(_df['trend_score']-0.5).abs()*2
        _df['spread']=(_df['high']-_df['low'])/(_df['close']+_eps)
        _FC=['rsi','rvol','vol_ratio','mom_3','mom_12','vi_ratio','vi_imb',
             'vi_slope','vi_std','fr','fr_z','atr_pct','trend_str','spread']
        _df['_sr']=sig_raw
        _df['_fr']=_df['close'].pct_change(6).shift(-6)
        _df['_ml']=(_df['_sr']*_df['_fr']>0).astype(int)
        _df2=_df.dropna(subset=_FC+['_fr','_ml'])
        _df2=_df2[_df2['_sr']!=0]
        if len(_df2)>200:
            _si=int(len(_df2)*0.70); _pe=_si+6
            _Xtr=_df2[_FC].iloc[:_si]; _ytr=_df2['_ml'].iloc[:_si]
            _Xte=_df2[_FC].iloc[_pe:]
            _pw=(_ytr==0).sum()/max((_ytr==1).sum(),1)
            _m=lgb.LGBMClassifier(n_estimators=200,max_depth=4,learning_rate=0.03,
                num_leaves=16,scale_pos_weight=_pw,random_state=42,verbose=-1)
            _m.fit(_Xtr,_ytr)
            _pr=_m.predict_proba(_Xte)[:,1]
            _mask=np.ones(len(_df2),dtype=float)
            _mask[_pe:]=(_pr>=0.50).astype(float)
            _sig_idx=_df2.index
            _meta_series=pd.Series(_mask,index=_sig_idx)
            _meta_aligned=_meta_series.reindex(_df.index,fill_value=1.0)
            sig_raw=sig_raw*_meta_aligned.values
            _kept=(_pr>=0.50).mean()
            logger.info(f"[META-VI] Filter applied. Kept:{_kept*100:.1f}%")
        else:
            logger.warning("[META-VI] Not enough signal bars, skipping filter")
    except Exception as _e:
        logger.warning(f"[META-VI] Skipped: {_e}")
    # —— END META FILTER ————————————————————————————————
'''

target='    ensemble_prob = np.nanmean(meta_p, axis=1)'
if target in content:
    content=content.replace(target, target+'\n'+inject_code)
    with open('al_fath_v21.py','w') as f:
        f.write(content)
    print("SUCCESS: Meta filter injected after line 1763")
else:
    print("ERROR: Target line not found")
    print("Searching...")
    for i,line in enumerate(content.split('\n')):
        if 'ensemble_prob' in line:
            print(f"  Line {i}: {line}")
