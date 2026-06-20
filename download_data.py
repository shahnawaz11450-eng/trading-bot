import requests, csv, time
from datetime import datetime, timezone

url = "https://api.binance.com/api/v3/klines"
params = {"symbol": "BTCUSDT", "interval": "5m", "limit": 1000}
all_data = []
end_time = None
print("Downloading BTC/USDT 5m data...")
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
with open("btc_5m_real.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["timestamp","open","high","low","close","volume"])
    for d in all_data:
        dt = datetime.fromtimestamp(int(d[0])/1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        w.writerow([dt,d[1],d[2],d[3],d[4],d[5]])
print("5m done! rows: " + str(len(all_data)))

fund_url = "https://fapi.binance.com/fapi/v1/fundingRate"
fund_params = {"symbol": "BTCUSDT", "limit": 1000}
all_funding = []
end_time = None
print("Downloading Funding Rate...")
for i in range(10):
    if end_time:
        fund_params["endTime"] = end_time
    r = requests.get(fund_url, params=fund_params)
    data = r.json()
    if not data or not isinstance(data, list):
        break
    all_funding = data + all_funding
    end_time = data[0]["fundingTime"] - 1
    time.sleep(0.3)
with open("btc_funding.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["timestamp","funding_rate"])
    for d in all_funding:
        dt = datetime.fromtimestamp(int(d["fundingTime"])/1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        w.writerow([dt,d["fundingRate"]])
print("Funding done! rows: " + str(len(all_funding)))
