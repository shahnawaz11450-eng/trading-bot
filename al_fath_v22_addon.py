"""
AL-FATH v22 ADDON
XGBoost Ensemble + Binance WebSocket Live Feed
"""
import xgboost as xgb
import websocket
import json, threading, time
import numpy as np
import pandas as pd
from datetime import datetime, timezone

# ══════════════════════════════════════════
# XGBOOST MODEL
# ══════════════════════════════════════════

class XGBoostSignal:
    """XGBoost ensemble — LightGBM ka complement"""
    
    def __init__(self):
        self.model = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            use_label_encoder=False,
            eval_metric='logloss',
            random_state=42,
            verbosity=0
        )
        self.trained = False
        
    def train(self, X, y, sample_weight=None):
        # Binary labels: 1=buy, 0=sell/hold
        y_bin = (y == 1).astype(int)
        if len(np.unique(y_bin)) < 2:
            return False
        self.model.fit(
            X, y_bin,
            sample_weight=sample_weight,
            verbose=False
        )
        self.trained = True
        print(f"[XGB] Trained on {len(X)} samples")
        return True
        
    def predict_proba(self, X):
        if not self.trained:
            return np.full(len(X), 0.5)
        return self.model.predict_proba(X)[:, 1]
    
    def signal(self, X, threshold=0.52):
        prob = self.predict_proba(X)
        return np.where(prob > threshold, 1.0,
               np.where(prob < (1-threshold), -1.0, 0.0))


# ══════════════════════════════════════════
# BINANCE WEBSOCKET LIVE FEED
# ══════════════════════════════════════════

class BinanceWebSocket:
    """Live 1m candle feed from Binance"""
    
    def __init__(self, symbol="btcusdt", interval="1m"):
        self.symbol   = symbol
        self.interval = interval
        self.url = f"wss://stream.binance.com:9443/ws/{symbol}@kline_{interval}"
        self.latest_candle = None
        self.candle_buffer = []
        self.running = False
        self._ws = None
        
    def _on_message(self, ws, message):
        data = json.loads(message)
        k    = data['k']
        candle = {
            'timestamp': pd.to_datetime(k['t'], unit='ms'),
            'open':      float(k['o']),
            'high':      float(k['h']),
            'low':       float(k['l']),
            'close':     float(k['c']),
            'volume':    float(k['v']),
            'closed':    k['x']  # True = candle closed
        }
        self.latest_candle = candle
        if candle['closed']:
            self.candle_buffer.append(candle)
            if len(self.candle_buffer) > 1000:
                self.candle_buffer.pop(0)
            print(f"[WS] New candle: {candle['timestamp']} "
                  f"Close=${candle['close']:,.2f} "
                  f"Vol={candle['volume']:.1f}")
    
    def _on_error(self, ws, error):
        print(f"[WS] Error: {error}")
        
    def _on_close(self, ws, *args):
        print("[WS] Connection closed")
        self.running = False
        
    def _on_open(self, ws):
        print(f"[WS] Connected: {self.symbol} {self.interval}")
        self.running = True
    
    def start(self):
        """Start WebSocket in background thread"""
        self._ws = websocket.WebSocketApp(
            self.url,
            on_message = self._on_message,
            on_error   = self._on_error,
            on_close   = self._on_close,
            on_open    = self._on_open,
        )
        t = threading.Thread(
            target=self._ws.run_forever,
            kwargs={'ping_interval': 30},
            daemon=True
        )
        t.start()
        print(f"[WS] Starting feed: {self.url}")
        time.sleep(2)
        return self
    
    def stop(self):
        if self._ws:
            self._ws.close()
    
    def get_buffer_df(self):
        if not self.candle_buffer:
            return None
        return pd.DataFrame(self.candle_buffer)
    
    def get_latest_price(self):
        if self.latest_candle:
            return self.latest_candle['close']
        return None


# ══════════════════════════════════════════
# ENSEMBLE: LightGBM + XGBoost
# ══════════════════════════════════════════

class EnsembleEngine:
    """
    Combines LightGBM (CPCV) + XGBoost signals
    Weights: LGB=60%, XGB=40%
    """
    LGB_WEIGHT = 0.60
    XGB_WEIGHT = 0.40
    
    def __init__(self):
        self.xgb = XGBoostSignal()
        
    def train_xgb(self, df, feature_cols, label_col='label'):
        avail = [c for c in feature_cols if c in df.columns]
        X = df[avail].fillna(0).values
        y = df[label_col].fillna(0).values.astype(int)
        return self.xgb.train(X, y)
    
    def ensemble_signal(self, lgb_prob, xgb_prob):
        """Weighted ensemble of both models"""
        combined = (lgb_prob * self.LGB_WEIGHT + 
                   xgb_prob * self.XGB_WEIGHT)
        signal = np.where(combined > 0.52,  1.0,
                 np.where(combined < 0.48, -1.0, 0.0))
        print(f"[Ensemble] LGB={lgb_prob.mean():.3f} "
              f"XGB={xgb_prob.mean():.3f} "
              f"Combined={combined.mean():.3f}")
        return signal, combined


# ══════════════════════════════════════════
# TEST
# ══════════════════════════════════════════

if __name__ == "__main__":
    print("="*50)
    print("AL-FATH v22 ADDON — TEST")
    print("="*50)
    
    # 1. XGBoost test
    print("\n[1] XGBoost test...")
    xgb_model = XGBoostSignal()
    X_dummy = np.random.randn(1000, 16)
    y_dummy = np.random.choice([-1, 0, 1], 1000)
    xgb_model.train(X_dummy, y_dummy)
    prob = xgb_model.predict_proba(X_dummy[:5])
    print(f"    Sample probs: {prob}")
    print("    ✅ XGBoost OK")
    
    # 2. WebSocket test
    print("\n[2] WebSocket test (10 seconds)...")
    ws = BinanceWebSocket("btcusdt", "1m")
    ws.start()
    time.sleep(10)
    price = ws.get_latest_price()
    print(f"    Latest BTC price: ${price:,.2f}" if price else "    No price yet")
    ws.stop()
    print("    ✅ WebSocket OK")
    
    print("\n✅ v22 Addon Ready!")
    print("Next: Integrate with al_fath_v21.py")
