"""從 Google Cloud 下載 ECMWF IFS 0.1° oper 00Z 預報 (0–120h, 每 3h)。

只用 byte-range 抓需要的欄位：
  sfc: msl, 10u, 10v
  pl : gh, u, v @ 850 hPa
"""
import datetime as dt
import os
import sys

from ecmwf.opendata import Client

DATE = sys.argv[1] if len(sys.argv) > 1 else dt.datetime.utcnow().strftime("%Y%m%d")
STEPS = list(range(0, 121, 3))
# 只抓部分時次 (逐 run 比較用)，例如 STEPS="24,48" python3 download_ecmwf.py 20261111
if os.environ.get("STEPS"):
    STEPS = [int(x) for x in os.environ["STEPS"].split(",")]
OUTDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", DATE)
os.makedirs(OUTDIR, exist_ok=True)

client = Client(source="google", model="ifs", resol="0p1")

common = dict(date=DATE, time=0, stream="oper", type="fc", step=STEPS)

sfc_file = os.path.join(OUTDIR, f"ifs_0p1_{DATE}00_sfc.grib2")
pl_file = os.path.join(OUTDIR, f"ifs_0p1_{DATE}00_pl850.grib2")

print("Downloading surface fields ->", sfc_file)
client.retrieve(**common, levtype="sfc", param=["msl", "10u", "10v"], target=sfc_file)

print("Downloading 850 hPa fields ->", pl_file)
client.retrieve(**common, levtype="pl", levelist=850, param=["gh", "u", "v"], target=pl_file)

print("Done.")
