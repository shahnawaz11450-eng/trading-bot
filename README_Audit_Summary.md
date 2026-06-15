# AL-FATH v21.0 — Audit Summary

## Phase 1: Validation Layer Fixes (Patches 1-3)

### Patch 1 — CPCV Overlap Purge
- Issue: `TrueCPCV.evaluate()` train/test split mein label-overlap purge missing tha
  (`events['t1']` ignored, despite `LabelEngine(horizon=60)`).
- Fix: overlap-based purge added — train samples jinka `t1` test-range overlap kare,
  exclude kiye gaye.
- Impact (synthetic data):
  | Metric | Before | After |
  |---|---|---|
  | Net EV Supervised | +4.75% | -0.88% |
  | PBO Supervised | 6.09% | 82.46% |
  | Lo HAC SR Supervised | +0.8222 | -0.1247 |
  - Direction: optimistic-bias removed, "no alpha" conclusion strengthened.

### Patch 2 — White RC / SPA Bootstrap Consistency
- Issue: observed statistic `nanmean(perf)` (per-column valid-count denominator)
  vs bootstrap `mean(nan_to_num(perf))` (full-T denominator) — asymmetric.
- Fix: bootstrap side switched to `nanmean` with `-inf` fallback for fully-NaN draws.
- Impact: minimal (White RC 0.7085→0.6320 on synthetic supervised; SPA unchanged at 1.0).
  Confirms RC/SPA results were not driven by this asymmetry.

### Patch 3 — Trade Reconstruction
- Added `reconstruct_trades()`: sign-based position-boundary reconstruction from
  `sig_exec`, producing entry/exit bars, holding period, regime, net/gross returns.
- Key finding (both synthetic AND real BTCUSDT data):
  | Metric | Synthetic | Real BTCUSDT |
  |---|---|---|
  | Holding period (mean/median) | 1.00 / 1.00 | 1.00 / 1.00 |
  | Win rate | 1.32% | 1.69% |
  | LONG mean return | -0.057% | -0.060% |
  | SHORT mean return | -0.058% | -0.051% |
  - Both directions equally negative → cost-driven loss, not directional bias.
  - 1-bar holding is structural/data-independent.

## Phase 2: Real Data Validation

- Real BTCUSDT 1m (2025-01, n=4000 after CPCV split):
  | Metric | Synthetic | Real |
  |---|---|---|
  | White RC (Supervised) | 0.7085 | 0.7105 |
  | HAC-SPA (Supervised) | 1.0000 ("No Edge") | 0.4845 ("Data Mined") |
  | PBO (Supervised) | 82.46% | 51.07% |
  | Lo HAC SR (ExecSim) | -4.75 | -9.94 |
  | Gate effect | -1823% (negative) | +22.36% (positive, both sides still negative) |

## Phase 3: IC Diagnostic (Decisive)

- Global Spearman IC between `sig_raw` (pre-MIN_HOLD, raw CPCV ensemble output)
  and `returns_horizon` (24-bar forward return), on non-zero signal bars:
  
  **IC = 0.0133, p = 0.4018, n = 3976**

- Conclusion: signal has **no statistically significant directional relationship**
  with future returns. This is consistent with White RC / SPA results.

## Final Conclusion

The raw signal (CPCV/LightGBM/XGBoost ensemble on current 26 features) shows
**no demonstrable predictive power**, on synthetic AND real data, before any
execution-layer processing. 

- "Signal exists but execution destroys it" — **REJECTED** (IC≈0, p=0.40)
- "Validation framework was hiding/inflating results" — **CONFIRMED and FIXED**
  (Patches 1-2), but underlying conclusion unchanged after fixing.
- Execution-layer redesign (state-machines, dynamic holding controllers) is
  **not justified** until feature-engineering/signal-generation produces a
  signal with IC significantly different from zero.

## Recommended Next Steps (separate project scope)
1. Feature engineering review — current 26 features insufficient for predictive edge
2. Label engineering review — triple-barrier params (pt=3 ATR, sl=1.5 ATR, horizon=60)
   vs prediction horizon (24) mismatch may need alignment
3. CPCV redesign (N=6,k=2 with true combinatorial paths) — secondary, only valuable
   once underlying signal shows non-zero IC
4. `Net EV (Raw)` relabeled to "Forward-Horizon Alpha Score" (Patch 4b) — cosmetic,
   prevents future misinterpretation
