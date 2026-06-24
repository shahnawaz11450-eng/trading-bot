# LSTM+GELU Experiment — v1

**Date:** 2025
**Dataset:** btc_5m_real.csv (50,000 bars, Jan–Jun 2024)
**Features:** Same 20 handcrafted features as LightGBM ensemble

## Results
| Metric | Value |
|--------|-------|
| LONG F1 | 0.076 |
| LONG Recall | 4.2% |
| IC (Spearman) | 0.0267 |
| Early stop | Epoch 7 / 30 |

## Decision
❌ No production integration

## Why LSTM underperformed (expected)
- Input was already-engineered tabular features (RSI, ATR, regime, etc.)
- Tree models dominate on this type of input
- LSTM had no access to raw OHLCV / order flow to learn sequence structure

## If deep learning revisited (future)
- Input: raw OHLCV + funding rate + OI + volume profile
- Architecture: Temporal CNN or Transformer (not LSTM on tabular features)
- Prerequisite: Fix Net EV < 0 and PBO issues first

## Priority order going forward
1. Signal quality (feature IC analysis)
2. CPCV robustness / PBO reduction
3. Market context features (funding rate, OI, perp basis)
4. Dashboard / monitoring
