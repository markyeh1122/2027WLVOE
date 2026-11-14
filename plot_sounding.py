"""ECMWF IFS 0.1° 預報探空 (Skew-T log-p)，仿中央氣象署探空圖樣式。
5 個地點 × 每天台北 08 時 (00Z)：0/24/48/72/96/120 h

用法: python3 plot_sounding.py [YYYYMMDD]
輸出: figures/{DATE}/sounding/{site}_f{hhh}.png 與 sounding_meta.json
測試: ONLY=0,0 python3 plot_sounding.py 20261113   (只畫第 0 個地點、第 0 個時間)
"""
import datetime as dt
import json
import os
import sys
import warnings

import numpy as np
import xarray as xr
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import NullFormatter, FixedLocator
import metpy.calc as mpcalc
from metpy.plots import SkewT
from metpy.units import units

warnings.filterwarnings("ignore")
SERIF = ["Times New Roman", "Liberation Serif", "DejaVu Serif"]  # Liberation Serif: Linux 上與 Times 等寬的替代字型
plt.rcParams["font.family"] = SERIF
plt.rcParams["mathtext.fontset"] = "stix"

DATE = sys.argv[1] if len(sys.argv) > 1 else dt.datetime.utcnow().strftime("%Y%m%d")
HERE = os.path.dirname(os.path.abspath(__file__))
DATADIR = os.path.join(HERE, "data", DATE)
OUTDIR = os.path.join(HERE, "figures", DATE, "sounding")
os.makedirs(OUTDIR, exist_ok=True)

SITES = [  # (代號, 選單名稱, 圖上標籤 / 文字檔名, 緯度, 經度)
    ("banqiao", "新北氣象站 (46692)",        "STATION = 46692", 24.96, 121.53),
    ("pengjia", "彭佳嶼氣象站 (46695)",      "STATION = 46695", 25.628, 122.080),
    ("ishigaki", "石垣島氣象站 (47918)",     "STATION = 47918", 24.337, 124.164),
    ("setw",    "SETW (21.5°N, 123.25°E)",  "POINT = SETW",    21.5,   123.25),
    ("swtw",    "SWTW (21.5°N, 118.5°E)",   "POINT = SWTW",    21.5,   118.5),
]

# 仿 CWA 配色
YELLOW = "#fff200"
T_COLOR = "#1428d8"     # 溫度：藍
TD_COLOR = "#e8141e"    # 露點：紅
DRY = "#1f2fbf"         # 乾絕熱線：藍
MOIST = "#22a33a"       # 濕絕熱線：綠
MIX = "#000000"         # 混合比線：黑虛線
P_BOT, P_TOP = 1050, 100
T_LEFT, T_RIGHT = -20, 40
MANDATORY = [1000, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100]
Rd, G = 287.04, 9.80665


def open_points(path, **filt):
    ds = xr.open_dataset(path, engine="cfgrib",
                         backend_kwargs={"filter_by_keys": filt, "indexpath": ""})
    lats = xr.DataArray([s[3] for s in SITES], dims="site")
    lons = xr.DataArray([s[4] for s in SITES], dims="site")
    return ds.sel(latitude=lats, longitude=lons, method="nearest").load()


sfc_path = os.path.join(DATADIR, f"ifs_0p1_{DATE}00_sounding_sfc.grib2")
pl_path = os.path.join(DATADIR, f"ifs_0p1_{DATE}00_sounding_pl.grib2")
sp = open_points(sfc_path, shortName="sp")
s2 = open_points(sfc_path, typeOfLevel="heightAboveGround", level=2)
s10 = open_points(sfc_path, typeOfLevel="heightAboveGround", level=10)
pl = open_points(pl_path, typeOfLevel="isobaricInhPa")
init = np.datetime64(pl.time.values, "h")
steps_h = (pl.step.values / np.timedelta64(1, "h")).astype(int)
plev = pl.isobaricInhPa.values  # 1000 → 50


def sounding(i_site, i_step):
    """由地面往上: p(hPa), T, Td(°C), u, v(m/s), z(m, 離地高度)；另回傳氣壓層 gh。"""
    g = dict(site=i_site, step=i_step)
    psfc = float(sp.sp.isel(**g)) / 100.0
    t = pl.t.isel(**g).values - 273.15
    q = pl.q.isel(**g).values
    above = plev < psfc - 1.0
    td_pl = mpcalc.dewpoint_from_specific_humidity(
        plev[above] * units.hPa, q[above] * units("kg/kg")).to("degC").magnitude
    p = np.concatenate([[psfc], plev[above]])
    T = np.concatenate([[float(s2.t2m.isel(**g)) - 273.15], t[above]])
    Td = np.minimum(np.concatenate([[float(s2.d2m.isel(**g)) - 273.15], td_pl]), T)
    U = np.concatenate([[float(s10.u10.isel(**g))], pl.u.isel(**g).values[above]])
    V = np.concatenate([[float(s10.v10.isel(**g))], pl.v.isel(**g).values[above]])
    # 靜力方程積分離地高度
    Tk = T + 273.15
    z = np.concatenate([[0.0], np.cumsum(Rd * 0.5 * (Tk[:-1] + Tk[1:]) / G * np.log(p[:-1] / p[1:]))])
    gh = dict(zip(plev.astype(int), pl.gh.isel(**g).values))
    return p, T, Td, U, V, z, gh


def z_at(p_target, p, z):
    """在 log p 上內插高度 (km)。"""
    if p_target is None or not np.isfinite(p_target):
        return np.nan
    return float(np.interp(-np.log(p_target), -np.log(p), z)) / 1000.0


def compute_indices(p, T, Td, U, V, z):
    P, TT, TD = p * units.hPa, T * units.degC, Td * units.degC
    prof = mpcalc.parcel_profile(P, TT[0], TD[0]).to("degC")
    r = {}

    def grab(fn):
        try:
            out = fn()
            vals = [o.magnitude if hasattr(o, "magnitude") else o for o in out]
            return [float(np.atleast_1d(v)[0]) for v in vals]
        except Exception:
            return [np.nan, np.nan]

    r["lcl_p"], r["lcl_t"] = grab(lambda: mpcalc.lcl(P[0], TT[0], TD[0]))
    r["ccl_p"], r["ccl_t"] = grab(lambda: mpcalc.ccl(P, TT, TD)[:2])
    r["lfc_p"], r["lfc_t"] = grab(lambda: mpcalc.lfc(P, TT, TD, prof))
    r["el_p"], r["el_t"] = grab(lambda: mpcalc.el(P, TT, TD, prof))
    cape, cin = mpcalc.surface_based_cape_cin(P, TT, TD)
    r["cape"], r["cin"] = float(cape.magnitude), float(cin.magnitude)

    def one(fn):
        try:
            v = fn()
            return float(np.atleast_1d(v.magnitude)[0])
        except Exception:
            return np.nan
    r["ki"] = one(lambda: mpcalc.k_index(P, TT, TD))
    r["tt"] = one(lambda: mpcalc.total_totals_index(P, TT, TD))
    r["li"] = one(lambda: mpcalc.lifted_index(P, TT, prof))
    r["ssi"] = one(lambda: mpcalc.showalter_index(P, TT, TD))
    spd = mpcalc.wind_speed(U * units("m/s"), V * units("m/s"))
    wdir = mpcalc.wind_direction(U * units("m/s"), V * units("m/s"))
    r["sweat"] = one(lambda: mpcalc.sweat_index(P, TT, TD, spd, wdir))
    r["pw"] = one(lambda: mpcalc.precipitable_water(P, TD).to("mm"))
    for k in ("lcl", "ccl", "lfc", "el"):
        r[k + "_z"] = z_at(r[k + "_p"], p, z)
    return r, prof.magnitude


def f(v, fmt):
    return "   —" if v is None or not np.isfinite(v) else format(v, fmt)


def index_text(p, T, Td, r):
    lines = [
        rf"P$_o$={p[0]:.1f} T$_o$= {T[0]:.1f} Td$_o$= {Td[0]:.1f}",
        f"L.C.L.= {f(r['lcl_p'], '.0f')} hPa ({f(r['lcl_z'], '.3f')} km)",
        f"C.C.L.= {f(r['ccl_p'], '.0f')} hPa ({f(r['ccl_z'], '.3f')} km)",
        f"L.F.C.= {f(r['lfc_p'], '.0f')} hPa ({f(r['lfc_z'], '.3f')} km)",
        f"E.L.= {f(r['el_p'], '.0f')} hPa ({f(r['el_z'], '.3f')} km)",
        rf"T$_{{LCL}}$= {f(r['lcl_t'], '.1f')}$\degree$C  T$_{{CCL}}$= {f(r['ccl_t'], '.1f')}$\degree$C",
        rf"T$_{{LFC}}$= {f(r['lfc_t'], '.1f')}$\degree$C  T$_{{EL}}$= {f(r['el_t'], '.1f')}$\degree$C",
        f"K. INDX= {f(r['ki'], '.1f')}  TOTAL.= {f(r['tt'], '.1f')}",
        f"Lifted INDX. =  {f(r['li'], '.1f')}",
        f"Showalter INDX. =  {f(r['ssi'], '.1f')}",
        f"SWEAT INDX. =  {f(r['sweat'], '.1f')}",
        rf"CAPE  =  {f(r['cape'], '.1f')} m$^2$s$^{{-2}}$",
        rf"CIN   =  {f(abs(r['cin']), '.1f')} m$^2$s$^{{-2}}$",
        f"PW= {f(r['pw'], '.1f')} mm",
    ]
    return "\n".join(lines)


def plot(i_site, i_step):
    sid, name_zh, label, lat, lon = SITES[i_site]
    h = int(steps_h[i_step])
    valid = init + np.timedelta64(h, "h")
    p, T, Td, U, V, z, gh = sounding(i_site, i_step)
    r, prof = compute_indices(p, T, Td, U, V, z)

    fig = plt.figure(figsize=(9.6, 10.0), facecolor="white")
    skew = SkewT(fig, rotation=45, rect=(0.15, 0.13, 0.63, 0.80), aspect="auto")
    ax = skew.ax
    ax.set_ylim(P_BOT, P_TOP)
    ax.set_xlim(T_LEFT, T_RIGHT)
    ax.set_facecolor("white")
    for line in ax.get_xgridlines() + ax.get_ygridlines():
        line.set_visible(False)

    # 黃白相間的等溫帶 (每 10 °C 一組，黃 5 °C)
    for t0 in range(-150, 60, 10):
        ax.fill([t0, t0 + 5, t0 + 5, t0], [P_BOT + 50, P_BOT + 50, P_TOP - 10, P_TOP - 10],
                color=YELLOW, lw=0, zorder=0.2)

    # 等壓線
    for pm in MANDATORY:
        ax.axhline(pm, color="black", lw=0.7, zorder=1)

    # 乾絕熱線 (藍實線)、濕絕熱線 (綠)、混合比線 (黑虛線)
    skew.plot_dry_adiabats(t0=np.arange(-30, 200, 10) * units.degC,
                           pressure=np.linspace(P_BOT, P_TOP, 60) * units.hPa,
                           colors=DRY, linewidths=0.8, alpha=1, linestyles="-", zorder=1.2)
    skew.plot_moist_adiabats(t0=np.arange(-10, 45, 5) * units.degC,
                             pressure=np.linspace(P_BOT, 200, 60) * units.hPa,
                             colors=MOIST, linewidths=0.8, alpha=1, linestyles="-", zorder=1.2)
    w_vals = np.array([0.7, 1, 1.5, 2, 3, 4, 5, 7, 10, 15, 20, 25, 30])
    skew.plot_mixing_lines(mixing_ratio=(w_vals / 1000.0)[:, None] * units("kg/kg"),
                           pressure=np.linspace(P_BOT, 300, 2) * units.hPa,
                           colors=MIX, linewidths=0.7, alpha=0.9, linestyles=(0, (4, 3)),
                           zorder=1.3)
    # 混合比數值 (底部)
    for w in w_vals:
        tw = mpcalc.dewpoint(mpcalc.vapor_pressure(1030 * units.hPa, w / 1000.0 * units("kg/kg")))
        tw = tw.to("degC").magnitude
        if T_LEFT + 1 < tw + 0 and tw < T_RIGHT + 8:
            ax.text(tw, 1032, f"{w:g}", fontsize=9.5, ha="center", va="center", zorder=5)
    ax.text(T_RIGHT - 0.3, 1032, "g/kg", fontsize=9, ha="right", va="center", zorder=5)

    # 0 °C 等溫線加粗
    ax.axvline(0, color="black", lw=1.4, zorder=1.5)
    # 等溫線數值 (沿對角排列)
    for tl in range(-90, 40, 10):
        pl_ = 118 * (830 / 118) ** ((tl + 90) / 120)
        ax.text(tl, pl_, f"{tl}", fontsize=10.5, ha="center", va="center", zorder=5)

    # 氣塊路徑與正浮力區 (斜線)
    P = p * units.hPa
    m = prof >= T
    ax.fill_betweenx(p, T, prof, where=m, interpolate=True, facecolor="none",
                     edgecolor="black", hatch="----", lw=0, zorder=2)
    # 氣塊路徑只畫到平衡高度 (沒有 EL 時畫到 LCL)
    p_end = r["el_p"] if np.isfinite(r["el_p"]) else r["lcl_p"]
    seg = p >= (p_end if np.isfinite(p_end) else p[0])
    pp = np.linspace(p[0], p_end, 60) if np.isfinite(p_end) else p[seg]
    tp = mpcalc.parcel_profile(pp * units.hPa, T[0] * units.degC, Td[0] * units.degC).to("degC").magnitude
    ax.plot(tp, pp, color="black", lw=1.0, zorder=3)

    # 溫度 / 露點
    ax.plot(T, p, color=T_COLOR, lw=2.0, zorder=4)
    ax.plot(Td, p, color=TD_COLOR, lw=2.0, zorder=4)

    # 座標軸
    ax.yaxis.set_major_locator(FixedLocator(MANDATORY))
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.set_yticklabels([str(v) for v in MANDATORY])
    ax.set_xticks(range(T_LEFT, T_RIGHT + 1, 5))
    ax.tick_params(axis="both", labelsize=14, length=4)
    ax.tick_params(axis="x", labelsize=11)
    ax.set_ylabel("PRESSURE (mb)", fontsize=20, labelpad=8)
    ax.text(1.005, -0.006, "(°C)", transform=ax.transAxes, fontsize=11, va="top")

    # 右側高度 (km)
    axr = ax.twinx()
    axr.set_yscale("log")
    axr.set_ylim(P_BOT, P_TOP)
    axr.yaxis.set_major_locator(FixedLocator(MANDATORY))
    axr.yaxis.set_minor_locator(FixedLocator([]))
    axr.set_yticklabels([f"{gh.get(pm, np.nan) / 1000:.4g}" if pm <= p[0] else "" for pm in MANDATORY])
    axr.tick_params(labelsize=13, length=0, pad=6)
    axr.set_ylabel("HEIGHT (km)", fontsize=20, labelpad=10)
    for s in axr.spines.values():
        s.set_visible(False)

    # 指數框
    ax.text(0.687, 0.995, index_text(p, T, Td, r), transform=ax.transAxes, fontsize=10.3,
            va="top", ha="left", linespacing=1.18, zorder=10,
            bbox=dict(fc="white", ec="black", lw=0.8, pad=3))

    # 風欄
    axw = fig.add_axes([0.905, 0.13, 0.08, 0.80])
    axw.set_yscale("log")
    axw.set_ylim(P_BOT, P_TOP)
    axw.set_xlim(-1, 1)
    axw.axis("off")
    kt = 1 / 0.514444
    axw.plot([0, 0], [p[0], P_TOP], color="black", lw=0.8)
    axw.plot(np.zeros_like(p), p, "o", color="black", ms=2.2)
    axw.barbs(np.zeros_like(p), p, U * kt, V * kt, length=6.2, lw=0.8,
              barb_increments=dict(half=5, full=10, flag=50))
    axw.text(0, 1.012, "WIND", transform=axw.transAxes, ha="center", va="bottom", fontsize=12)

    # 標題 / 底部
    fig.text(0.18, 0.958, label, fontsize=17, va="bottom")
    fig.text(0.78, 0.958, f"{str(valid)[:10]} {str(valid)[11:13]}00 UTC", fontsize=17,
             va="bottom", ha="right")
    fig.text(0.465, 0.065, "SKEW T, log p DIAGRAM", fontsize=15, ha="center")
    fig.text(0.465, 0.03,
             f"ECMWF IFS 0.1° forecast  ·  Init {str(init)[:10]} {str(init)[11:13]}00 UTC  ·  +{h} h"
             f"  ·  {lat:.2f}N {lon:.2f}E",
             fontsize=11, ha="center", color="#444444")

    fig.savefig(os.path.join(OUTDIR, f"{sid}_f{h:03d}.png"), dpi=110, facecolor="white")
    plt.close(fig)


TXTDIR = os.path.join(OUTDIR, "txt")
os.makedirs(TXTDIR, exist_ok=True)


def edt_name(i_site, i_step):
    """仿 CWA 檔名: {站號或座標}-{有效時間 YYYYMMDDHH}.edt.txt"""
    label = SITES[i_site][2].split("=", 1)[1].strip().replace(" ", "")
    valid = (init + np.timedelta64(int(steps_h[i_step]), "h")).astype(dt.datetime)
    return f"{label}-{valid:%Y%m%d%H}.edt.txt"


def write_edt(i_site, i_step):
    """仿 CWA 探空文字檔 (.edt.txt)。Time / Height / Ascent 無資料填 NaN。
    第 1 列為有效時間 (UTC)，第 3 列為欄位名稱，CRLF 換行，最後一列無換行。"""
    p, T, Td, U, V, z, gh = sounding(i_site, i_step)
    rh = mpcalc.relative_humidity_from_dewpoint(T * units.degC, Td * units.degC).to("percent").magnitude
    ws = np.hypot(U, V)
    wd = mpcalc.wind_direction(U * units("m/s"), V * units("m/s")).to("degree").magnitude
    valid = (init + np.timedelta64(int(steps_h[i_step]), "h")).astype(dt.datetime)
    hour12 = valid.hour % 12 or 12
    ampm = "AM" if valid.hour < 12 else "PM"
    lines = [f"Start time:      {valid.month}/{valid.day}/{valid.year} "
             f"{hour12}:{valid.minute:02d}:{valid.second:02d} {ampm}",
             "",
             "Time\t  Height\t       P\t       T\t       U\t      WS\t      WD\t  Ascent"]
    for k in range(len(p)):
        lines.append("{:>4},\t{:>8},\t{:>8.1f},\t{:>8.1f},\t{:>8.1f},\t{:>8.1f},\t{:>8.1f},\t{:>8}".format(
            "NaN", "NaN", p[k], T[k], min(rh[k], 100.0), ws[k], wd[k], "NaN"))
    path = os.path.join(TXTDIR, edt_name(i_site, i_step))
    with open(path, "w", encoding="ascii", newline="") as fh:
        fh.write("\r\n".join(lines))
    return os.path.basename(path)


only = os.environ.get("ONLY")
for i_site in range(len(SITES)):
    for i_step in range(len(steps_h)):
        if only and (i_site, i_step) != tuple(map(int, only.split(","))):
            continue
        if os.environ.get("TXT_ONLY") != "1":
            plot(i_site, i_step)
        write_edt(i_site, i_step)
        print(SITES[i_site][0], f"f{int(steps_h[i_step]):03d} done")

meta = {"init": f"{DATE}00", "steps": [int(h) for h in steps_h],
        "sites": [{"id": s[0], "name": s[1], "lat": s[3], "lon": s[4],
                   "txt": {str(int(h)): edt_name(i, j) for j, h in enumerate(steps_h)}}
                  for i, s in enumerate(SITES)]}
with open(os.path.join(OUTDIR, "sounding_meta.json"), "w", encoding="utf-8") as fh:
    json.dump(meta, fh, ensure_ascii=False, indent=1)
print("Soundings saved to", OUTDIR)

# 畫完後刪除原始 GRIB2 以節省空間 (測試模式 ONLY 或 KEEP_GRIB=1 時保留)
if not only and os.environ.get("KEEP_GRIB") != "1":
    for _f in (sfc_path, pl_path):
        if os.path.exists(_f):
            os.remove(_f)
            print("Deleted", _f)
