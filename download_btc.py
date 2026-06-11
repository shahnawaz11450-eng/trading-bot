import requests, csv, time

url = "https://api.binance.com/api/v3/klines"
params = {"symbol": "BTCUSDT", "interval": "1m", "limit": 1000}

all_data = []
end_time = None

print("Downloading BTC/USDT 1m data...")

for i in range(50):
    if end_time:
        params["endTime"] = end_time
    r = requests.get(url, params=params)
    data = r.json()
    if not data:
        break
    all_data = data + all_data
    end_time = data[0][0] - 1
    time.sleep(0.3)

with open("btc_1m.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["timestamp","open","high","low","close","volume"])
    for d in all_data:
        w.writerow([d[0],d[1],d[2],d[3],d[4],d[5]])

print(f"Done! {len(all_data)} rows saved to btc_1m.csv")
