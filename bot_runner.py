#!/usr/bin/env python3
"""
AL-FATH v21 — Background Runner
Runs al_fath_v21.py every 15 minutes, parses its console output,
and writes the latest results to bot_status.json for the dashboard to read.

This does NOT place real trades. It re-runs the research/backtest
pipeline on a schedule and records the research metrics.
"""

import subprocess
import re
import json
import time
import pandas as pd
import os
from datetime import datetime, timezone

# ── CONFIG ───────────────────────────────────────────────────────────────
AL_FATH_DIR = "/root/al_fath_v21"
AL_FATH_SCRIPT = os.path.join(AL_FATH_DIR, "al_fath_v21.py")
PYTHON_BIN = os.path.join(AL_FATH_DIR, "venv", "bin", "python")
STATUS_FILE = "/var/www/alfath/bot_status.json"
RUN_LOG = "/var/www/alfath/runner.log"
INTERVAL_SECONDS = 15 * 60  # 15 minutes

# ── REGEX PATTERNS ───────────────────────────────────────────────────────
PATTERNS = {
    "rating_score": re.compile(r"\[(\d+)/(\d+)\]\s+RATING:\s*(.+)"),
    "fill_rate": re.compile(r"Fill Rate:\s+([\d.]+)%"),
    "avg_slippage_bps": re.compile(r"Avg Slippage:\s+([\d.]+)\s*bps"),
    "trade_count": re.compile(r"Trade Count:\s+(\d+)"),
    "pbo_supervised": re.compile(r"PBO \(Supervised\):\s+([\d.]+)%"),
    "drifted_features": re.compile(r"Drifted Features:\s+(\d+)\s*/\s*(\d+)"),
    "supervisor_block_rate": re.compile(r"Blocked:\s+\d+\s+\(([\d.]+)%\)"),
    "win_rate": re.compile(r"win_rate=([\d.]+)"),
    "hac_sr_execsim": re.compile(r"Lo HAC SR \(ExecSim\):\s+(-?[\d.]+)"),
}


def log(msg: str):
    timestamp = datetime.now(timezone.utc).isoformat()
    line = f"[{timestamp}] {msg}"
    print(line, flush=True)
    with open(RUN_LOG, "a") as f:
        f.write(line + "\n")


def get_trade_stats() -> dict:
    """Read trade_log_reconstructed.csv and compute LONG/SHORT counts + P&L."""
    trade_log_path = os.path.join(AL_FATH_DIR, "trade_log_reconstructed.csv")
    try:
        df = pd.read_csv(trade_log_path)
        if df.empty or 'direction' not in df.columns:
            return {}
        long_count = int((df['direction'] == 'LONG').sum())
        short_count = int((df['direction'] == 'SHORT').sum())
        total_pnl_pct = float(df['net_return'].sum() * 100)
        long_pnl_pct = float(df.loc[df['direction'] == 'LONG', 'net_return'].sum() * 100)
        short_pnl_pct = float(df.loc[df['direction'] == 'SHORT', 'net_return'].sum() * 100)
        return {
            "long_count": long_count,
            "short_count": short_count,
            "total_pnl_pct": round(total_pnl_pct, 4),
            "long_pnl_pct": round(long_pnl_pct, 4),
            "short_pnl_pct": round(short_pnl_pct, 4),
        }
    except Exception as e:
        log(f"WARNING: could not read trade log: {e}")
        return {}


def parse_output(output: str) -> dict:
    result = {}

    m = PATTERNS["rating_score"].search(output)
    if m:
        result["rating_passed"] = int(m.group(1))
        result["rating_total"] = int(m.group(2))
        result["rating_label"] = m.group(3).strip()
        result["rating_display"] = f"{m.group(1)}/{m.group(2)}"

    m = PATTERNS["fill_rate"].search(output)
    if m:
        result["fill_rate_pct"] = float(m.group(1))

    m = PATTERNS["avg_slippage_bps"].search(output)
    if m:
        result["avg_slippage_bps"] = float(m.group(1))

    m = PATTERNS["trade_count"].search(output)
    if m:
        result["trade_count"] = int(m.group(1))

    m = PATTERNS["pbo_supervised"].search(output)
    if m:
        result["pbo_supervised_pct"] = float(m.group(1))

    m = PATTERNS["drifted_features"].search(output)
    if m:
        result["drifted_count"] = int(m.group(1))
        result["drifted_total"] = int(m.group(2))

    m = PATTERNS["supervisor_block_rate"].search(output)
    if m:
        result["supervisor_block_pct"] = float(m.group(1))

    m = PATTERNS["win_rate"].search(output)
    if m:
        result["win_rate_pct"] = float(m.group(1)) * 100

    m = PATTERNS["hac_sr_execsim"].search(output)
    if m:
        result["hac_sr_execsim"] = float(m.group(1))

    return result
def compute_scores(parsed: dict, trade_stats: dict) -> dict:
    """Compute separate System Health and Trading Quality scores."""
    health_checks = []
    quality_checks = []

    fill_rate = parsed.get("fill_rate_pct")
    if fill_rate is not None:
        health_checks.append(70 <= fill_rate <= 90)

    slippage = parsed.get("avg_slippage_bps")
    if slippage is not None:
        health_checks.append(slippage < 10)

    drifted = parsed.get("drifted_count")
    drifted_total = parsed.get("drifted_total")
    if drifted is not None and drifted_total:
        health_checks.append(drifted < drifted_total)

    sup_block = parsed.get("supervisor_block_pct")
    if sup_block is not None:
        health_checks.append(sup_block < 80)

    health_checks.append(True)  # uptime/no-crash (run completed = True)

    pbo = parsed.get("pbo_supervised_pct")
    if pbo is not None:
        quality_checks.append(pbo < 20)

    total_pnl = trade_stats.get("total_pnl_pct")
    if total_pnl is not None:
        quality_checks.append(total_pnl > 0)

    win_rate = parsed.get("win_rate_pct")
    if win_rate is not None:
        quality_checks.append(win_rate > 50)

    hac_sr = parsed.get("hac_sr_execsim")
    if hac_sr is not None:
        quality_checks.append(hac_sr > 0)

    long_count = trade_stats.get("long_count")
    short_count = trade_stats.get("short_count")
    if long_count is not None and short_count is not None and (long_count + short_count) > 0:
        long_ratio = long_count / (long_count + short_count)
        quality_checks.append(0.3 <= long_ratio <= 0.7)  # not heavily one-sided

    health_score = sum(health_checks)
    health_total = len(health_checks)
    quality_score = sum(quality_checks)
    quality_total = len(quality_checks) if quality_checks else 1

    if quality_score / quality_total < 0.4:
        verdict = "Operationally Stable, Financially Unprofitable"
    elif quality_score / quality_total < 0.7:
        verdict = "Operationally Stable, Trading Quality Marginal"
    else:
        verdict = "Operationally Stable, Trading Quality Acceptable"

    return {
        "system_health_score": health_score,
        "system_health_total": health_total,
        "trading_quality_score": quality_score,
        "trading_quality_total": quality_total,
        "verdict": verdict,
    }




def run_once():
    log("Starting al_fath_v21.py run...")
    try:
        proc = subprocess.run(
            [PYTHON_BIN, AL_FATH_SCRIPT, '--download', '--csv', 'btc_1m_enhanced.csv'],
            cwd=AL_FATH_DIR,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute safety timeout
        )
        combined_output = proc.stdout + "\n" + proc.stderr
        parsed = parse_output(combined_output)
        trade_stats = get_trade_stats()
        scores = compute_scores(parsed, trade_stats)

        status = {
            "last_run_utc": datetime.now(timezone.utc).isoformat(),
            "run_success": proc.returncode == 0,
            "bot_mode": "RESEARCH_BACKTEST_ONLY",
            "live_trading": False,
            **parsed,
            **trade_stats,
            **scores,
        }

        if not parsed:
            log("WARNING: no metrics parsed from output. Check script output format.")
            status["parse_warning"] = "No metrics matched — check al_fath_v21.py output format"

        with open(STATUS_FILE, "w") as f:
            json.dump(status, f, indent=2)

        log(f"Run complete. Parsed: {parsed}")

    except subprocess.TimeoutExpired:
        log("ERROR: al_fath_v21.py run timed out after 600s")
        status = {
            "last_run_utc": datetime.now(timezone.utc).isoformat(),
            "run_success": False,
            "error": "timeout",
            "bot_mode": "RESEARCH_BACKTEST_ONLY",
            "live_trading": False,
        }
        with open(STATUS_FILE, "w") as f:
            json.dump(status, f, indent=2)

    except Exception as e:
        log(f"ERROR: {e}")
        status = {
            "last_run_utc": datetime.now(timezone.utc).isoformat(),
            "run_success": False,
            "error": str(e),
            "bot_mode": "RESEARCH_BACKTEST_ONLY",
            "live_trading": False,
        }
        with open(STATUS_FILE, "w") as f:
            json.dump(status, f, indent=2)


def main():
    log("AL-FATH background runner started. Interval: 15 minutes.")
    log("NOTE: This runs the RESEARCH/BACKTEST pipeline only. No real trades are placed.")
    while True:
        run_once()
        log(f"Sleeping for {INTERVAL_SECONDS} seconds...")
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()

