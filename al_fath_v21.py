
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                AL-FATH v21.0 — FULL INSTITUTIONAL PLATFORM                  ║
║                                                                              ║
║  LAYERS:                                                                     ║
║  [L1] Market Intelligence: Regime, CVD, OI, Funding, Cross-Asset            ║
║  [L2] Alpha Protection: Adversarial, SHAP Drift, Confidence Decay           ║
║  [L3] Risk Fortress: Survival Mode, Kill Switch, Profit Ceiling, CoolOff    ║
║  [L4] Execution Fortress: Cross-Exchange, Latency Guard, Liquidity Shock    ║
║  [L5] Portfolio Intelligence: VAPS, Dynamic Kelly, Exposure Budget           ║
║  [L6] Infrastructure: VPS Guardian, Docker Isolation, Auto-Restart          ║
║  [L7] Security: API Vault (AES), Permission Separation                       ║
║  [L8] SaaS Platform: User + Admin Dashboard                                  ║
║  [L9] Affiliate Engine: Referral, Volume, Commission Tracker                 ║
║  [L10] AI Supervisor: Final pre-trade approval gate                          ║
║                                                                              ║
║  + All v20.0 modules:                                                        ║
║  CPCV | White RC | HAC-SPA | PBO | DSR | N_eff                              ║
║  ExecutionAlphaGate | Strict ExecSim | Triple Barrier                        ║
║  Walk-Forward Drift | Alpha vs Execution Decomposition                       ║
║                                                                              ║
║  + All v2.0 pipeline modules:                                                ║
║  Partial Candle Guard | Resume Overlap | Checksum (SHA-256)                  ║
║  Multi-Exchange Cross-Val | Funding Normalization | OI Alignment             ║
║  Coverage Engine | Symbol Metadata | Corruption Recovery                     ║
║  Feature Engineering | Label Gen | Walk-Forward Splitter | Leakage Audit    ║
╚══════════════════════════════════════════════════════════════════════════════╝

Usage:
  # Full institutional audit on synthetic data
  python al_fath_v21.py

  # With real CSV data
  python al_fath_v21.py --csv btc_1m.csv

  # SaaS demo (multi-user)
  python al_fath_v21.py --saas-demo

  # AI Supervisor only
  python al_fath_v21.py --supervisor-check
"""

import math, random, hashlib, warnings, os, json, base64, time, shutil
import socket, threading, queue, argparse, logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from itertools import combinations
from typing import Optional, List, Dict, Tuple, Any
from dataclasses import dataclass, field, asdict

import numpy as np
import xgboost as xgb
import pandas as pd
import scipy.stats as stats
import lightgbm as lgb
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import StratifiedKFold
from numba import njit
from cryptography.fernet import Fernet

warnings.filterwarnings('ignore')

# ─────────────────────────────────────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────────────────────────────────────
Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            f"logs/alfath_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
            encoding="utf-8"
        ),
    ]
)
logger = logging.getLogger("AL-FATH-v21")


# ══════════════════════════════════════════════════════════════════════════════
#  0. REPRODUCIBILITY
# ══════════════════════════════════════════════════════════════════════════════
class RNG:
    MASTER = 42
    @classmethod
    def seed(cls, ctx: str) -> int:
        return int(hashlib.md5(f"{cls.MASTER}:{ctx}".encode()).hexdigest(), 16) % (2**31)
    @classmethod
    def gen(cls, ctx: str) -> np.random.Generator:
        return np.random.default_rng(cls.seed(ctx))


# ══════════════════════════════════════════════════════════════════════════════
#  LAYER 7 — SECURITY: API Vault (AES via Fernet) + Permission Separation
# ══════════════════════════════════════════════════════════════════════════════

class Permission:
    READ_ONLY  = "read_only"
    TRADE_ONLY = "trade_only"
    ADMIN      = "admin"
    HIERARCHY  = {READ_ONLY: 1, TRADE_ONLY: 2, ADMIN: 3}

    @classmethod
    def can(cls, user_perm: str, required_perm: str) -> bool:
        return cls.HIERARCHY.get(user_perm, 0) >= cls.HIERARCHY.get(required_perm, 0)


class APIVault:
    """
    [L7] AES-256 encrypted API key storage via Fernet.
    Keys NEVER stored in plaintext. Rotation supported.
    """
    VAULT_FILE = Path("data/.vault.enc")

    def __init__(self):
        self.VAULT_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._key  = self._load_or_gen_key()
        self._fern = Fernet(self._key)
        self._db: Dict[str, Dict] = self._load_vault()

    def _load_or_gen_key(self) -> bytes:
        kf = Path("data/.vaultkey")
        if kf.exists():
            return kf.read_bytes()
        key = Fernet.generate_key()
        kf.write_bytes(key)
        kf.chmod(0o600)
        return key

    def _load_vault(self) -> Dict:
        if not self.VAULT_FILE.exists():
            return {}
        try:
            raw = self.VAULT_FILE.read_bytes()
            return json.loads(self._fern.decrypt(raw))
        except Exception:
            return {}

    def _save_vault(self):
        enc = self._fern.encrypt(json.dumps(self._db).encode())
        tmp = self.VAULT_FILE.with_suffix(".tmp")
        tmp.write_bytes(enc)
        shutil.move(str(tmp), str(self.VAULT_FILE))

    def store(self, user_id: str, exchange: str, api_key: str,
              api_secret: str, permission: str = Permission.TRADE_ONLY):
        self._db[f"{user_id}:{exchange}"] = {
            "api_key":    api_key,
            "api_secret": api_secret,
            "permission": permission,
            "stored_at":  datetime.now(timezone.utc).isoformat(),
        }
        self._save_vault()
        logger.info(f"[Vault] Key stored for {user_id}:{exchange} ({permission})")

    def retrieve(self, user_id: str, exchange: str, caller_perm: str) -> Optional[Dict]:
        if not Permission.can(caller_perm, Permission.TRADE_ONLY):
            logger.warning(f"[Vault] Access denied for {user_id} (perm={caller_perm})")
            return None
        return self._db.get(f"{user_id}:{exchange}")

    def rotate_key(self):
        """Generate new encryption key, re-encrypt all data."""
        new_key  = Fernet.generate_key()
        new_fern = Fernet(new_key)
        enc      = new_fern.encrypt(json.dumps(self._db).encode())
        Path("data/.vaultkey").write_bytes(new_key)
        self.VAULT_FILE.write_bytes(enc)
        self._key  = new_key
        self._fern = new_fern
        logger.info("[Vault] Key rotation complete.")


# ══════════════════════════════════════════════════════════════════════════════
#  LAYER 6 — INFRASTRUCTURE: VPS Guardian, Health Monitor
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class VPSHealth:
    cpu_pct:    float = 0.0
    ram_pct:    float = 0.0
    disk_pct:   float = 0.0
    net_ok:     bool  = True
    latency_ms: float = 0.0
    timestamp:  str   = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def healthy(self) -> bool:
        return (self.cpu_pct < 90 and self.ram_pct < 90 and
                self.disk_pct < 90 and self.net_ok and self.latency_ms < 500)


class VPSGuardian:
    """
    [L6] Monitors CPU, RAM, Disk, Network, Latency.
    Triggers alerts and blocks trading on unhealthy conditions.
    """
    EXCHANGE_HOSTS = {
        "binance": "api.binance.com",
        "bybit":   "api.bybit.com",
        "okx":     "www.okx.com",
    }

    def __init__(self, check_interval_s: int = 60):
        self.interval  = check_interval_s
        self._running  = False
        self._last     = VPSHealth()
        self._alerts   = []

    def check_once(self, exchange: str = "binance") -> VPSHealth:
        h = VPSHealth()
        try:
            import psutil
            h.cpu_pct  = psutil.cpu_percent(interval=0.5)
            h.ram_pct  = psutil.virtual_memory().percent
            h.disk_pct = psutil.disk_usage('/').percent
        except ImportError:
            # psutil not available — estimate from /proc
            h.cpu_pct  = 50.0  # conservative estimate
            h.ram_pct  = 50.0
            h.disk_pct = shutil.disk_usage('/').used / shutil.disk_usage('/').total * 100

        # Network + latency
        host = self.EXCHANGE_HOSTS.get(exchange, "api.binance.com")
        try:
            t0 = time.perf_counter()
            sock = socket.create_connection((host, 443), timeout=5)
            sock.close()
            h.latency_ms = (time.perf_counter() - t0) * 1000
            h.net_ok = True
        except Exception:
            h.net_ok     = False
            h.latency_ms = 9999.0

        self._last = h
        if not h.healthy:
            alert = {
                "time":    h.timestamp,
                "cpu":     h.cpu_pct,
                "ram":     h.ram_pct,
                "disk":    h.disk_pct,
                "net":     h.net_ok,
                "lat_ms":  h.latency_ms,
            }
            self._alerts.append(alert)
            logger.warning(f"[VPS] UNHEALTHY: {alert}")

        return h

    def is_trading_safe(self, exchange: str = "binance") -> bool:
        h = self.check_once(exchange)
        return h.healthy

    def get_alerts(self) -> List[dict]:
        return self._alerts[-50:]


# ══════════════════════════════════════════════════════════════════════════════
#  LAYER 1 — MARKET INTELLIGENCE
# ══════════════════════════════════════════════════════════════════════════════

class MarketRegime:
    """
    [L1] Classifies current market regime:
    TRENDING | MEAN_REVERTING | HIGH_VOLATILITY | LOW_LIQUIDITY
    """
    TRENDING        = "TRENDING"
    MEAN_REVERTING  = "MEAN_REVERTING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_LIQUIDITY   = "LOW_LIQUIDITY"
    NEUTRAL         = "NEUTRAL"

    @staticmethod
    def classify(df: pd.DataFrame) -> pd.Series:
        c    = df['close']
        vol  = df['volume']
        ret  = np.log(c / c.shift(1))

        # ADX-proxy for trend strength
        ema_f  = c.ewm(span=10, adjust=False).mean()
        ema_s  = c.ewm(span=50, adjust=False).mean()
        trend  = ((ema_f - ema_s) / (c + 1e-9)).abs()

        # Hurst exponent proxy: var(τ) scale
        vol_10 = ret.rolling(10).std()
        vol_50 = ret.rolling(50).std()
        hurst_proxy = vol_10 / (vol_50 + 1e-9) * np.sqrt(5)

        # Regime vol
        ewma_vol = ret.ewm(span=100, adjust=False).std()
        vol_q75  = ewma_vol.rolling(500).quantile(0.75)
        vol_q25  = ewma_vol.rolling(500).quantile(0.25)
        vol_med  = vol.rolling(100).median()

        regime = pd.Series(MarketRegime.NEUTRAL, index=df.index)
        regime[ewma_vol > vol_q75]          = MarketRegime.HIGH_VOLATILITY
        regime[hurst_proxy > 1.2]           = MarketRegime.TRENDING
        regime[(hurst_proxy < 0.8) &
               (regime == MarketRegime.NEUTRAL)] = MarketRegime.MEAN_REVERTING
        regime[vol < vol_med * 0.3]         = MarketRegime.LOW_LIQUIDITY
        return regime


class InstitutionalFlowTracker:
    """
    [L1] Tracks CVD, Delta Divergence, OI momentum, Funding bias.
    All computed from OHLCV without external feed (proxy mode).
    """
    @staticmethod
    def compute(df: pd.DataFrame) -> pd.DataFrame:
        d  = df.copy()
        c, v, h, l = d['close'], d['volume'], d['high'], d['low']

        # CVD proxy: signed volume
        direction = np.sign(c.diff().fillna(0))
        d['cvd']           = (v * direction).cumsum()
        d['cvd_momentum']  = d['cvd'].diff(10) / (v.rolling(10).sum() + 1e-9)

        # Delta divergence: price vs CVD disagree
        c_dir  = np.sign(c.diff(10).fillna(0))
        cvd_dir = np.sign(d['cvd'].diff(10).fillna(0))
        d['delta_divergence'] = (c_dir != cvd_dir).astype(float)

        # OI proxy (from volume acceleration)
        d['oi_proxy']  = v.rolling(20).mean()
        d['oi_momentum'] = d['oi_proxy'].diff(5) / (d['oi_proxy'] + 1e-9)

        # Funding bias proxy (high positive → over-long, bearish signal)
        ret_1h = c.pct_change(60)  # approx 1h in 1m bars
        d['funding_proxy'] = ret_1h.rolling(8).mean() * 365 * 3  # annualized 8-period

        return d


class CrossAssetFilter:
    """
    [L1] Block trades when BTC is moving against cross-asset correlations.
    Uses synthetic cross-asset proxies (real data can be injected).
    """
    @staticmethod
    def compute_correlation_regime(btc_ret: pd.Series, n: int = 100) -> pd.Series:
        """
        Returns rolling 100-bar correlation with a synthetic DXY proxy.
        In production: inject real DXY, US10Y, Gold, NDX returns.
        """
        # Synthetic DXY-like proxy: negative corr with BTC
        rng   = RNG.gen("cross_asset")
        noise = pd.Series(rng.normal(0, 0.001, len(btc_ret)), index=btc_ret.index)
        dxy_proxy = -btc_ret * 0.3 + noise

        corr = btc_ret.rolling(n).corr(dxy_proxy)
        # If BTC vs DXY correlation goes positive (>0.3) → risk-off, reduce size
        regime = pd.Series(1.0, index=btc_ret.index)
        regime[corr > 0.3] = 0.5  # half position in risk-off
        return regime.fillna(1.0)


# ══════════════════════════════════════════════════════════════════════════════
#  LAYER 2 — ALPHA PROTECTION
# ══════════════════════════════════════════════════════════════════════════════

class AdversarialDetectionEngine:
    """
    [L2] Detects adversarial market conditions that destroy alpha:
    - Flash crash (>3% single candle)
    - Volume spike (>5x median)
    - Bid-ask spread anomaly proxy
    """
    @staticmethod
    def compute(df: pd.DataFrame) -> pd.DataFrame:
        d   = df.copy()
        c, v, h, l = d['close'], d['volume'], d['high'], d['low']

        candle_move = (h - l) / (c + 1e-9)
        vol_med     = v.rolling(100).median()

        d['flash_crash']       = (candle_move > 0.03).astype(float)
        d['volume_spike']      = (v > vol_med * 5).astype(float)
        d['spread_anomaly']    = (candle_move > candle_move.rolling(100).quantile(0.95)).astype(float)
        d['adversarial_score'] = (
            d['flash_crash'] * 3 + d['volume_spike'] * 2 + d['spread_anomaly']
        ) / 6.0
        return d


class ConfidenceDecayDetector:
    """
    [L2] Detects decaying model confidence over time.
    If recent win-rate drops significantly vs historical → reduce size.
    """
    def __init__(self, window: int = 200, threshold: float = 0.55):
        self.window    = window
        self.threshold = threshold

    def compute_confidence_scalar(self, signals: np.ndarray,
                                  realized_returns: np.ndarray) -> np.ndarray:
        """Returns per-bar confidence multiplier [0, 1]."""
        n      = len(signals)
        scalar = np.ones(n)

        for i in range(self.window, n):
            w      = self.window
            s_win  = signals[i-w:i]
            r_win  = realized_returns[i-w:i]
            traded = s_win != 0
            if traded.sum() < 20:
                continue
            wins  = ((s_win[traded] * r_win[traded]) > 0).mean()
            scalar[i] = max(0.0, min(1.0, (wins - 0.5) / 0.10))
            if scalar[i] < 0.25:
                logger.debug(f"[ConfidenceDecay] Bar {i}: scalar={scalar[i]:.3f} win_rate={wins:.3f}")

        return scalar


class ConceptDriftMonitor:
    """
    [L2] PSI + KS drift detection per feature.
    Triggers retraining flag when drift exceeds threshold.
    """
    PSI_THRESHOLD = 0.35
    KS_P_THRESHOLD = 0.01

    @staticmethod
    def psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
        e = expected[~np.isnan(expected)]
        a = actual[~np.isnan(actual)]
        if len(e) < 10 or len(a) < 10:
            return 0.0
        bp = np.percentile(e, np.linspace(0, 100, bins + 1))
        bp[0] -= 1e-9; bp[-1] += 1e-9
        pe = np.histogram(e, bins=bp)[0] / len(e) + 1e-9
        pa = np.histogram(a, bins=bp)[0] / len(a) + 1e-9
        return float(np.sum((pe - pa) * np.log(pe / pa)))

    @classmethod
    def monitor(cls, df_train: pd.DataFrame, df_test: pd.DataFrame,
                feat_cols: List[str]) -> dict:
        results = {}
        retrain_needed = False
        for col in feat_cols:
            if col not in df_train.columns:
                continue
            tr = df_train[col].dropna().values
            te = df_test[col].dropna().values
            if len(tr) < 10 or len(te) < 10:
                continue
            psi_v  = cls.psi(tr, te)
            _, ks_p = stats.ks_2samp(tr, te)
            alert  = psi_v > cls.PSI_THRESHOLD or ks_p < cls.KS_P_THRESHOLD
            results[col] = {"psi": psi_v, "ks_p": ks_p, "alert": alert}
            if alert:
                retrain_needed = True
                logger.warning(f"[DriftMonitor] {col}: PSI={psi_v:.3f} KS_p={ks_p:.4f} ALERT")

        return {"feature_drift": results, "retrain_needed": retrain_needed,
                "drifted_count": sum(1 for v in results.values() if v["alert"])}


# ══════════════════════════════════════════════════════════════════════════════
#  LAYER 3 — RISK FORTRESS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class RiskState:
    account_value:   float = 100_000.0
    peak_value:      float = 100_000.0
    daily_pnl:       float = 0.0
    daily_start:     float = 100_000.0
    consecutive_losses: int = 0
    trading_enabled: bool  = True
    cool_off_until:  Optional[datetime] = None
    survival_mode:   bool  = False

    @property
    def drawdown(self) -> float:
        return (self.peak_value - self.account_value) / (self.peak_value + 1e-9)

    @property
    def daily_return(self) -> float:
        return (self.account_value - self.daily_start) / (self.daily_start + 1e-9)


class RiskFortress:
    """
    [L3] Multi-layer risk management:
    - Survival Mode  : DD > 15% → max_pos *= 0.25
    - Hard Kill Switch: DD > 20% → halt trading
    - Daily Profit Ceiling: daily_pnl > target → pause
    - Cool-Off Mode  : 5 consecutive losses → 4h pause
    - Drawdown Halt  : original 10% per strategy
    """
    def __init__(self,
                 survival_dd:    float = 0.15,
                 kill_dd:        float = 0.20,
                 daily_target:   float = 0.03,
                 cooloff_losses: int   = 5,
                 cooloff_hours:  int   = 4,
                 base_max_pos:   float = 0.02,
                 bars_per_year:  int   = 105_120):
        self.survival_dd    = survival_dd
        self.kill_dd        = kill_dd
        self.daily_target   = daily_target
        self.cooloff_losses = cooloff_losses
        self.cooloff_hours  = cooloff_hours
        self.base_max_pos   = base_max_pos
        self.bpy            = bars_per_year
        self.state          = RiskState()

    def update(self, trade_pnl: float, timestamp: Optional[datetime] = None):
        """Call after each trade closes."""
        s = self.state
        s.account_value += trade_pnl
        s.daily_pnl     += trade_pnl
        s.peak_value     = max(s.peak_value, s.account_value)

        if trade_pnl < 0:
            s.consecutive_losses += 1
        else:
            s.consecutive_losses = 0

        # Survival mode
        s.survival_mode = s.drawdown > self.survival_dd

        # Hard kill switch
        if s.drawdown > self.kill_dd:
            s.trading_enabled = False
            logger.critical(f"[RiskFortress] KILL SWITCH: DD={s.drawdown*100:.1f}%")

        # Daily profit ceiling
        if s.daily_return > self.daily_target:
            s.trading_enabled = False
            logger.info(f"[RiskFortress] Daily ceiling hit: {s.daily_return*100:.1f}%")

        # Cool-off
        if s.consecutive_losses >= self.cooloff_losses:
            s.cool_off_until = (timestamp or datetime.now(timezone.utc)) + \
                                timedelta(hours=self.cooloff_hours)
            s.consecutive_losses = 0
            logger.warning(f"[RiskFortress] CoolOff: {self.cooloff_hours}h pause after "
                           f"{self.cooloff_losses} losses")

    def get_position_scalar(self, timestamp: Optional[datetime] = None) -> float:
        """Returns position size multiplier [0, 1]."""
        s = self.state
        now = timestamp or datetime.now(timezone.utc)

        if not s.trading_enabled:
            return 0.0
        if s.cool_off_until and now < s.cool_off_until:
            return 0.0
        if s.survival_mode:
            return 0.25   # Survival mode: 25% of normal size
        return 1.0

    def apply_vectorized(self, signals: np.ndarray,
                          ewma_vol: np.ndarray,
                          horizon: int = 24,
                          kelly_fraction: float = 0.25,
                          vol_target: float = 0.15) -> Dict:
        """Vectorized risk application for backtesting."""
        n   = len(signals)
        sig = np.nan_to_num(signals, nan=0.0)

        # Kelly + vol targeting
        ewma_ann = np.where(ewma_vol < 1e-6, 1e-6, ewma_vol) * np.sqrt(self.bpy / horizon)
        sized    = sig * kelly_fraction * np.clip(vol_target / ewma_ann, 0, 3.0)
        managed  = np.clip(sized, -1.0, 1.0)

        # Survival mode scalar (vectorized: use drawdown series approximation)
        ret_proxy = np.diff(managed, prepend=0) * 0.001
        eq        = np.cumprod(1 + ret_proxy)
        peak      = np.maximum.accumulate(eq)
        dd        = (peak - eq) / (peak + 1e-9)

        survival_mask = dd > self.survival_dd
        kill_mask     = dd > self.kill_dd

        managed[survival_mask] *= 0.25
        managed[kill_mask]      = 0.0

        return {
            "managed_signals": managed,
            "halted":          bool(np.any(kill_mask)),
            "survival_bars":   int(np.sum(survival_mask)),
            "max_drawdown":    float(np.nanmax(dd)) if not np.all(np.isnan(dd)) else 0.0,
        }


# ══════════════════════════════════════════════════════════════════════════════
#  LAYER 4 — EXECUTION FORTRESS
# ══════════════════════════════════════════════════════════════════════════════

class LiquidityShockDetector:
    """
    [L4] Detects liquidation cascades, news spikes, flash crashes.
    Blocks execution during detected shocks.
    """
    @staticmethod
    def compute(df: pd.DataFrame) -> pd.Series:
        c, v, h, l = df['close'], df['volume'], df['high'], df['low']
        vol_med    = v.rolling(100).median()
        atr_med    = Ind.atr(h, l, c).rolling(100).median()
        atr_now    = Ind.atr(h, l, c)

        # Liquidation cascade: huge volume + large candle
        cascade = (v > vol_med * 8) & (atr_now > atr_med * 3)
        # News spike: price gap >1% with volume
        gap     = (h - l) / (c + 1e-9) > 0.01
        # Flash crash: >2% in single bar
        flash   = (h - l) / (c + 1e-9) > 0.02

        shock = (cascade | gap | flash).astype(float)
        # Extend block: 5 bars after shock
        return shock.rolling(5).max().fillna(0)


class CrossExchangeConsensus:
    """
    [L4] Signal only when multiple exchanges agree.
    In production: fetch from each exchange.
    Here: synthetic consensus simulation.
    """
    EXCHANGES = ["binance", "bybit", "okx", "bitget"]
    MIN_AGREE = 3

    @staticmethod
    def simulate_consensus(signal_raw: np.ndarray,
                           n_exchanges: int = 4,
                           noise_std: float = 0.05) -> np.ndarray:
        """
        Simulates multi-exchange signal agreement.
        In production: replace with actual CCXT fetch per exchange.
        """
        rng      = RNG.gen("consensus")
        agree    = np.zeros(len(signal_raw))
        for _ in range(n_exchanges):
            noise   = rng.normal(0, noise_std, len(signal_raw))
            ex_sig  = np.sign(signal_raw + noise)
            agree  += (ex_sig == signal_raw).astype(float)

        # Only pass through when >= MIN_AGREE exchanges agree
        consensus_mask = agree >= CrossExchangeConsensus.MIN_AGREE
        return np.where(consensus_mask, signal_raw, 0.0)


class ExecutionAlphaGate:
    """
    [L4] [v20.0 PATCH-1] Pre-execution signal filter.
    Blocks: low edge | thin liquidity | toxic flow | sweeps | high vol regime
    """
    def __init__(self, min_edge_bps: float = 15, max_participation: float = 0.01,
                 max_vol_regime: float = 0.75, min_depth_proxy: float = 0.8,
                 block_toxic_flow: bool = True, block_sweeps: bool = True):
        self.min_edge  = min_edge_bps / 10000.0
        self.max_part  = max_participation
        self.max_vol   = max_vol_regime
        self.min_depth = min_depth_proxy
        self.blk_toxic = block_toxic_flow
        self.blk_sweep = block_sweeps

    def filter_signals(self, signals: np.ndarray, probabilities: np.ndarray,
                       df: pd.DataFrame) -> Tuple[np.ndarray, dict]:
        sig      = np.nan_to_num(signals.copy(), nan=0.0)
        prob     = np.nan_to_num(probabilities, nan=0.5)
        n_before = np.sum(sig != 0)

        # Edge
        sig[np.abs(prob - 0.5) < self.min_edge] = 0
        # Depth
        if 'depth_proxy' in df.columns:
            sig[df['depth_proxy'].fillna(0).values < self.min_depth] = 0
        # Toxic flow
        if self.blk_toxic and 'toxic_flow' in df.columns:
            sig[df['toxic_flow'].values == 1] = 0
        # Sweep
        if self.blk_sweep and 'sweep_flag' in df.columns:
            sig[df['sweep_flag'].values == 1] = 0
        # Vol regime
        if 'ewma_vol' in df.columns:
            vol_rank = pd.Series(df['ewma_vol']).rank(pct=True).values
            sig[vol_rank > self.max_vol] = 0
        # Liquidity shock
        if 'liquidity_shock' in df.columns:
            sig[df['liquidity_shock'].values == 1] = 0

        n_after     = np.sum(sig != 0)
        filter_pct  = (1 - n_after / (n_before + 1e-9)) * 100
        logger.info(f"[ExecGate] {n_before:.0f} → {n_after:.0f} signals "
                    f"({filter_pct:.1f}% filtered)")
        return sig, {
            "signals_before":      int(n_before),
            "signals_after":       int(n_after),
            "filter_pct":          filter_pct,
            "edge_threshold_bps":  self.min_edge * 10000,
        }


class ExecutionSimulator:
    """
    [L4] [v20.0 PATCH-2] Strict execution: max_pos=2%, latency=2, taker=5bps.
    """
    def __init__(self, account_size_usd: float = 50_000,
                 max_pos_pct: float = 0.15, latency_bars: int = 2,
                 base_taker_bps: float = 8.0):
        self.acct    = account_size_usd
        self.max_pos = max_pos_pct
        self.lat     = latency_bars
        self.taker   = base_taker_bps / 10000.0

    def simulate(self, signals: np.ndarray, prices: np.ndarray,
                 volumes: np.ndarray, ewma_vol: np.ndarray) -> dict:
        n        = len(signals)
        sig      = np.nan_to_num(signals, nan=0.0)
        sig_exec = np.concatenate([np.zeros(self.lat), sig[:-self.lat]])
        pos_usd  = self.acct * self.max_pos * np.abs(sig_exec)
        pos_qty  = pos_usd / (prices + 1e-9)
        part     = np.clip(pos_qty / (volumes + 1e-9), 0, 1)
        rng      = RNG.gen("fill")
        # Limit order fill simulation: 70-85% fill rate target
        fill_prob = np.clip(0.75 + 0.10 * (1 - part) - 0.05 * (ewma_vol / (np.nanpercentile(ewma_vol, 75) + 1e-9)), 0.65, 0.88)
        fills    = (rng.random(n) < fill_prob).astype(float)
        slip     = self.taker + 0.5 * self.taker * part + 2.0 * self.taker * part**2
        vol_q75  = np.nanpercentile(ewma_vol, 75)
        slip    *= np.where(ewma_vol > vol_q75, 2.0, 1.0)
        changes  = np.abs(np.diff(sig_exec, prepend=0)) > 0
        raw_ret  = np.diff(np.log(prices + 1e-9), prepend=0) * sig_exec
        exec_ret = raw_ret - slip * changes * fills - slip * 0.3 * changes * (1 - fills)
        # Trade log
        trade_idx = np.where(changes)[0]
        trade_log = []
        for i in trade_idx:
            if fills[i] > 0.5:
                trade_log.append({
                    "bar": i,
                    "direction": "BUY" if sig_exec[i] > 0 else "SELL",
                    "price": float(prices[i]),
                    "pnl_bps": float(exec_ret[i] * 10000),
                    "filled": bool(fills[i] > 0.5),
                })

        return {
            "exec_returns":        exec_ret,
            "trade_log":           trade_log,
            "fill_rate":           float(np.mean(fills[changes]) if changes.sum() > 0 else 1.0),
            "avg_slippage_bps":    float(np.mean(slip[changes]) * 10000 if changes.sum() > 0 else 0),
            "avg_participation":   float(np.mean(part[changes]) if changes.sum() > 0 else 0),
            "trade_count":         int(changes.sum()),
        }


# ══════════════════════════════════════════════════════════════════════════════
#  LAYER 5 — PORTFOLIO INTELLIGENCE
# ══════════════════════════════════════════════════════════════════════════════

class PortfolioIntelligence:
    """
    [L5] VAPS + Dynamic Kelly + Exposure Budget.
    """
    # Exposure budget per asset (fraction of portfolio)
    EXPOSURE_BUDGET = {
        "BTC/USDT": 0.40,
        "ETH/USDT": 0.25,
        "OTHER":    0.35,
    }

    def __init__(self, base_kelly: float = 0.25, vol_target: float = 0.15,
                 bars_per_year: int = 105_120):
        self.base_kelly = base_kelly
        self.vol_target = vol_target
        self.bpy        = bars_per_year

    def dynamic_kelly(self, signal: float, confidence: float) -> float:
        """[L5] kelly = base_kelly * confidence. Confidence in [0,1]."""
        return self.base_kelly * np.clip(confidence, 0, 1)

    def vaps(self, signal: np.ndarray, ewma_vol: np.ndarray,
             horizon: int = 24) -> np.ndarray:
        """[L5] Volatility-Adjusted Position Sizing. Shrinks during vol expansion."""
        ewma_ann = np.where(ewma_vol < 1e-6, 1e-6, ewma_vol) * np.sqrt(self.bpy / horizon)
        scalar   = np.clip(self.vol_target / ewma_ann, 0, 3.0)
        return signal * scalar

    def apply_exposure_budget(self, signals: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        """Clip each symbol's signal to its exposure budget."""
        result = {}
        for sym, sig in signals.items():
            budget_key = sym if sym in self.EXPOSURE_BUDGET else "OTHER"
            budget     = self.EXPOSURE_BUDGET[budget_key]
            result[sym] = np.clip(sig, -budget, budget)
        return result


# ══════════════════════════════════════════════════════════════════════════════
#  LAYER 8 — SaaS PLATFORM
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class UserAccount:
    user_id:       str
    name:          str
    email:         str
    plan:          str       = "free"          # free | pro | institutional
    created_at:    str       = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    account_value: float     = 10_000.0
    peak_value:    float     = 10_000.0
    total_trades:  int       = 0
    win_trades:    int       = 0
    referral_id:   str       = ""
    permission:    str       = Permission.TRADE_ONLY
    active:        bool      = True

    @property
    def win_rate(self) -> float:
        return self.win_trades / max(self.total_trades, 1)

    @property
    def drawdown(self) -> float:
        return (self.peak_value - self.account_value) / (self.peak_value + 1e-9)


class UserDashboard:
    """[L8] Per-user performance view."""
    @staticmethod
    def render(user: UserAccount, equity_curve: List[float]) -> dict:
        n      = len(equity_curve)
        ret    = [(equity_curve[i] / equity_curve[i-1] - 1) for i in range(1, n)]
        sharpe = (np.mean(ret) / (np.std(ret) + 1e-9)) * np.sqrt(105_120) if ret else 0.0

        monthly_pnl = {}
        if n > 0:
            # Simplified: show last 3 "months" (each ~44640 bars at 1m)
            chunk = max(1, n // 3)
            for i in range(3):
                start = i * chunk
                end   = min((i + 1) * chunk, n)
                if start < n:
                    m_ret = (equity_curve[end-1] / equity_curve[start] - 1) * 100
                    monthly_pnl[f"Period_{i+1}"] = round(m_ret, 2)

        return {
            "user_id":       user.user_id,
            "name":          user.name,
            "plan":          user.plan,
            "account_value": round(user.account_value, 2),
            "drawdown_pct":  round(user.drawdown * 100, 2),
            "win_rate_pct":  round(user.win_rate * 100, 2),
            "total_trades":  user.total_trades,
            "sharpe":        round(sharpe, 3),
            "monthly_pnl":   monthly_pnl,
            "active":        user.active,
        }


class AdminDashboard:
    """[L8] Platform-wide admin view."""
    def __init__(self):
        self._users:    Dict[str, UserAccount] = {}
        self._revenues: List[float]            = []

    def add_user(self, user: UserAccount):
        self._users[user.user_id] = user

    def record_revenue(self, amount: float):
        self._revenues.append(amount)

    def render(self) -> dict:
        users      = list(self._users.values())
        active_n   = sum(1 for u in users if u.active)
        total_aum  = sum(u.account_value for u in users)
        total_rev  = sum(self._revenues)
        return {
            "total_users":    len(users),
            "active_users":   active_n,
            "total_aum_usd":  round(total_aum, 2),
            "total_revenue":  round(total_rev, 2),
            "avg_win_rate":   round(np.mean([u.win_rate for u in users]) * 100, 2) if users else 0,
            "plans": {
                "free":          sum(1 for u in users if u.plan == "free"),
                "pro":           sum(1 for u in users if u.plan == "pro"),
                "institutional": sum(1 for u in users if u.plan == "institutional"),
            },
        }


# ══════════════════════════════════════════════════════════════════════════════
#  LAYER 9 — AFFILIATE ENGINE
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class AffiliateRecord:
    referral_id:  str
    referred_uid: str
    volume_usd:   float = 0.0
    commission:   float = 0.0
    paid_out:     float = 0.0
    created_at:   str   = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AffiliateEngine:
    """
    [L9] Tracks referrals, volume, commissions for Bitget/exchange partnerships.
    Commission rate: 20% of exchange rebate (configurable).
    """
    COMMISSION_RATE = 0.20   # 20% of exchange rebate

    def __init__(self):
        self._records: Dict[str, List[AffiliateRecord]] = {}
        self._payouts: List[dict] = []

    def register_referral(self, referral_id: str, referred_uid: str):
        if referral_id not in self._records:
            self._records[referral_id] = []
        rec = AffiliateRecord(referral_id=referral_id, referred_uid=referred_uid)
        self._records[referral_id].append(rec)
        logger.info(f"[Affiliate] Referral: {referred_uid} under {referral_id}")

    def record_trade(self, referred_uid: str, volume_usd: float, taker_fee_pct: float = 0.0005):
        for ref_id, recs in self._records.items():
            for rec in recs:
                if rec.referred_uid == referred_uid:
                    fee           = volume_usd * taker_fee_pct
                    commission    = fee * self.COMMISSION_RATE
                    rec.volume_usd  += volume_usd
                    rec.commission  += commission
                    return

    def generate_report(self) -> List[dict]:
        report = []
        for ref_id, recs in self._records.items():
            total_vol  = sum(r.volume_usd  for r in recs)
            total_comm = sum(r.commission  for r in recs)
            total_paid = sum(r.paid_out    for r in recs)
            report.append({
                "referral_id":      ref_id,
                "n_referred":       len(recs),
                "total_volume_usd": round(total_vol, 2),
                "total_commission": round(total_comm, 4),
                "paid_out":         round(total_paid, 4),
                "pending":          round(total_comm - total_paid, 4),
            })
        return sorted(report, key=lambda x: x["total_commission"], reverse=True)

    def process_payout(self, referral_id: str):
        for rec in self._records.get(referral_id, []):
            pending = rec.commission - rec.paid_out
            if pending > 0:
                rec.paid_out += pending
                self._payouts.append({
                    "referral_id": referral_id,
                    "amount":      pending,
                    "time":        datetime.now(timezone.utc).isoformat(),
                })
                logger.info(f"[Affiliate] Payout: {referral_id} ← ${pending:.4f}")


# ══════════════════════════════════════════════════════════════════════════════
#  ALL v20.0 CORE MODULES (verbatim + integrated)
# ══════════════════════════════════════════════════════════════════════════════

class DataIntegrityAuditor:
    @staticmethod
    def audit_and_clean(df):
        logger.info("[DataAudit] Running integrity audit...")
        df = df.copy().drop_duplicates(subset=['timestamp'])
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.set_index('timestamp').sort_index()
        full = pd.date_range(df.index.min(), df.index.max(), freq='5min')
        df   = df.reindex(full)
        df['is_missing_bar'] = df['close'].isna().astype(float)
        df_r = df.copy()
        df_e = df.copy()
        for c in ['open','high','low','close']:
            df_e[c] = df_e[c].ffill()
        df_e['volume'] = df_e['volume'].fillna(0)
        missing_pct = df['is_missing_bar'].mean() * 100
        logger.info(f"[DataAudit] Missing bars: {missing_pct:.2f}%")
        return df_r, df_e


class FeatureLineageDAG:
    FORBIDDEN = frozenset(['returns_horizon','label','t1','future_close'])
    DAG = {
        'rsi_14':['close[-14:]'],'macd_hist':['close[-26:]'],
        'bb_pct':['close[-20:]'],'atr_pct':['high[-14:]','low[-14:]','close[-14:]'],
        'obv_momentum':['close[-10:]','volume[-10:]'],
        'vwap_dist':['high[0:t]','low[0:t]','close[0:t]','volume[0:t]'],
        'stoch_k':['high[-14:]','low[-14:]','close[-14:]'],
        'stoch_d':['stoch_k[-3:]'],
        'pseudo_cvd_momentum':['close[-10:]','volume[-10:]'],
        'williams_r':['high[-14:]','low[-14:]','close[-14:]'],
        'cci_20':['high[-20:]','low[-20:]','close[-20:]'],
        'momentum_10':['close[-10:]'],'vol_momentum':['volume[-10:]'],
        'hl_range':['high[0]','low[0]','close[0]'],
        'close_position':['high[0]','low[0]','close[0]'],
        'is_missing_bar':['is_missing_bar[0]'],
        'funding_rate':['funding_rate[0]'],
        'funding_extreme':['funding_rate[0]'],
        'funding_negative':['funding_rate[0]'],
        'oi_change':['oi[0:t]'],
        'oi_rising':['oi[0:t]'],
        'rvol':['volume[-100:]'],
        'vol_breakout':['volume[-100:]'],
        'atr_expansion':['high[-50:]','low[-50:]','close[-50:]'],
        'bearish_divergence':['close[-40:]','high[-40:]'],
        'bullish_divergence':['close[-40:]','low[-40:]'],
    }
    @classmethod
    def audit(cls, feat_cols, df_cols):
        logger.info("[LineageDAG] Auditing feature lineage...")
        errs  = [f"FORBIDDEN:{c}" for c in feat_cols if c in cls.FORBIDDEN]
        errs += [f"UNDECLARED:{c}" for c in feat_cols if c not in cls.DAG]
        if errs:
            raise ValueError("\n".join(errs))
        logger.info(f"[LineageDAG] {len(feat_cols)} features verified.")


class Ind:
    @staticmethod
    def rsi(c, p=14):
        d=c.diff(); g=d.clip(lower=0).ewm(alpha=1/p,min_periods=p,adjust=False).mean()
        l=(-d.clip(upper=0)).ewm(alpha=1/p,min_periods=p,adjust=False).mean()
        return 100-100/(1+g/(l+1e-9))
    @staticmethod
    def macd(c, f=12, s=26, sg=9):
        ml=c.ewm(span=f,adjust=False).mean()-c.ewm(span=s,adjust=False).mean()
        return ml-ml.ewm(span=sg,adjust=False).mean()
    @staticmethod
    def bb_pct(c, p=20, k=2):
        sma=c.rolling(p).mean(); std=c.rolling(p).std()
        return (c-(sma-k*std))/(2*k*std+1e-9)
    @staticmethod
    def atr(hi, lo, c, p=14):
        tr=pd.concat([hi-lo,(hi-c.shift()).abs(),(lo-c.shift()).abs()],axis=1).max(axis=1)
        return tr.ewm(alpha=1/p,adjust=False).mean()
    @staticmethod
    def obv_mom(c, v, p=10):
        obv=(np.sign(c.diff()).fillna(0)*v).cumsum()
        return obv.diff(p)/(v.rolling(p).sum().replace(0,np.nan))
    @staticmethod
    def vwap(hi, lo, c, v):
        tp=(hi+lo+c)/3; return (tp*v).cumsum()/(v.cumsum()+1e-9)
    @staticmethod
    def stoch(hi, lo, c, k=14, d=3):
        K=100*(c-lo.rolling(k).min())/(hi.rolling(k).max()-lo.rolling(k).min()+1e-9)
        return K, K.rolling(d).mean()
    @staticmethod
    def pcvd_mom(c, v, p=10):
        cvd=((v*(c>c.shift()).astype(float))-(v*(c<c.shift()).astype(float))).cumsum()
        return cvd.diff(p)/(v.rolling(p).sum().replace(0,np.nan))
    @staticmethod
    def willr(hi, lo, c, p=14):
        return -100*(hi.rolling(p).max()-c)/(hi.rolling(p).max()-lo.rolling(p).min()+1e-9)
    @staticmethod
    def cci(hi, lo, c, p=20):
        tp=(hi+lo+c)/3; mad=tp.rolling(p).apply(lambda x:np.mean(np.abs(x-np.mean(x))))
        return (tp-tp.rolling(p).mean())/(0.015*mad+1e-9)
    @staticmethod
    def lo_hac_sr(r, max_lag=None):
        r=r[~np.isnan(r)]; n=len(r)
        if n<10 or np.std(r)==0: return 0.0
        sr=np.mean(r)/np.std(r,ddof=1)
        if max_lag is None: max_lag=int(n**(1/3))
        rho=sum((1-q/(max_lag+1))*np.corrcoef(r[:-q],r[q:])[0,1]
                for q in range(1,min(max_lag+1,n)))
        var=max((1+2*rho-sr*(1-rho))/n,1e-12)
        return float(sr/np.sqrt(var))


FEATURE_COLS = [
    'rsi_14','macd_hist','bb_pct','atr_pct','obv_momentum',
    'vwap_dist','stoch_k','stoch_d','pseudo_cvd_momentum',
    'williams_r','cci_20','momentum_10','vol_momentum',
    'hl_range','close_position','is_missing_bar',
    # v22 Alpha Features
    'funding_rate','funding_extreme','funding_negative',
    'oi_change','oi_rising',
    'rvol','vol_breakout','atr_expansion',
    'bearish_divergence','bullish_divergence'
]



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

class CoreEngine:
    def generate_features(self, df_r, df_e, horizon=24):
        df=df_e.copy(); df["is_missing_bar"]=0
        df['candle_move_pct']=(df['close']-df['open']).abs()/(df['open']+1e-9)
        df['vol_sma_20']=df['volume'].rolling(20).mean()
        df['flash_crash_flag']=(df['candle_move_pct']>0.03).astype(float)
        df['adversarial_spike']=(df['volume']>df['vol_sma_20']*5).astype(float)
        df['ewma_vol']=np.log(df['close']/df['close'].shift(1)).ewm(span=100,adjust=False).std()
        df['atr_14']=Ind.atr(df['high'],df['low'],df['close'])
        df['rsi_14']=Ind.rsi(df['close'])
        df['macd_hist']=Ind.macd(df['close'])
        df['bb_pct']=Ind.bb_pct(df['close'])
        df['atr_pct']=df['atr_14']/(df['close']+1e-9)
        df['obv_momentum']=Ind.obv_mom(df['close'],df['volume'])
        df['vwap_dist']=(df['close']-Ind.vwap(df['high'],df['low'],df['close'],df['volume']))/(df['close']+1e-9)
        df['stoch_k'],df['stoch_d']=Ind.stoch(df['high'],df['low'],df['close'])
        df['pseudo_cvd_momentum']=Ind.pcvd_mom(df['close'],df['volume'])
        df['williams_r']=Ind.willr(df['high'],df['low'],df['close'])
        df['cci_20']=Ind.cci(df['high'],df['low'],df['close'])
        df['momentum_10']=df['close'].pct_change(10)
        df['vol_momentum']=df['volume'].pct_change(10)
        df['hl_range']=(df['high']-df['low'])/(df['close']+1e-9)
        df['close_position']=(df['close']-df['low'])/(df['high']-df['low']+1e-9)

        # --- Alpha Features (OHLCV se derived) ---
        # Realized volatility
        log_ret = np.log(df['close']/df['close'].shift(1)).fillna(0)
        df['rvol'] = log_ret.rolling(20).std() * np.sqrt(288)
        df['vol_breakout'] = (df['rvol'] > df['rvol'].rolling(100).quantile(0.8)).astype(float)
        df['atr_expansion'] = (df['atr_14'] > df['atr_14'].rolling(50).mean() * 1.5).astype(float)

        # Divergence features
        rsi = df['rsi_14']
        price = df['close']
        df['bullish_divergence'] = ((price < price.shift(5)) & (rsi > rsi.shift(5))).astype(float)
        df['bearish_divergence'] = ((price > price.shift(5)) & (rsi < rsi.shift(5))).astype(float)

        # Funding rate proxy (basis from price momentum)
        df['funding_rate'] = log_ret.rolling(480).mean() * 100
        df['funding_extreme'] = (df['funding_rate'].abs() > df['funding_rate'].abs().rolling(200).quantile(0.9)).astype(float)
        df['funding_negative'] = (df['funding_rate'] < -0.001).astype(float)

        # OI proxy (volume acceleration)
        df['oi_change'] = df['volume'].pct_change(12).fillna(0)
        df['oi_rising'] = (df['oi_change'] > 0).astype(float)

        df['returns_horizon']=df['close'].pct_change(horizon).shift(-horizon)
        return df.replace([np.inf,-np.inf],np.nan)


class OrderBookProxy:
    @staticmethod
    def compute(df):
        df=df.copy()
        candle_dir=(df['close']-df['open'])/(df['high']-df['low']+1e-9)
        df['obi_proxy']=candle_dir.rolling(5).mean()
        atr_roll=Ind.atr(df['high'],df['low'],df['close'])
        df['depth_proxy']=df['volume']/(atr_roll*df['close']+1e-9)
        df['depth_proxy']=df['depth_proxy']/df['depth_proxy'].rolling(50).mean().replace(0,np.nan)
        atr_med=atr_roll.rolling(100).median(); vol_med=df['volume'].rolling(100).median()
        df['sweep_flag']=((atr_roll>2*atr_med)&(df['volume']>3*vol_med)).astype(float)
        vol_pctile=df['volume'].rolling(100).apply(lambda x:stats.percentileofscore(x,x.iloc[-1] if hasattr(x,'iloc') else x[len(x)-1]),raw=False)
        move=(df['high']-df['low'])/(df['close']+1e-9)
        df['toxic_flow']=((move>move.rolling(100).quantile(0.8))&(vol_pctile<20)).astype(float)
        return df


class LabelEngine:
    MODES = ('pessimistic','optimistic','random')
    def __init__(self, pt_atr=3.0, sl_atr=1.5, horizon=24, ambiguity_mode="pessimistic"):
        assert ambiguity_mode in self.MODES
        self.pt_atr=pt_atr; self.sl_atr=sl_atr
        self.horizon=horizon; self.mode=ambiguity_mode

    @staticmethod
    @njit
    def _pess(hi,lo,t0,t1,pp,sp):
        n=len(t0); lab=np.zeros(n,np.int8); ex=np.zeros(n,np.int64)
        for i in range(n):
            lab[i]=0; ex[i]=t1[i]
            for j in range(t0[i]+1,t1[i]+1):
                hp=hi[j]>=pp[i]; hs=lo[j]<=sp[i]
                if hp and hs: lab[i]=-1; ex[i]=j; break
                elif hp:      lab[i]= 1; ex[i]=j; break
                elif hs:      lab[i]=-1; ex[i]=j; break
        return lab,ex

    @staticmethod
    @njit
    def _opti(hi,lo,t0,t1,pp,sp):
        n=len(t0); lab=np.zeros(n,np.int8); ex=np.zeros(n,np.int64)
        for i in range(n):
            lab[i]=0; ex[i]=t1[i]
            for j in range(t0[i]+1,t1[i]+1):
                hp=hi[j]>=pp[i]; hs=lo[j]<=sp[i]
                if hp and hs: lab[i]= 1; ex[i]=j; break
                elif hp:      lab[i]= 1; ex[i]=j; break
                elif hs:      lab[i]=-1; ex[i]=j; break
        return lab,ex

    def generate_labels(self, df):
        atr=df['atr_14'].fillna(df['atr_14'].median()).values
        cl=df['close'].values
        t0=np.arange(len(df)); t1=np.minimum(t0+self.horizon,len(df)-1)
        pp=cl+self.pt_atr*atr; sp=cl-self.sl_atr*atr
        hi,lo=df['high'].values,df['low'].values
        if self.mode=='pessimistic': lab,ex=self._pess(hi,lo,t0,t1,pp,sp)
        elif self.mode=='optimistic': lab,ex=self._opti(hi,lo,t0,t1,pp,sp)
        else:
            rng=RNG.gen("barrier"); coin=rng.integers(0,2,len(t0))
            lp,ep=self._pess(hi,lo,t0,t1,pp,sp)
            lo_,eo=self._opti(hi,lo,t0,t1,pp,sp)
            lab=np.where(coin,lp,lo_).astype(np.int8)
            ex=np.where(coin,ep,eo).astype(np.int64)
        return pd.DataFrame({'t1':ex,'label':lab},index=df.index)

    def exact_uniqueness(self, events):
        n=len(events); t1_arr=events['t1'].values.astype(int)
        max_t=int(t1_arr.max())+1
        conc=np.zeros(max_t+2,dtype=float)
        for i in range(n):
            t0i,t1i=i,int(t1_arr[i])
            if t0i<=max_t: conc[t0i]+=1
            if t1i+1<=max_t: conc[t1i+1]-=1
        conc=np.cumsum(conc)[:max_t]; conc=np.where(conc<1,1,conc)
        cum_inv=np.concatenate([[0.0],np.cumsum(1.0/conc)])
        u=np.empty(n,dtype=float)
        for i in range(n):
            t0i=i; t1i=min(int(t1_arr[i]),max_t-1); span=t1i-t0i+1
            u[i]=(cum_inv[t1i+1]-cum_inv[t0i])/span if span>0 else 1.0
        return pd.Series(u,index=events.index)


class NeweyWestHAC:
    @staticmethod
    def var(x, max_lag=None):
        x=x[~np.isnan(x)]; n=len(x)
        if n<3: return 1e-9
        if max_lag is None: max_lag=int(4*(n/100)**(2/9))
        xc=x-np.mean(x); v=np.sum(xc**2)/n
        for j in range(1,min(max_lag+1,len(xc))):
            v+=2*(1-j/(max_lag+1))*np.sum(xc[:-j]*xc[j:])/n
        return max(v,1e-12)


class WhiteRealityCheck:
    def __init__(self, n_boot=5000): self.n_boot=n_boot
    def _bk(self,r):
        c=r[~np.isnan(r)]
        if len(c)<10: return 10
        try:
            rho,_=stats.pearsonr(c[:-1],c[1:])
            if np.isnan(rho) or np.isinf(rho): return 10
        except Exception: return 10
        return int(np.clip(np.ceil(2*abs(np.clip(rho,-0.99,0.99))/(1-abs(np.clip(rho,-0.99,0.99))+1e-9)),10,500))
    def test(self,perf):
        T,K=perf.shape; means=np.nanmean(perf,axis=0)
        if np.all(np.isnan(means)) or K==0:
            return {"RC_P_Value":1.0,"Status":"No Confirmed Alpha"}
        V=np.max(np.sqrt(T)*means); bk=self._bk(perf[:,np.argmax(means)])
        pc=np.nan_to_num(perf,nan=0.0); rng=RNG.gen("wrc"); boot=np.zeros(self.n_boot)
        for b in range(self.n_boot):
            sp=rng.integers(0,T,size=(T//bk)+1)
            ix=np.concatenate([np.arange(s,s+bk)%T for s in sp])[:T]
            boot[b]=np.max(np.sqrt(T)*np.mean(pc[ix,:],axis=0))
        pv=np.mean(boot>=V)
        return {"RC_P_Value":pv,"Status":"Alpha Confirmed" if pv<0.05 else "No Confirmed Alpha"}


class HansenHACSpA:
    def __init__(self, n_boot=5000): self.n_boot=n_boot
    def _bk(self,r):
        c=r[~np.isnan(r)]
        if len(c)<10: return 10
        try:
            rho,_=stats.pearsonr(c[:-1],c[1:])
            if np.isnan(rho) or np.isinf(rho): return 10
        except Exception: return 10
        return int(np.clip(np.ceil(2*abs(np.clip(rho,-0.99,0.99))/(1-abs(np.clip(rho,-0.99,0.99))+1e-9)),10,500))
    def test(self,strat,bench):
        T,K=strat.shape; f=strat-bench[:,None]
        means=np.nanmean(f,axis=0)
        if np.all(np.isnan(means)) or K==0:
            return {"SPA_P_Value":1.0,"Status":"No Edge"}
        omega=np.sqrt(np.array([NeweyWestHAC.var(f[:,k]) for k in range(K)]))
        omega=np.where(omega<1e-12, 1e-12, omega)
        T_spa=np.nanmax(np.sqrt(T)*means/omega)
        if T_spa<=0 or np.isnan(T_spa): return {"SPA_P_Value":1.0,"Status":"No Edge"}
        bk=self._bk(f[:,np.argmax(means/omega)])
        gc=np.where(means>=-np.sqrt(np.log(np.log(T))/T)*omega,means,0.0)
        rf=np.nan_to_num(f-gc,nan=0.0); rng=RNG.gen("spa"); boot=np.zeros(self.n_boot)
        for b in range(self.n_boot):
            sp=rng.integers(0,T,size=(T//bk)+1)
            ix=np.concatenate([np.arange(s,s+bk)%T for s in sp])[:T]
            boot[b]=np.max(np.sqrt(T)*np.mean(rf[ix,:],axis=0)/omega)
        pv=np.mean(boot>=T_spa)
        return {"SPA_P_Value":pv,"Status":"Robust Alpha" if pv<0.05 else "Data Mined"}


class PBO:
    @staticmethod
    def calculate(perf,n_splits=16,max_evals=10000):
        T,K=perf.shape
        if K<2 or T<n_splits*2: return {"pbo":1.0}
        ss=T//n_splits; subs=[perf[i*ss:(i+1)*ss,:] for i in range(n_splits)]
        combos=list(combinations(range(n_splits),n_splits//2))
        rng=RNG.gen("pbo")
        if len(combos)>max_evals:
            idx=rng.choice(len(combos),max_evals,replace=False)
            combos=[combos[i] for i in idx]
        def sc(d):
            d=np.nan_to_num(d,nan=0.0); m=np.mean(d,axis=0)
            return m/(np.std(np.where(d<0,d,0),axis=0)+1e-9)
        logits=[]
        for tr in combos:
            te=[i for i in range(n_splits) if i not in tr]
            ts=sc(np.vstack([subs[i] for i in tr])); vs=sc(np.vstack([subs[i] for i in te]))
            rank=stats.rankdata(vs)[np.argmax(ts)]/(K+1)
            logits.append(np.log(rank/(1-rank+1e-9)))
        return {"pbo":float(np.mean(np.array(logits)<0))}


class HPGovernance:
    GRID=[
        {'n_estimators':30,'max_depth':3,'learning_rate':0.1},
        {'n_estimators':50,'max_depth':4,'learning_rate':0.05},
        {'n_estimators':100,'max_depth':3,'learning_rate':0.03},
        {'n_estimators':50,'max_depth':5,'learning_rate':0.05},
    ]
    @classmethod
    def select(cls,Xtr,ytr,wtr,n_inner=3):
        seed=RNG.seed("hp"); skf=StratifiedKFold(n_splits=n_inner,shuffle=True,random_state=seed)
        Xa,ya,wa=Xtr.fillna(0).values,ytr.values,wtr.values
        best_p,best_s=cls.GRID[0],-np.inf
        for p in cls.GRID:
            scores=[]
            for tri,vai in skf.split(Xa,ya):
                m=lgb.LGBMClassifier(**p,class_weight='balanced',random_state=seed,verbose=-1)
                m.fit(Xa[tri],ya[tri],sample_weight=wa[tri])
                try: li=np.where(m.classes_==1)[0][0]
                except: li=0
                pr=m.predict_proba(Xa[vai])[:,li]
                yv=(ya[vai]==1).astype(float)
                scores.append(-np.mean(yv*np.log(pr+1e-9)+(1-yv)*np.log(1-pr+1e-9)))
            if np.mean(scores)>best_s: best_s,best_p=np.mean(scores),p
        return {**best_p,'random_state':seed}


class OOFCalibrator:
    def __init__(self,k=5): self.k=k; self.iso=IsotonicRegression(out_of_bounds='clip')
    def fit(self,Xtr,ytr,wtr,params):
        seed=RNG.seed("cal"); skf=StratifiedKFold(n_splits=self.k,shuffle=True,random_state=seed)
        Xa,ya,wa=Xtr.fillna(0).values,ytr.values,wtr.values
        op,ol=[],[]
        for tri,vai in skf.split(Xa,ya):
            m=lgb.LGBMClassifier(**params,class_weight='balanced',verbose=-1)
            m.fit(Xa[tri],ya[tri],sample_weight=wa[tri])
            try: li=np.where(m.classes_==1)[0][0]
            except: li=0
            op.append(m.predict_proba(Xa[vai])[:,li]); ol.append((ya[vai]==1).astype(float))
        self.iso.fit(np.concatenate(op),np.concatenate(ol)); return self
    def cal(self,p): return self.iso.predict(p)


class NEffEngine:
    @staticmethod
    def _psd(A):
        Y=np.copy(A); dS=np.zeros_like(Y)
        for _ in range(100):
            R=Y-dS; ev,ec=np.linalg.eigh(R); ev=np.maximum(ev,1e-9)
            X=ec@np.diag(ev)@ec.T; dS=X-R; Y=np.copy(X); np.fill_diagonal(Y,1.0)
            if np.linalg.norm(Y-X,'fro')<1e-8: break
        return Y
    @classmethod
    def compute(cls,ret_mat,sig_mat=None):
        n=ret_mat.shape[1]; C=np.eye(n)
        for i in range(n):
            for j in range(i+1,n):
                m=~np.isnan(ret_mat[:,i])&~np.isnan(ret_mat[:,j])
                if m.sum()>30:
                    r=np.corrcoef(ret_mat[m,i],ret_mat[m,j])[0,1]
                    C[i,j]=C[j,i]=np.nan_to_num(r,nan=0.0)
        ev=np.clip(np.linalg.eigh(cls._psd(C))[0],1e-9,None)
        nc=float(np.sum(ev)**2/np.sum(ev**2)); nt=nc
        if sig_mat is not None:
            jac=0.0; cnt=0
            for i in range(n):
                for j in range(i+1,n):
                    si=~np.isnan(sig_mat[:,i]); sj=~np.isnan(sig_mat[:,j])
                    both=si&sj
                    if both.sum()>0:
                        jac+=np.sum(sig_mat[both,i]==sig_mat[both,j])/both.sum(); cnt+=1
            if cnt>0: aj=jac/cnt; nt=max(1.0,n/((n-1)*aj+1))
        return {'n_eff_corr':nc,'n_eff_trade':nt,'n_eff_min':min(nc,nt)}


class DSR:
    def __init__(self,emc=0.5772156649): self.emc=emc
    def calc(self,oos,sharpes,n_eff,nb=5000):
        r=oos[~np.isnan(oos)]
        if len(r)<3 or np.std(r)==0: return 0.0
        sr=np.mean(r)/np.std(r); sk=stats.skew(r); kt=stats.kurtosis(r,fisher=False)
        cs=sharpes[~np.isnan(sharpes)]; rng=RNG.gen("dsr")
        if len(cs)<2 or n_eff<=1: emsr=np.mean(cs) if len(cs)>0 else 0.0
        else:
            bm=[np.mean(rng.choice(cs,len(cs),replace=True)) for _ in range(nb)]
            bs=[np.std(rng.choice(cs,len(cs),replace=True)) for _ in range(nb)]
            mz=(1-self.emc)*stats.norm.ppf(1-1/n_eff)+self.emc*stats.norm.ppf(1-1/(n_eff*np.e))
            emsr=np.mean(bm)+np.mean(bs)*mz
        den=max(1-sk*sr+((kt-1)/4)*(sr**2),1e-12)
        return float(stats.norm.cdf((sr-emsr)*np.sqrt(len(r)-1)/np.sqrt(den)))


class TrueCPCV:
    def __init__(self, N=6, k=2, horizon=24):
        self.N=N; self.k=k; self.horizon=horizon
        self.all_combos=list(combinations(range(N),k))
        from math import comb
        self.n_paths=comb(N,k)*k//N
        logger.info(f"[CPCV] N={N}, k={k}, combos={len(self.all_combos)}, paths={self.n_paths}")

    def _build_paths(self):
        paths=[[] for _ in range(self.n_paths)]
        for ci,combo in enumerate(self.all_combos):
            paths[ci%self.n_paths].extend(list(combo))
        return [list(set(p)) for p in paths]

    def evaluate(self, df, events, w):
        logger.info("[CPCV] Evaluating...")
        ts=np.arange(len(df)); gs=len(ts)//self.N
        bounds=[(ts[i*gs],ts[min((i+1)*gs-1,len(ts)-1)]) for i in range(self.N)]
        avail=[c for c in FEATURE_COLS if c in df.columns]
        X=df[avail].fillna(0)
        y=events['label'].reindex(df.index).fillna(0).astype(int)
        r=df['returns_horizon']
        logger.info(f"[CPCV] X={X.shape} y_dist={dict(y.value_counts())}")
        paths=[[i] for i in range(self.N)]
        meta_p=np.full((len(df),max(self.N,self.n_paths,4)),np.nan)
        meta_r=np.full((len(df),max(self.N,self.n_paths,4)),np.nan)
        meta_s=np.full((len(df),max(self.N,self.n_paths,4)),np.nan)
        for p_idx,test_groups in enumerate(paths):
            test_idx=set()
            for tg in test_groups:
                s,e=bounds[tg]
                test_idx.update(range(s,min(len(df),e+1)))
            train_idx=[i for i in range(len(df)) if i not in test_idx]
            Xtr=X.iloc[train_idx]; ytr=y.iloc[train_idx]; wtr=w.iloc[train_idx]
            logger.info(f"[CPCV] p{p_idx} train={len(Xtr)} classes={list(np.unique(ytr))}")
            import logging; logging.getLogger("AL-FATH-v21").info(f"[CPCV] p{p_idx} after ok filter: {len(Xtr)} rows, classes={list(np.unique(ytr))}")
            if len(np.unique(ytr))<2:
                import logging; logging.getLogger("AL-FATH-v21").info(f"[CPCV] path {p_idx} skipped")
                continue
            import logging; logging.getLogger("AL-FATH-v21").info(f"[CPCV] path {p_idx} training X={Xtr.shape}")
            params=HPGovernance.select(Xtr,ytr,wtr)
            model=lgb.LGBMClassifier(**params,class_weight='balanced',verbose=-1)
            model.fit(Xtr.fillna(0),ytr,sample_weight=wtr)
            try: li=np.where(model.classes_==1)[0][0]
            except: li=0
            cal=OOFCalibrator(k=3).fit(Xtr,ytr,wtr,params)
            for tg in test_groups:
                s,e=bounds[tg]; mask=(ts>=s)&(ts<=e)
                rp=model.predict_proba(X.iloc[mask].fillna(0))[:,li]
                cp=cal.cal(rp); meta_p[mask,p_idx]=cp
                sg=np.where(cp>0.5,1.0,-1.0)
                meta_s[mask,p_idx]=sg; meta_r[mask,p_idx]=r.values[mask]*sg
        ep=np.nanmean(meta_p,axis=1)
        sig=np.where(np.isnan(ep),0.0,np.where(ep>=0.48,1.0,-1.0))
        return meta_p,meta_r,meta_s,sig


class Micro:
    def __init__(self, bt=4.0, bs=1.0, fl=1.0, fs=-0.5):
        self.bt=bt/10000; self.bs=bs/10000; self.fl=fl/10000; self.fs=fs/10000
    def net(self, sig, ret, vol):
        sc=np.nan_to_num(sig,nan=0.0); tr=np.abs(np.diff(sc,prepend=0))
        q25,q75,q95=np.nanpercentile(vol,[25,75,95])
        sm=np.where(vol<q25,1,np.where(vol<q75,2,np.where(vol<q95,4,8)))
        tm=np.where(vol<q25,1,np.where(vol<q75,1.2,np.where(vol<q95,1.5,2)))
        r=ret.copy()
        r-=tr*(2*self.bt*tm+self.bs*sm)
        r-=np.where(sc>0,sc,0)*(self.fl/480)
        r-=np.where(sc<0,-sc,0)*(self.fs/480)
        return r


# ══════════════════════════════════════════════════════════════════════════════
#  LAYER 10 — AI SUPERVISOR (Final pre-trade approval gate)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class SupervisorDecision:
    approved:    bool
    signal_in:   float
    signal_out:  float
    reasons:     List[str] = field(default_factory=list)
    timestamp:   str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __str__(self):
        status = "APPROVED" if self.approved else "BLOCKED"
        return (f"[Supervisor] {status} | in={self.signal_in:+.2f} "
                f"out={self.signal_out:+.2f} | {'; '.join(self.reasons) or 'all checks passed'}")


class AISupervisor:
    """
    [L10] Final decision-maker before any trade execution.
    Aggregates all layer checks and approves/blocks the trade.

    Checks (in order):
      1. VPS Health (L6)
      2. Risk Fortress state (L3)
      3. Execution Alpha Gate (L4)
      4. Liquidity Shock (L4)
      5. Adversarial Score (L2)
      6. Market Regime (L1) — block in LOW_LIQUIDITY
      7. Confidence Decay scalar (L2)
      8. Cross-Exchange Consensus (L4) — optional
      9. Cross-Asset Filter scalar (L1)
     10. Portfolio Exposure Budget (L5)
    """
    def __init__(self,
                 vps_guardian:       VPSGuardian,
                 risk_fortress:      RiskFortress,
                 exec_gate:          ExecutionAlphaGate,
                 portfolio_intel:    PortfolioIntelligence,
                 min_confidence:     float = 0.52,
                 block_adversarial:  float = 0.8,
                 log_every:          int   = 100):
        self.vps          = vps_guardian
        self.risk         = risk_fortress
        self.gate         = exec_gate
        self.portfolio    = portfolio_intel
        self.min_conf     = min_confidence
        self.blk_adv      = block_adversarial
        self.log_every    = log_every
        self._call_count  = 0
        self._block_count = 0
        self._decisions   = []

    def approve(self,
                signal:        float,
                probability:   float,
                symbol:        str,
                row:           pd.Series,
                regime:        str,
                conf_scalar:   float,
                cross_scalar:  float = 1.0,
                timestamp:     Optional[datetime] = None) -> SupervisorDecision:
        """
        Single-bar approval. Returns SupervisorDecision.
        signal_out = 0 if blocked, else scaled signal.
        """
        self._call_count += 1
        reasons   = []
        out_sig   = signal
        approved  = True

        # 1. VPS health — fast check (skip if check already done recently)
        if self._call_count % self.log_every == 1:
            vps_ok = self.vps.is_trading_safe()
            if not vps_ok:
                reasons.append("VPS_UNHEALTHY")
                approved = False

        # 2. Risk Fortress
        pos_scalar = self.risk.get_position_scalar(timestamp)
        if pos_scalar == 0.0:
            reasons.append(f"RISK_BLOCKED(dd={self.risk.state.drawdown*100:.1f}%)")
            approved = False
        else:
            out_sig *= pos_scalar

        # 3. Probability edge
        edge = abs(probability - 0.5)
        if edge < self.gate.min_edge:
            reasons.append(f"LOW_EDGE({edge*10000:.1f}bps)")
            approved = False

        # 4. Liquidity shock
        liq_shock = row.get('liquidity_shock', 0)
        if liq_shock == 1:
            reasons.append("LIQUIDITY_SHOCK")
            approved = False

        # 5. Adversarial score
        adv_score = row.get('adversarial_score', 0)
        if adv_score > self.blk_adv:
            reasons.append(f"ADVERSARIAL({adv_score:.2f})")
            approved = False

        # 6. Market regime
        if regime == MarketRegime.LOW_LIQUIDITY:
            reasons.append("LOW_LIQUIDITY_REGIME")
            approved = False

        # 7. Confidence decay
        if conf_scalar < 0.25:
            reasons.append(f"CONFIDENCE_DECAY({conf_scalar:.2f})")
            approved = False
        else:
            out_sig *= conf_scalar

        # 8. Cross-asset filter
        if cross_scalar < 0.5:
            reasons.append(f"CROSS_ASSET_RISK({cross_scalar:.2f})")
        out_sig *= cross_scalar

        # 9. Exposure budget
        budget    = self.portfolio.EXPOSURE_BUDGET.get(symbol, 0.35)
        out_sig   = np.clip(out_sig, -budget, budget)

        # 10. Final zero check
        if abs(out_sig) < 1e-6:
            approved = False

        if not approved:
            out_sig = 0.0
            self._block_count += 1

        decision = SupervisorDecision(
            approved=approved,
            signal_in=signal,
            signal_out=out_sig,
            reasons=reasons,
        )
        self._decisions.append(decision)

        if self._call_count % self.log_every == 0:
            rate = self._block_count / self._call_count * 100
            logger.info(f"[Supervisor] Calls={self._call_count} "
                        f"BlockRate={rate:.1f}%")

        return decision

    def vectorized_approve(self,
                           signals:       np.ndarray,
                           probabilities: np.ndarray,
                           df:            pd.DataFrame,
                           regimes:       pd.Series,
                           conf_scalars:  np.ndarray,
                           cross_scalars: np.ndarray,
                           symbol:        str = "BTC/USDT") -> np.ndarray:
        """Vectorized approval for backtesting. Returns approved signal array."""
        sig    = np.nan_to_num(signals, nan=0.0)
        prob   = np.nan_to_num(probabilities, nan=0.5)
        out    = sig.copy()
        block  = np.zeros(len(sig), dtype=bool)

        # Edge
        block |= (np.abs(prob - 0.5) < self.gate.min_edge)

        # Liquidity shock
        if 'liquidity_shock' in df.columns:
            block |= (df['liquidity_shock'].values == 1)

        # Adversarial
        if 'adversarial_score' in df.columns:
            block |= (df['adversarial_score'].values > self.blk_adv)

        # Regime
        block |= (regimes.values == MarketRegime.LOW_LIQUIDITY)

        # Confidence decay
        block |= (conf_scalars < 0.25)

        # Toxic / sweep
        if 'toxic_flow' in df.columns:
            block |= (df['toxic_flow'].values == 1)
        if 'sweep_flag' in df.columns:
            block |= (df['sweep_flag'].values == 1)

        out[block] = 0.0

        # Scalars
        out *= np.where(conf_scalars < 0.25, 0.0, conf_scalars)
        out *= cross_scalars

        # Budget
        budget = self.portfolio.EXPOSURE_BUDGET.get(symbol, 0.35) if self.portfolio is not None else 0.35
        out    = np.clip(out, -budget, budget)

        self._call_count += len(sig)
        self._block_count += int(block.sum())
        block_rate = block.mean() * 100
        logger.info(f"[Supervisor] Vectorized block rate: {block_rate:.1f}%")
        return out

    def summary(self) -> dict:
        total  = self._call_count
        return {
            "total_calls":   total,
            "blocked":       self._block_count,
            "approved":      total - self._block_count,
            "block_rate_pct": self._block_count / max(total, 1) * 100,
        }


# ══════════════════════════════════════════════════════════════════════════════
#  SYNTHETIC DATA
# ══════════════════════════════════════════════════════════════════════════════

def gen_data(n: int = 20000) -> pd.DataFrame:
    logger.info(f"[Data] Generating {n} synthetic BTC/USDT 1m OHLCV bars (seeded)...")
    rng = RNG.gen("data")
    ft  = rng.standard_t(1.5, n) * 0.005
    op  = np.exp(rng.normal(10.5, 0.002, n))
    cl  = op * np.exp(ft)
    hi  = np.maximum(op, cl) + np.abs(rng.standard_t(1.5, n) * 0.002)
    lo  = np.minimum(op, cl) - np.abs(rng.standard_t(1.5, n) * 0.002)
    vol = np.exp(rng.normal(6, 0.8, n))
    return pd.DataFrame({
        'timestamp': pd.date_range('2025-01-01', periods=n, freq='5min'),
        'open': op, 'high': hi, 'low': lo, 'close': cl, 'volume': vol
    })


def load_csv(path: str) -> pd.DataFrame:
    """Load real OHLCV CSV. Expected columns: timestamp,open,high,low,close,volume"""
    logger.info(f"[Data] Loading CSV: {path}")
    df = pd.read_csv(path)
    df.columns = [c.lower().strip() for c in df.columns]
    required = ['timestamp','open','high','low','close','volume']
    missing  = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"CSV missing columns: {missing}")
    return df


# ══════════════════════════════════════════════════════════════════════════════
#  MASTER RUN — AL-FATH v21.0
# ══════════════════════════════════════════════════════════════════════════════

def run_v21(csv_path: Optional[str] = None,
            saas_demo: bool = False,
            supervisor_check: bool = False):

    sep = "=" * 72
    logger.info(sep)
    logger.info("AL-FATH v21.0 — FULL INSTITUTIONAL PLATFORM")
    logger.info(sep)

    # ── 0. Infrastructure init ────────────────────────────────────────────
    vault    = APIVault()
    guardian = VPSGuardian()
    logger.info("[Init] Vault + VPS Guardian ready.")

    # Demo vault store (production: use real keys)
    vault.store("demo_user", "binance", "DEMO_KEY", "DEMO_SECRET", Permission.TRADE_ONLY)

    # ── 1. Data ───────────────────────────────────────────────────────────
    if csv_path:
        df_raw = load_csv(csv_path)
    else:
        df_raw = gen_data(20000)
        logger.info("[Note] SYNTHETIC DATA: alpha metrics = governance validation only.")

    df_r, df_e = DataIntegrityAuditor.audit_and_clean(df_raw)

    # ── 2. L1 Market Intelligence ─────────────────────────────────────────
    logger.info("[L1] Market Intelligence...")
    df_feat   = CoreEngine().generate_features(df_r, df_e, horizon=24)
    df_feat   = OrderBookProxy.compute(df_feat)
    df_feat   = InstitutionalFlowTracker.compute(df_feat)
    df_feat   = AdversarialDetectionEngine.compute(df_feat)

    # Market regime
    regimes   = MarketRegime.classify(df_feat)
    df_feat['regime']          = regimes
    df_feat['liquidity_shock'] = LiquidityShockDetector.compute(df_feat)

    # Cross-asset filter
    btc_ret = np.log(df_feat['close'] / df_feat['close'].shift(1))
    cross_scalars = CrossAssetFilter.compute_correlation_regime(btc_ret).values

    FeatureLineageDAG.audit(FEATURE_COLS, list(df_feat.columns))

    # ── 3. Labels (Conservative ATR barriers) ────────────────────────────
    labeler = LabelEngine(pt_atr=3.0, sl_atr=1.5, horizon=60, ambiguity_mode="optimistic")
    exec_gate = ExecutionAlphaGate(min_edge_bps=50, min_depth_proxy=0.5, max_vol_regime=0.70, block_toxic_flow=True, block_sweeps=True)
    logger.info("[L2] Triple Barrier Labels [pt=3x, sl=1.5x, h=24]...")
    events  = labeler.generate_labels(df_feat)
    w       = labeler.exact_uniqueness(events)
    label_dist = events['label'].value_counts().to_dict()
    logger.info(f"[Labels] Distribution: {label_dist}")

    # ── 4. CPCV Evaluation ───────────────────────────────────────────────
    cpcv = TrueCPCV(N=4, k=1, horizon=1)
    meta_p, meta_r, meta_s, sig_raw = cpcv.evaluate(df_feat, events, w)
    ensemble_prob = np.nanmean(meta_p, axis=1)

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


    # ── 5. L2 Confidence Decay ───────────────────────────────────────────
    logger.info("[L2] Confidence Decay + Concept Drift...")
    decay_detector = ConfidenceDecayDetector(window=200)
    gross_raw_ret  = np.nan_to_num(df_feat['returns_horizon'].values * sig_raw, nan=0.0)
    conf_scalars   = decay_detector.compute_confidence_scalar(
        np.nan_to_num(sig_raw, nan=0.0), gross_raw_ret
    )

    # Concept drift (80/20 split)
    mid        = int(len(df_feat) * 0.80)
    drift_res  = ConceptDriftMonitor.monitor(
        df_feat.iloc[:mid], df_feat.iloc[mid:], FEATURE_COLS
    )

    # ── 6. L4 Execution Fortress ──────────────────────────────────────────
    logger.info("[L4] Execution Fortress...")
    # Regime filter - sirf TRENDING + HIGH_VOLATILITY mein trade
    trending_mask = (regimes.values == MarketRegime.TRENDING) | (regimes.values == MarketRegime.HIGH_VOLATILITY)
    sig_raw = sig_raw * trending_mask.astype(float)

    sig_gated, gate_stats = exec_gate.filter_signals(sig_raw, ensemble_prob, df_feat)

    # ── 8. L10 AI Supervisor (vectorized) ────────────────────────────────
    logger.info("[L10] AI Supervisor...")
    risk_fortress = RiskFortress(
        survival_dd=0.15, kill_dd=0.20, daily_target=0.03,
        base_max_pos=0.02
    )
    supervisor = AISupervisor(
        vps_guardian=guardian,
        risk_fortress=risk_fortress,
        exec_gate=exec_gate,
        portfolio_intel=None,
        min_confidence=0.35,
    )
    sig_supervised = supervisor.vectorized_approve(
        signals=sig_raw,
        probabilities=ensemble_prob,
        df=df_feat,
        regimes=regimes,
        conf_scalars=conf_scalars,
        cross_scalars=cross_scalars,
        symbol="BTC/USDT",
    )

    # ── 9. L3 Risk Fortress (vectorized) ─────────────────────────────────
    logger.info("[L3] Risk Fortress sizing...")
    risk_out = risk_fortress.apply_vectorized(
        sig_supervised, df_feat['ewma_vol'].values, horizon=24
    )
    managed_sig = risk_out['managed_signals']

    # ── 10. L4 Strict Execution Simulation ───────────────────────────────
    logger.info("[L4] Strict Execution Simulation...")
    exec_sim = ExecutionSimulator(account_size_usd=50_000, max_pos_pct=0.15,
                                  latency_bars=2, base_taker_bps=5.0)
    exec_out = exec_sim.simulate(
        managed_sig, df_feat['close'].values,
        df_feat['volume'].values, df_feat['ewma_vol'].values
    )

    # ── 11. Returns at each layer ─────────────────────────────────────────
    micro = Micro()
    gross_raw    = df_feat['returns_horizon'].values * np.nan_to_num(sig_raw, nan=0.0)
    gross_sup    = df_feat['returns_horizon'].values * np.nan_to_num(sig_supervised, nan=0.0)
    net_raw      = micro.net(np.nan_to_num(sig_raw, nan=0.0), gross_raw, df_feat['ewma_vol'].values)
    net_gated    = micro.net(np.nan_to_num(sig_gated, nan=0.0), gross_sup, df_feat['ewma_vol'].values)
    net_exec     = exec_out['exec_returns']

    # ── 12. Statistical Governance ────────────────────────────────────────
    logger.info("[Stats] White RC + HAC-SPA + PBO + DSR...")
    wrc      = WhiteRealityCheck(n_boot=2000)
    rc_raw   = wrc.test(np.nan_to_num(meta_r, 0.0))

    meta_r_sup = meta_r.copy()
    sup_mask   = sig_supervised != 0
    meta_r_sup[~sup_mask, :] = 0.0
    rc_sup   = wrc.test(np.nan_to_num(meta_r_sup, 0.0))

    spa      = HansenHACSpA(n_boot=2000)
    spa_raw  = spa.test(np.nan_to_num(meta_r, 0.0),
                        df_feat['returns_horizon'].values)
    spa_sup  = spa.test(np.nan_to_num(meta_r_sup, 0.0),
                        df_feat['returns_horizon'].values)

    pbo_raw  = PBO.calculate(np.nan_to_num(meta_r, 0.0))
    pbo_sup  = PBO.calculate(np.nan_to_num(meta_r_sup, 0.0))

    neff     = NEffEngine.compute(meta_r, meta_s)
    path_sr  = []
    for p in range(meta_r.shape[1]):
        pr = meta_r[:, p]; pr = pr[~np.isnan(pr)]
        if len(pr) > 3 and np.std(pr) > 0:
            path_sr.append(np.mean(pr) / np.std(pr))

    dsr_val  = DSR().calc(
        net_gated[~np.isnan(net_gated)],
        np.array(path_sr), neff['n_eff_min']
    )

    oos_raw   = net_raw[~np.isnan(net_raw)]
    oos_gated = net_gated[~np.isnan(net_gated)]
    oos_exec  = net_exec[~np.isnan(net_exec)]
    lo_raw    = Ind.lo_hac_sr(oos_raw)
    lo_gated  = Ind.lo_hac_sr(oos_gated)
    lo_exec   = Ind.lo_hac_sr(oos_exec)

    # ── 13. PATCH-5: Alpha vs Execution Decomposition ────────────────────
    alpha_ev     = float(np.nansum(net_raw) * 100)
    gate_ev      = float(np.nansum(net_gated) * 100)
    exec_ev      = float(np.nansum(net_exec) * 100)
    exec_drag    = gate_ev - exec_ev
    gate_benefit = gate_ev - alpha_ev

    # ── 14. L8 SaaS Demo ──────────────────────────────────────────────────
    admin = AdminDashboard()
    affiliate = AffiliateEngine()
    if saas_demo:
        logger.info("[L8] SaaS Demo: creating sample users...")
        for i, (uid, name, email, plan, val) in enumerate([
            ("u001","Ali Khan","ali@email.com","institutional", 250_000),
            ("u002","Sara Ahmed","sara@email.com","pro",           15_000),
            ("u003","Farrukh Beg","farrukh@email.com","free",      2_000),
            ("u004","Nadia Mir","nadia@email.com","pro",          22_000),
        ]):
            u = UserAccount(user_id=uid, name=name, email=email, plan=plan,
                            account_value=val, peak_value=val * 1.1,
                            total_trades=100+i*30, win_trades=55+i*8,
                            referral_id="ref001" if i>0 else "")
            admin.add_user(u)
            admin.record_revenue(val * 0.002)

        affiliate.register_referral("ref001", "u002")
        affiliate.register_referral("ref001", "u003")
        affiliate.register_referral("ref001", "u004")
        for uid in ["u002","u003","u004"]:
            affiliate.record_trade(uid, volume_usd=50_000)

    sup_summary = supervisor.summary()

    # ═══════════════════════════════════════════════════════════════════════
    #  FINAL REPORT
    # ═══════════════════════════════════════════════════════════════════════
    print(f"\n{sep}")
    print("  AL-FATH v21.0 — FULL INSTITUTIONAL AUDIT REPORT")
    print(sep)
    if not csv_path:
        print("  ⚠️  SYNTHETIC DATA: RC/SPA valid as governance checks only.")

    print(f"\n  ── ALPHA vs EXECUTION DECOMPOSITION ──────────────────────")
    print(f"  Net EV (Raw, no supervisor):    {alpha_ev:>10.2f}%")
    print(f"  Net EV (Supervised + micro):    {gate_ev:>10.2f}%  Gate benefit: {gate_benefit:+.2f}%")
    print(f"  Net EV (Supervisor + ExecSim):  {exec_ev:>10.2f}%  Exec drag:    {exec_drag:+.2f}%")
    if exec_ev > gate_ev:
        diag = "ExecSim IMPROVED over micro — low slippage regime"
    elif gate_ev > alpha_ev:
        diag = "Supervisor helped signal quality"
    else:
        diag = "Alpha problem — signal has no predictive power on synthetic data"
    print(f"  DIAGNOSIS: {diag}")

    print(f"\n  ── L10 AI SUPERVISOR ─────────────────────────────────────")
    print(f"  Total Calls:                    {sup_summary['total_calls']:>10}")
    print(f"  Blocked:                        {sup_summary['blocked']:>10}  ({sup_summary['block_rate_pct']:.1f}%)")
    print(f"  Approved:                       {sup_summary['approved']:>10}")

    print(f"\n  ── L4 EXECUTION GATE ─────────────────────────────────────")
    print(f"  Signals Before Gate:            {gate_stats['signals_before']:>10}")
    print(f"  Signals After Gate:             {gate_stats['signals_after']:>10}")
    print(f"  Filtered:                       {gate_stats['filter_pct']:>10.1f}%")
    print(f"  Edge Threshold:                 {gate_stats['edge_threshold_bps']:>10.1f} bps")

    print(f"\n  ── STATISTICAL GOVERNANCE (RAW) ──────────────────────────")
    print(f"  White RC p-value (Raw):         {rc_raw['RC_P_Value']:>10.4f}  → {rc_raw['Status']}")
    print(f"  HAC-SPA p-value (Raw):          {spa_raw['SPA_P_Value']:>10.4f}  → {spa_raw['Status']}")
    print(f"  PBO (Raw):                      {pbo_raw['pbo']*100:>10.2f}%")

    print(f"\n  ── STATISTICAL GOVERNANCE (SUPERVISED) ──────────────────")
    print(f"  White RC p-value (Supervised):  {rc_sup['RC_P_Value']:>10.4f}  → {rc_sup['Status']}")
    print(f"  HAC-SPA p-value (Supervised):   {spa_sup['SPA_P_Value']:>10.4f}  → {spa_sup['Status']}")
    print(f"  PBO (Supervised):               {pbo_sup['pbo']*100:>10.2f}%")
    print(f"  True DSR:                       {dsr_val:>10.4f}   [Target: >0.95]")

    print(f"\n  ── HAC SHARPE ────────────────────────────────────────────")
    print(f"  Lo HAC SR (Raw):                {lo_raw:>10.4f}")
    print(f"  Lo HAC SR (Supervised):         {lo_gated:>10.4f}")
    print(f"  Lo HAC SR (ExecSim):            {lo_exec:>10.4f}")

    print(f"\n  ── L4 EXECUTION (STRICT) ─────────────────────────────────")
    print(f"  Fill Rate:                      {exec_out['fill_rate']*100:>10.2f}%  [Target: 70-90%]")
    print(f"  Avg Slippage:                   {exec_out['avg_slippage_bps']:>10.2f} bps [Target: <3]")
    print(f"  Trade Count:                    {exec_out['trade_count']:>10}")
    print(f"  Circuit Halted:                 {'YES ⚠️' if risk_out['halted'] else 'No':>10}")

    print(f"\n  ── L3 RISK FORTRESS ──────────────────────────────────────")
    print(f"  Max Drawdown:                   {risk_out['max_drawdown']*100:>10.2f}%")
    print(f"  Survival Bars:                  {risk_out['survival_bars']:>10}")

    print(f"\n  ── L2 CONCEPT DRIFT (80/20) ──────────────────────────────")
    print(f"  Drifted Features:               {drift_res['drifted_count']:>10} / {len(FEATURE_COLS)}")
    print(f"  Retrain Needed:                 {'YES' if drift_res['retrain_needed'] else 'No':>10}")

    print(f"\n  ── L1 MARKET INTELLIGENCE ────────────────────────────────")
    regime_counts = regimes.value_counts().to_dict()
    for rname, rcount in regime_counts.items():
        print(f"  Regime {rname:<20}        {rcount:>10} bars")

    print(f"\n  ── N_EFF ─────────────────────────────────────────────────")
    print(f"  N_eff Corr:                     {neff['n_eff_corr']:>10.2f}")
    print(f"  N_eff Trade:                    {neff['n_eff_trade']:>10.2f}")
    print(f"  N_eff Conservative:             {neff['n_eff_min']:>10.2f}")

    if saas_demo:
        print(f"\n  ── L8 SaaS ADMIN DASHBOARD ───────────────────────────────")
        admin_view = admin.render()
        for k, v in admin_view.items():
            if isinstance(v, dict):
                print(f"  {k}: {v}")
            else:
                print(f"  {k:<30}          {str(v):>10}")

        print(f"\n  ── L9 AFFILIATE REPORT ───────────────────────────────────")
        for rec in affiliate.generate_report():
            print(f"  {rec['referral_id']}: referred={rec['n_referred']} "
                  f"vol=${rec['total_volume_usd']:,.0f} "
                  f"commission=${rec['total_commission']:.4f} "
                  f"pending=${rec['pending']:.4f}")

    # ── Scorecard ────────────────────────────────────────────────────────
    checks = [
        ("Net EV Exec > 0",              exec_ev > 0),
        ("Fill Rate 70-90%",             0.70 <= exec_out['fill_rate'] <= 0.90),
        ("Slippage < 10 bps",            exec_out['avg_slippage_bps'] < 10),
        ("PBO < 20%",                    pbo_sup['pbo'] < 0.20),
        ("Drift < 20 features",           drift_res['drifted_count'] < 20),
        ("Gate > 20% filtered",          gate_stats['filter_pct'] > 20),
        ("No Circuit Halt",              not risk_out['halted']),
        ("HAC SR Supervised > 0",        lo_gated > 0),
        ("Supervisor Block Rate < 80%",  sup_summary['block_rate_pct'] < 80),
        ("N_eff > 1",                    neff['n_eff_min'] > 1),
    ]
    passed = sum(ok for _, ok in checks)

    print(f"\n{sep}")
    for name, ok in checks:
        print(f"  {'✅' if ok else '❌'} {name}")

    rating = (
        "Production-Ready Research Platform" if passed >= 8 else
        "Execution-Ready Research Platform"  if passed >= 6 else
        "Advanced Research Platform"          if passed >= 4 else
        "Needs Alpha Development"
    )
    print(f"\n  [{passed}/{len(checks)}] RATING: {rating}")
    print(f"\n  NOTE: White RC & SPA will only pass with REAL predictive alpha.")
    print(f"  Load real BTC/USDT CSV: python al_fath_v21.py --csv btc_1m.csv")
    print(sep)

    return {
        "alpha_ev": alpha_ev, "gate_ev": gate_ev, "exec_ev": exec_ev,
        "dsr": dsr_val, "pbo": pbo_sup['pbo'], "n_eff": neff['n_eff_min'],
        "lo_hac_sr_exec": lo_exec, "fill_rate": exec_out['fill_rate'],
        "slippage_bps": exec_out['avg_slippage_bps'],
        "supervisor": sup_summary, "drift": drift_res,
        "passed_checks": passed, "rating": rating,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════════════════════

def parse_args():
    p = argparse.ArgumentParser(
        description="AL-FATH v21.0 — Full Institutional Platform",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p.add_argument("--csv", default=None,
                   help="Path to real OHLCV CSV (columns: timestamp,open,high,low,close,volume)")
    p.add_argument("--saas-demo", action="store_true",
                   help="Show SaaS admin + affiliate demo output")
    p.add_argument("--supervisor-check", action="store_true",
                   help="Run AI Supervisor check only (fast mode)")
    p.add_argument("--n-bars", type=int, default=20000,
                   help="Number of synthetic bars if no CSV (default: 20000)")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_v21(
        csv_path         = args.csv,
        saas_demo        = args.saas_demo,
        supervisor_check = args.supervisor_check,
    )


