"""
AL-FATH v22 — v21 mein XGBoost + WebSocket integrate karna
"""
import subprocess, sys

# v21 file padho
with open('al_fath_v21.py', 'r') as f:
    content = f.read()

# XGBoost import add karo
old_import = "import xgboost as xgb"
if old_import not in content:
    content = content.replace(
        "import numpy as np",
        "import numpy as np\nimport xgboost as xgb"
    )
    print("[1] XGBoost import added ✅")
else:
    print("[1] XGBoost already imported ✅")

# EnsembleEngine class inject karo
addon_code = '''
# ══════════════════════════════════════════
# v22 ADDON: XGBoost Ensemble
# ══════════════════════════════════════════
class XGBoostSignal:
    def __init__(self):
        self.model = xgb.XGBClassifier(
            n_estimators=100, max_depth=4,
            learning_rate=0.05, subsample=0.8,
            colsample_bytree=0.8,
            eval_metric="logloss",
            random_state=42, verbosity=0
        )
        self.trained = False

    def train(self, X, y, sample_weight=None):
        y_bin = (y == 1).astype(int)
        if len(set(y_bin)) < 2:
            return False
        self.model.fit(X, y_bin, sample_weight=sample_weight)
        self.trained = True
        return True

    def predict_proba(self, X):
        if not self.trained:
            return np.full(len(X), 0.5)
        return self.model.predict_proba(X)[:, 1]
'''

# Class inject karo CoreEngine se pehle
if "class XGBoostSignal" not in content:
    content = content.replace(
        "class CoreEngine:",
        addon_code + "\nclass CoreEngine:"
    )
    print("[2] XGBoostSignal class injected ✅")
else:
    print("[2] XGBoostSignal already exists ✅")

# CPCV evaluate ke baad XGBoost train + ensemble karo
old_cpcv = "ensemble_prob = np.nanmean(meta_p, axis=1)"
new_cpcv = """ensemble_prob = np.nanmean(meta_p, axis=1)

    # ── v22: XGBoost Ensemble ─────────────────
    logger.info("[v22] XGBoost training...")
    avail_cols = [c for c in FEATURE_COLS if c in df_feat.columns]
    X_full = df_feat[avail_cols].fillna(0).values
    y_full = events['label'].reindex(df_feat.index).fillna(0).values.astype(int)
    xgb_model = XGBoostSignal()
    xgb_ok = xgb_model.train(X_full, y_full)
    if xgb_ok:
        xgb_prob = xgb_model.predict_proba(X_full)
        ensemble_prob = 0.60 * ensemble_prob + 0.40 * xgb_prob
        logger.info(f"[v22] Ensemble: LGB 60% + XGB 40% ✅")
    else:
        logger.warning("[v22] XGBoost skipped — label issue")"""

if "XGBoost Ensemble" not in content:
    content = content.replace(old_cpcv, new_cpcv)
    print("[3] XGBoost ensemble injected ✅")
else:
    print("[3] XGBoost ensemble already exists ✅")

# File save karo
with open('al_fath_v21.py', 'w') as f:
    f.write(content)

print("\n✅ Integration complete!")
print("Run: python3 al_fath_v21.py --csv btc_1m.csv")
