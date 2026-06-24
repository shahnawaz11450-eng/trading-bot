#!/usr/bin/env python3
"""
Feature Importance Checker for AL-FATH v21
Downloads real BTC data, generates the same 26 features used by al_fath_v21.py,
trains the same type of LightGBM model, and prints feature importance ranking.

This tells you which features are actually contributing to predictions
vs which ones are "dead weight" that could be removed.

Run from the al_fath_v21 directory:
    cd /root/al_fath_v21 && venv/bin/python check_feature_importance.py
"""

import sys
import numpy as np
import pandas as pd
import lightgbm as lgb

# Import directly from the main bot file
sys.path.insert(0, '/root/al_fath_v21')
from al_fath_v21 import download_binance_csv, CoreEngine, LabelEngine, FEATURE_COLS

def main():
    print("=" * 70)
    print("AL-FATH Feature Importance Checker")
    print("=" * 70)

    # 1. Download fresh real BTC data (same as al_fath_v21.py --download)
    print("\n[1/4] Downloading real BTC/USDT 1m data from Binance...")
    csv_path = download_binance_csv(symbol="BTCUSDT", interval="1m",
                                     limit=1000, max_batches=50,
                                     out_path="/tmp/fi_check_btc.csv")
    df_raw = pd.read_csv(csv_path)
    print(f"    Downloaded {len(df_raw)} bars -> {csv_path}")

    # 2. Generate the same 26 features
    print("\n[2/4] Generating features...")
    engine = CoreEngine()
    df_features = engine.generate_features(df_raw, df_raw, horizon=60)
    print(f"    Generated features. Shape: {df_features.shape}")

    # 3. Generate labels (triple barrier)
    print("\n[3/4] Generating triple-barrier labels...")
    label_engine = LabelEngine(horizon=60)
    labels_df = label_engine.generate_labels(df_features)
    df_features = df_features.join(labels_df[['label']], how='left')

    valid = df_features.dropna(subset=FEATURE_COLS + ['label'])
    X = valid[FEATURE_COLS]
    y = valid['label']

    print(f"    Valid rows for training: {len(X)}")
    print(f"    Label distribution: {y.value_counts().to_dict()}")

    # 4. Train the same type of model and extract feature importance
    print("\n[4/4] Training LightGBM model and extracting feature importance...")
    model = lgb.LGBMClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.03,
        num_leaves=16, class_weight='balanced',
        random_state=42, verbose=-1
    )
    model.fit(X.fillna(0), y)

    importances = pd.Series(
        model.feature_importances_, index=FEATURE_COLS
    ).sort_values(ascending=False)

    total = importances.sum()

    print("\n" + "=" * 70)
    print("FEATURE IMPORTANCE RANKING (LightGBM 'gain' / split count)")
    print("=" * 70)
    for i, (feat, score) in enumerate(importances.items(), 1):
        pct = (score / total * 100) if total > 0 else 0
        bar = "#" * int(pct / 2)
        print(f"{i:2d}. {feat:<22s} {score:>6.0f}  ({pct:5.1f}%)  {bar}")

    print("\n" + "=" * 70)
    print("WEAKEST FEATURES (candidates for removal):")
    print("=" * 70)
    weakest = importances.tail(8)
    for feat, score in weakest.items():
        pct = (score / total * 100) if total > 0 else 0
        print(f"  - {feat:<22s} {pct:5.1f}% of total importance")

    print("\nNOTE: Low importance does not automatically mean 'remove this'.")
    print("Re-run this a few times across different data windows before")
    print("deciding — importance can vary run to run, especially with")
    print("correlated features (removing one may shift importance to another).")


if __name__ == "__main__":
    main()

