"""
10 Alpha Features ko al_fath_v21.py mein inject karo
"""

with open('al_fath_v21.py', 'r') as f:
    content = f.read()

# 1. New FEATURE_COLS add karo
old_cols = """FEATURE_COLS = [
    'rsi_14','macd_hist','bb_pct','atr_pct','obv_momentum',
    'vwap_dist','stoch_k','stoch_d','pseudo_cvd_momentum',
    'williams_r','cci_20','momentum_10','vol_momentum',
    'hl_range','close_position','is_missing_bar'
]"""

new_cols = """FEATURE_COLS = [
    'rsi_14','macd_hist','bb_pct','atr_pct','obv_momentum',
    'vwap_dist','stoch_k','stoch_d','pseudo_cvd_momentum',
    'williams_r','cci_20','momentum_10','vol_momentum',
    'hl_range','close_position','is_missing_bar',
    # v22 Alpha Features
    'funding_rate','funding_extreme','funding_negative',
    'oi_change','oi_rising',
    'rvol','vol_breakout','atr_expansion',
    'bearish_divergence','bullish_divergence'
]"""

if 'funding_rate' not in content:
    content = content.replace(old_cols, new_cols)
    print("[1] FEATURE_COLS updated ✅")
else:
    print("[1] Features already added ✅")

# 2. FeatureLineageDAG mein new features add karo
old_dag = "        'is_missing_bar':['is_missing_bar[0]'],"
new_dag = """        'is_missing_bar':['is_missing_bar[0]'],
        # v22 Alpha
        'funding_rate':['funding_rate[0]'],
        'funding_extreme':['funding_rate[0]'],
        'funding_negative':['funding_rate[0]'],
        'oi_change':['oi[0:t]'],
        'oi_rising':['oi[0:t]'],
        'rvol':['volume[-100:]'],
        'vol_breakout':['volume[-100:]'],
        'atr_expansion':['high[-50:]','low[-50:]','close[-50:]'],
        'bearish_divergence':['close[-40:]','high[-40:]'],
        'bullish_divergence':['close[-40:]','low[-40:]'],"""

if 'funding_rate' not in content:
    content = content.replace(old_dag, new_dag)
    print("[2] DAG updated ✅")
else:
    print("[2] DAG already updated ✅")

# 3. generate_features mein alpha features add karo
old_gen = "        df['close_position']=(df['close']-df['low'])/(df['high']-df['low']+1e-9)"

new_gen = """        df['close_position']=(df['close']-df['low'])/(df['high']-df['low']+1e-9)
        # ── v22 Alpha Features ──────────────────
        try:
            alpha = pd.read_csv('btc_alpha_features.csv')
            alpha['timestamp'] = pd.to_datetime(alpha['timestamp'])
            alpha = alpha.set_index('timestamp')
            for col in ['funding_rate','funding_extreme','funding_negative',
                        'oi_change','oi_rising','rvol','vol_breakout',
                        'atr_expansion','bearish_divergence','bullish_divergence']:
                if col in alpha.columns:
                    df[col] = alpha[col].reindex(df.index).ffill().fillna(0)
                else:
                    df[col] = 0.0
        except Exception as e:
            for col in ['funding_rate','funding_extreme','funding_negative',
                        'oi_change','oi_rising','rvol','vol_breakout',
                        'atr_expansion','bearish_divergence','bullish_divergence']:
                df[col] = 0.0"""

if 'v22 Alpha Features' not in content:
    content = content.replace(old_gen, new_gen)
    print("[3] generate_features updated ✅")
else:
    print("[3] Alpha features already injected ✅")

with open('al_fath_v21.py', 'w') as f:
    f.write(content)

print("\n✅ Injection complete!")
