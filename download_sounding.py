"""下載探空用的 ECMWF IFS 0.1° 多層資料 (Google Cloud)。

時間：初始場起每 24 h（台北早上 08 時 = 00Z），0/24/48/72/96/120 h
  pl : t, q, u, v, gh @ 1000–50 hPa (13 層)
  sfc: sp, 2t, 2d, 10u, 10v

用法: python3 download_sounding.py [YYYYMMDD]
"""
import datetime as dt
import os
import sys

from ecmwf.opendata import Client

DATE = sys.argv[1] if len(sys.argv) > 1 else dt.datetime.utcnow().strftime("%Y%m%d")
STEPS = [0, 24, 48, 72, 96, 120]
LEVELS = [1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100, 50]
OUTDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", DATE)
os.makedirs(OUTDIR, exist_ok=True)

client = Client(source="google", model="ifs", resol="0p1")
common = dict(date=DATE, time=0, stream="oper", type="fc", step=STEPS)

sfc_file = os.path.join(OUTDIR, f"ifs_0p1_{DATE}00_sounding_sfc.grib2")
pl_file = os.path.join(OUTDIR, f"ifs_0p1_{DATE}00_sounding_pl.grib2")

print("Downloading surface fields ->", sfc_file)
client.retrieve(**common, levtype="sfc", param=["sp", "2t", "2d", "10u", "10v"], target=sfc_file)
print("Downloading pressure-level fields ->", pl_file)
client.retrieve(**common, levtype="pl", levelist=LEVELS, param=["t", "q", "u", "v", "gh"],
                target=pl_file)
print("Done.")
