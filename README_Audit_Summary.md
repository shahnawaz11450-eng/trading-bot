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

## Addendum: Independent EMA-Crossover Signal Test (meta_label.py)

A separate, simpler primary signal (EMA(10) vs EMA(30) crossover) was tested
independently via `meta_label.py`, with a meta-labeling filter on top.

Results:
- Primary signal accuracy: 47.2% (sub-random, i.e. worse than a coin flip)
- Meta-filter accuracy: 51.2% (statistically indistinguishable from random)
- Trades kept after filter: 7.3% (very small, high-variance subset)
- Reported Sharpe ratios (Raw: 2.851, Meta: -2.953) are inflated by aggressive
  per-minute-to-annual scaling (`sqrt(525600)`) and should not be trusted at
  face value — consistent with the overlapping-window inflation issue found
  in the main `Net EV (Raw)` metric.

Conclusion: this independent, simpler signal-generation approach reaches the
same conclusion as the main CPCV-based pipeline — no demonstrable predictive
edge in the current feature/signal design. `meta_filter.py` and `meta_label.py`
are kept as reference/archive, not merged into the active `al_fath_v21.py`
pipeline.

## Phase 4: Label-Horizon Alignment Fix + Critical Data Bugs Found

### Bug Fix 1: Label/Feature Horizon Mismatch
- Issue: generate_features(horizon=24) produced returns_horizon on a 24-bar
  window, while LabelEngine(horizon=60) trained the model on 60-bar triple-barrier
  labels. The IC diagnostic was comparing the signal against the wrong horizon.
- Fix: aligned generate_features(horizon=60) to match LabelEngine.

### Bug Fix 2: Hardcoded Resample Frequency
- Issue: DataIntegrityAuditor.audit_and_clean() had freq='5min' hardcoded in
  pd.date_range(...), causing incorrect alignment when processing 1-minute
  datasets. This affected earlier BTCUSDT audit runs and likely contributed to
  the unexpected row-count reductions observed during testing.
- Fix: frequency now inferred dynamically via pd.infer_freq() with fallback.

### Bug Fix 3: download_binance_csv() Timestamp Bug
- Issue: integrated download_binance_csv() wrote raw millisecond epoch integers
  without conversion, misinterpreted as nanoseconds by pd.to_datetime(),
  silently corrupting dates (collapsed to 1970-01-01).
- Fix: timestamps converted to ISO datetime strings at download time.

### Result After All Fixes (real BTCUSDT, n=19940 non-zero signal bars)

| Metric | Before fixes | After fixes |
|---|---|---|
| IC (Spearman) | 0.0133 | 0.0252 |
| IC p-value | 0.4018 | 0.0004 |
| White RC (Supervised) | 0.7105 | 0.8100 |
| HAC-SPA (Supervised) | 0.4845 | 0.4665 |
| PBO (Supervised) | 51.07% | 76.99% |
| Lo HAC SR (Supervised) | -3.28 | -8.30 |
| Lo HAC SR (ExecSim) | -9.94 | -24.15 |

### Interpretation
The IC is now statistically significant (IC=0.0252, p=0.0004, n≈19,940
non-zero signal bars) - a real, measurable directional relationship exists
between sig_raw and 60-bar forward returns. This does NOT reverse the "no
alpha" conclusion: with a sample this large, even a very small effect can
reach significance, and the effect size here remains economically tiny.
White RC, SPA, PBO, and HAC Sharpe all remain firmly in "no tradeable edge"
territory, and in fact worsened slightly post-fix. The 1-bar holding period /
transaction-cost structure documented earlier in this audit appears to fully
consume this small statistical edge.

**Revised conclusion:** Data-processing defects materially affected earlier
diagnostics and have now been corrected. After re-evaluation on corrected
data, the signal exhibits a statistically detectable relationship with future
returns (IC≈0.025), but the effect remains economically insignificant and
fails robustness tests (White RC, SPA, PBO, HAC Sharpe). The strategy
therefore remains unsuitable for production deployment in its current form.
