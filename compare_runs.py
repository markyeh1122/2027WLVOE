"""逐 run 比較：準備「有效時間 = 本報初始時間」的前幾報預報圖。

例：本報 2026-11-13 00Z → 需要
    11/12 00Z +24h、11/11 +48h、11/10 +72h、11/09 +96h、11/08 +120h
已經有圖的就直接用，沒有的才只下載那一個時次再畫 (地面 + 850 hPa，風羽與流線)。

用法: python3 compare_runs.py 20261113
接著執行 python3 build_site.py 20261113 放進網站。
"""
import datetime as dt
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATE = sys.argv[1] if len(sys.argv) > 1 else dt.datetime.utcnow().strftime("%Y%m%d")
LEADS = [24, 48, 72, 96, 120]
SUBS = ["mslp_10m", "850hPa", "mslp_10m_stream", "850hPa_stream"]

t0 = dt.datetime.strptime(DATE, "%Y%m%d")
need = {}
for lead in LEADS:
    run = (t0 - dt.timedelta(hours=lead)).strftime("%Y%m%d")
    have = all(os.path.exists(os.path.join(HERE, "figures", run, sub, f"{sub}_{run}00_f{lead:03d}.png"))
               for sub in SUBS)
    print(f"{run} 00Z +{lead}h:", "已有圖" if have else "需要下載")
    if not have:
        need.setdefault(run, []).append(lead)

for run, steps in need.items():
    env = dict(os.environ, STEPS=",".join(map(str, steps)))
    print(f"== {run} 00Z steps {steps}")
    subprocess.run([sys.executable, os.path.join(HERE, "download_ecmwf.py"), run], env=env, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run([sys.executable, os.path.join(HERE, "plot_ecmwf.py"), run], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print("Done.")
