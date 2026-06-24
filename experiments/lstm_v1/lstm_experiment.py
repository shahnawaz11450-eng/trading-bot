#!/usr/bin/env python3
"""
LSTM+GELU Model for AL-FATH v21
Trains a sequence-based LSTM model (with GELU activation in its head) on the
same 20 features used by the LightGBM/XGBoost ensemble, to evaluate whether
a deep learning approach adds predictive value.

This is a STANDALONE EXPERIMENT script. It does not modify al_fath_v21.py.
Results here should be compared against the existing LightGBM CPCV results
before deciding whether to integrate LSTM into the main pipeline.

FIXES APPLIED vs original:
  FIX-1: Train-only normalization (no data leakage from val/test into train mean/std)
  FIX-2: classification_report for F1/Precision/Recall (accuracy alone is misleading)
  FIX-3: Softmax probability outputs stored (needed for IC / EV comparison vs LightGBM)
  FIX-4: 60/20/20 split with early stopping on val loss (was 70/30, no early stop)
  FIX-5: Random seeds for reproducibility

Run from the al_fath_v21 directory:
    cd /root/al_fath_v21 && venv/bin/python lstm_experiment.py
"""

import sys
import time
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from sklearn.metrics import classification_report

# ── Reproducibility ──────────────────────────────────────────────────────────
SEED = 42
torch.manual_seed(SEED)
np.random.seed(SEED)

sys.path.insert(0, '/root/al_fath_v21')
from al_fath_v21 import download_binance_csv, CoreEngine, LabelEngine, FEATURE_COLS

# ── Hyperparameters ───────────────────────────────────────────────────────────
SEQ_LEN      = 120   # 2 hours of 1-minute bars (try 30/60/240 to compare)
BATCH_SIZE   = 256
EPOCHS       = 30    # more epochs; early stopping will cut off when val loss stagnates
HIDDEN_SIZE  = 64
LEARNING_RATE = 1e-3
PATIENCE     = 5     # early stopping patience


# ── Model ─────────────────────────────────────────────────────────────────────
class GELUHead(nn.Module):
    def __init__(self, input_size, num_classes=3):
        super().__init__()
        self.fc1  = nn.Linear(input_size, 32)
        self.gelu = nn.GELU()
        self.fc2  = nn.Linear(32, num_classes)

    def forward(self, x):
        return self.fc2(self.gelu(self.fc1(x)))


class LSTMClassifier(nn.Module):
    def __init__(self, n_features, hidden_size=HIDDEN_SIZE, num_classes=3):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=n_features, hidden_size=hidden_size,
            num_layers=2, batch_first=True, dropout=0.2
        )
        self.head = GELUHead(hidden_size, num_classes)

    def forward(self, x):
        _, (h_n, _) = self.lstm(x)
        return self.head(h_n[-1])


# ── Dataset ───────────────────────────────────────────────────────────────────
class SequenceDataset(Dataset):
    def __init__(self, X, y, seq_len):
        self.X, self.y, self.seq_len = X, y, seq_len

    def __len__(self):
        return len(self.X) - self.seq_len

    def __getitem__(self, idx):
        seq   = self.X[idx : idx + self.seq_len]
        label = self.y[idx + self.seq_len]
        return torch.tensor(seq, dtype=torch.float32), torch.tensor(label, dtype=torch.long)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("AL-FATH LSTM+GELU Experiment  (Fixed)")
    print(f"SEQ_LEN={SEQ_LEN} | HIDDEN={HIDDEN_SIZE} | MAX_EPOCHS={EPOCHS} | PATIENCE={PATIENCE}")
    print("=" * 70)

    device = torch.device("cpu")
    print(f"\nDevice: {device}")

    # ── 1. Load data ──────────────────────────────────────────────────────────
    print("\n[1/5] Loading BTC/USDT data...")
    csv_path = "/root/al_fath_v21/btc_5m_real.csv"   # prefer real 5m dataset
    if not __import__('os').path.exists(csv_path):
        csv_path = "/root/al_fath_v21/btc_1m.csv"
    try:
        df_raw = pd.read_csv(csv_path)
        print(f"    Using {csv_path} ({len(df_raw):,} bars)")
    except FileNotFoundError:
        csv_path = download_binance_csv(symbol="BTCUSDT", interval="1m",
                                        limit=1000, max_batches=50,
                                        out_path="/root/al_fath_v21/btc_1m.csv")
        df_raw = pd.read_csv(csv_path)
        print(f"    Downloaded {len(df_raw):,} bars")

    # ── 2. Features + labels ──────────────────────────────────────────────────
    print("\n[2/5] Generating features and labels...")
    engine = CoreEngine()
    df_feat = engine.generate_features(df_raw, df_raw, horizon=24)
    label_engine = LabelEngine(horizon=24)
    labels_df = label_engine.generate_labels(df_feat)
    df_feat = df_feat.join(labels_df[['label']], how='left')

    valid = df_feat.dropna(subset=FEATURE_COLS + ['label']).reset_index(drop=True)
    print(f"    Valid rows: {len(valid):,}")

    label_map = {-1: 0, 0: 1, 1: 2}
    y = valid['label'].map(label_map).values
    X = valid[FEATURE_COLS].values.astype(np.float32)

    # ── 3. Split THEN normalize (FIX-1: no leakage) ──────────────────────────
    print("\n[3/5] Splitting 60/20/20 chronologically, normalizing on train only...")
    n = len(X)
    train_end = int(n * 0.60)
    val_end   = int(n * 0.80)

    X_train, y_train = X[:train_end],        y[:train_end]
    X_val,   y_val   = X[train_end:val_end], y[train_end:val_end]
    X_test,  y_test  = X[val_end:],          y[val_end:]

    # Fit scaler on train only
    X_mean = X_train.mean(axis=0)
    X_std  = X_train.std(axis=0) + 1e-9
    X_train = (X_train - X_mean) / X_std
    X_val   = (X_val   - X_mean) / X_std
    X_test  = (X_test  - X_mean) / X_std

    train_ds = SequenceDataset(X_train, y_train, SEQ_LEN)
    val_ds   = SequenceDataset(X_val,   y_val,   SEQ_LEN)
    test_ds  = SequenceDataset(X_test,  y_test,  SEQ_LEN)

    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=False)
    val_loader   = DataLoader(val_ds,   batch_size=BATCH_SIZE, shuffle=False)
    test_loader  = DataLoader(test_ds,  batch_size=BATCH_SIZE, shuffle=False)

    print(f"    Train: {len(train_ds):,} | Val: {len(val_ds):,} | Test: {len(test_ds):,}")

    # Class weights from train set only
    class_counts   = np.bincount(y_train[SEQ_LEN:], minlength=3)
    class_weights  = len(y_train[SEQ_LEN:]) / (3 * np.maximum(class_counts, 1))
    class_weights_t = torch.tensor(class_weights, dtype=torch.float32)
    print(f"    Class counts (train): SHORT={class_counts[0]}  NEUTRAL={class_counts[1]}  LONG={class_counts[2]}")
    print(f"    Class weights:        {class_weights.round(3)}")

    # ── 4. Train with early stopping ──────────────────────────────────────────
    print(f"\n[4/5] Training LSTM+GELU (max {EPOCHS} epochs, early stop patience={PATIENCE})...")
    model     = LSTMClassifier(n_features=len(FEATURE_COLS)).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=LEARNING_RATE)
    criterion = nn.CrossEntropyLoss(weight=class_weights_t)

    best_val_loss   = float('inf')
    patience_counter = 0
    best_state      = None

    for epoch in range(1, EPOCHS + 1):
        # -- train --
        model.train()
        t0 = time.time()
        train_loss = 0.0
        n_batches  = 0
        for xb, yb in train_loader:
            optimizer.zero_grad()
            loss = criterion(model(xb), yb)
            loss.backward()
            optimizer.step()
            train_loss += loss.item()
            n_batches  += 1

        # -- validate --
        model.eval()
        val_loss = 0.0
        vb_count = 0
        with torch.no_grad():
            for xb, yb in val_loader:
                val_loss += criterion(model(xb), yb).item()
                vb_count += 1
        val_loss /= max(vb_count, 1)

        elapsed = time.time() - t0
        print(f"    Epoch {epoch:02d}/{EPOCHS} | train_loss={train_loss/n_batches:.4f} "
              f"| val_loss={val_loss:.4f} | {elapsed:.1f}s", end="")

        if val_loss < best_val_loss:
            best_val_loss    = val_loss
            patience_counter = 0
            best_state       = {k: v.clone() for k, v in model.state_dict().items()}
            print("  ✓ best")
        else:
            patience_counter += 1
            print(f"  (patience {patience_counter}/{PATIENCE})")
            if patience_counter >= PATIENCE:
                print(f"\n    Early stop at epoch {epoch}.")
                break

    # Restore best weights
    if best_state:
        model.load_state_dict(best_state)

    # ── 5. Evaluate ───────────────────────────────────────────────────────────
    print("\n[5/5] Evaluating on held-out test set...")
    model.eval()
    all_preds, all_labels, all_probs = [], [], []

    with torch.no_grad():
        for xb, yb in test_loader:
            logits     = model(xb)
            probs      = torch.softmax(logits, dim=1)   # FIX-3: probability outputs
            pred_labels = logits.argmax(dim=1)
            all_preds.extend(pred_labels.tolist())
            all_labels.extend(yb.tolist())
            all_probs.extend(probs.tolist())

    all_preds  = np.array(all_preds)
    all_labels = np.array(all_labels)
    all_probs  = np.array(all_probs)   # shape: (N, 3)

    accuracy = (all_preds == all_labels).mean()

    print(f"\n{'='*70}")
    print(f"RESULTS  (test set, n={len(all_labels):,})")
    print(f"{'='*70}")
    print(f"Accuracy : {accuracy*100:.2f}%  (random 3-class baseline ~33%)")

    # FIX-2: Full classification report
    print(f"\nClassification Report:")
    print(classification_report(
        all_labels, all_preds,
        target_names=['SHORT(-1)', 'NEUTRAL(0)', 'LONG(+1)'],
        digits=3
    ))

    # IC (Information Coefficient) — Spearman corr between P(long)-P(short) and actual direction
    # Map labels back to -1/0/1 for IC calculation
    actual_dir  = all_labels - 1                     # 0,1,2 → -1,0,1
    pred_signal = all_probs[:, 2] - all_probs[:, 0]  # P(long) - P(short)
    from scipy.stats import spearmanr
    ic, ic_pval = spearmanr(pred_signal, actual_dir)
    print(f"IC (Spearman P(long)-P(short) vs actual): {ic:.4f}  p={ic_pval:.4f}")
    print(f"  → IC > 0.05 with p < 0.05 is meaningful for trading")

    # Save probability outputs for further analysis
    prob_df = pd.DataFrame({
        'p_short':   all_probs[:, 0],
        'p_neutral': all_probs[:, 1],
        'p_long':    all_probs[:, 2],
        'pred':      all_preds,
        'actual':    all_labels,
    })
    out_path = "/root/al_fath_v21/lstm_probs.csv"
    prob_df.to_csv(out_path, index=False)
    print(f"\nProbability outputs saved to: {out_path}")

    print(f"\n{'='*70}")
    print("NEXT STEPS (before integrating into production):")
    print("  1. Compare IC above with LightGBM ensemble IC from CPCV run")
    print("  2. Run with SEQ_LEN in [30, 60, 240] to find optimal window")
    print("  3. If IC > LightGBM IC consistently → worth adding as 3rd ensemble member")
    print("  4. Full CPCV validation needed (not just this single chronological split)")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()

