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

    return result


def run_once():
    log("Starting al_fath_v21.py run...")
    try:
        proc = subprocess.run(
            [PYTHON_BIN, AL_FATH_SCRIPT, '--download'],
            cwd=AL_FATH_DIR,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute safety timeout
        )
        combined_output = proc.stdout + "\n" + proc.stderr
        parsed = parse_output(combined_output)
        trade_stats = get_trade_stats()

        status = {
            "last_run_utc": datetime.now(timezone.utc).isoformat(),
            "run_success": proc.returncode == 0,
            "bot_mode": "RESEARCH_BACKTEST_ONLY",
            "live_trading": False,
            **parsed,
            **trade_stats,
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

