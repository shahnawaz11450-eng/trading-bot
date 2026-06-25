import subprocess, json, os, time
from datetime import datetime, timezone

SYMBOLS = {
    'BTC': 'btc_enhanced.csv',
    'ETH': 'eth_enhanced.csv',
    'SOL': 'sol_enhanced.csv',
}

AL_FATH_DIR = "/root/al_fath_v21"
PYTHON_BIN = os.path.join(AL_FATH_DIR, "venv/bin/python")
SCRIPT = os.path.join(AL_FATH_DIR, "al_fath_v21.py")
STATUS_FILE = "/var/www/alfath/bot_status.json"

def run_symbol(symbol, csv_file):
    print(f"[{datetime.now(timezone.utc).isoformat()}] Running {symbol}...")
    proc = subprocess.run(
        [PYTHON_BIN, SCRIPT, '--csv', csv_file],
        cwd=AL_FATH_DIR,
        capture_output=True, text=True, timeout=600
    )
    return proc.stdout + proc.stderr

def parse(output, symbol):
    import re
    result = {"symbol": symbol}
    m = re.search(r"Execution-Simulated PnL.*?([-\d.]+)%", output)
    if m: result["exec_pnl"] = float(m.group(1))
    m = re.search(r"win_rate_pct': ([\d.]+)", output)
    if m: result["win_rate"] = float(m.group(1))
    m = re.search(r"\[(\d+)/(\d+)\] RATING: (.+)", output)
    if m: result["rating"] = f"{m.group(1)}/{m.group(2)}"
    return result

while True:
    results = []
    for sym, csv in SYMBOLS.items():
        out = run_symbol(sym, csv)
        r = parse(out, sym)
        results.append(r)
        print(f"  {sym}: {r}")

    best = max(results, key=lambda x: x.get('exec_pnl', -999))
    print(f"\nBest: {best['symbol']} with {best.get('exec_pnl')}%\n")

    status = {
        "last_run_utc": datetime.now(timezone.utc).isoformat(),
        "run_success": True,
        "multi_symbol": results,
        "best_symbol": best['symbol'],
        "bot_mode": "MULTI_SYMBOL_RESEARCH",
    }
    os.makedirs("/var/www/alfath", exist_ok=True)
    with open(STATUS_FILE, "w") as f:
        json.dump(status, f, indent=2)

    print(f"Sleeping 15 minutes...")
    time.sleep(900)
