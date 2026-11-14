"""繪製 ECMWF IFS 0.1° 預報圖：21–26N, 118–125E
  1) 海平面氣壓 (hPa) + 10 m 風 (knots, 風羽)
  2) 850 hPa 重力位高度 (gpm) + 風 (knots, 風羽)
每個預報時間各一張。

用法: python3 plot_ecmwf.py [YYYYMMDD]
"""
import os
import sys
import datetime as dt

import numpy as np
import xarray as xr
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.colors import LinearSegmentedColormap, BoundaryNorm
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from cartopy.mpl.ticker import LongitudeFormatter, LatitudeFormatter

DATE = sys.argv[1] if len(sys.argv) > 1 else dt.datetime.utcnow().strftime("%Y%m%d")
HERE = os.path.dirname(os.path.abspath(__file__))
DATADIR = os.path.join(HERE, "data", DATE)
OUTDIR = os.path.join(HERE, "figures", DATE)
# 風羽版: mslp_10m/, 850hPa/   流線版: mslp_10m_stream/, 850hPa_stream/
for _d in ("mslp_10m", "850hPa", "mslp_10m_stream", "850hPa_stream"):
    os.makedirs(os.path.join(OUTDIR, _d), exist_ok=True)

LAT0, LAT1, LON0, LON1 = 21, 26, 118, 125
MS2KT = 1.0 / 0.514444
BARB_SKIP = 2          # 0.1° 網格每 2 點一支風羽 (約 0.2°)
STREAM_DENSITY = 2.4  # 流線密度
TPE = np.timedelta64(8, "h")

# ---- 樣式 ----
INK = "#1d2b3a"        # 標題、等值線
MUTED = "#5b6b7b"      # 次要文字
FRAME = "#a9b4bf"      # 外框
LEVELS = [0, 2, 4, 6, 8, 10, 12, 15, 20, 25, 30, 35]
CMAP = LinearSegmentedColormap.from_list(
    "wspd", ["#f7fbf6", "#e3f1df", "#c9e6c4", "#a9d8c2", "#8ccbc8",
             "#72b7d3", "#5e9fcb", "#4f84bd", "#4b68a8", "#4d5197"], N=256)
CMAP.set_over("#4a3d7d")
NORM = BoundaryNorm(LEVELS, CMAP.N, extend="max")


def open_grib(path, **filt):
    ds = xr.open_dataset(path, engine="cfgrib",
                         backend_kwargs={"filter_by_keys": filt, "indexpath": ""})
    # 緯度遞減排列，用 slice(高, 低)；加 0.01 容差避免浮點誤差漏掉邊界格點
    eps = 0.01
    if "step" not in ds.dims:  # 只下載單一時次時，補上 step 維度
        ds = ds.expand_dims("step")
    return ds.sel(latitude=slice(LAT1 + eps, LAT0 - eps),
                  longitude=slice(LON0 - eps, LON1 + eps)).load()


_sfc_path = os.path.join(DATADIR, f"ifs_0p1_{DATE}00_sfc.grib2")
sfc = xr.merge([open_grib(_sfc_path, shortName="msl"),
                open_grib(_sfc_path, typeOfLevel="heightAboveGround", level=10)],
               compat="override")
pl = open_grib(os.path.join(DATADIR, f"ifs_0p1_{DATE}00_pl850.grib2"),
               typeOfLevel="isobaricInhPa")

lon, lat = sfc.longitude.values, sfc.latitude.values
init = np.datetime64(sfc.time.values, "h")


def fmt_utc(t):
    return str(t)[:13].replace("T", " ") + "Z"


def make_figure(field, u, v, step, title, interval, unit, cbar_label, outpath,
                style="barb", wind_name="wind"):
    wspd = np.hypot(u, v) * MS2KT
    valid = init + np.timedelta64(int(step), "h")
    local = (valid + TPE).astype(dt.datetime)

    fig = plt.figure(figsize=(10.5, 9.6), facecolor="white")
    ax = fig.add_axes([0.10, 0.20, 0.80, 0.63], projection=ccrs.PlateCarree())
    ax.set_extent([LON0, LON1, LAT0, LAT1], crs=ccrs.PlateCarree())
    ax.spines["geo"].set_edgecolor(FRAME)
    ax.spines["geo"].set_linewidth(1.0)

    # 風速底色 (格點色塊)
    pm = ax.pcolormesh(lon, lat, wspd, cmap=CMAP, norm=NORM, shading="nearest",
                       transform=ccrs.PlateCarree(), zorder=1)

    # 海岸線：深色粗線 + 白色外框，在藍綠底色上也清楚
    ax.add_feature(cfeature.COASTLINE.with_scale("10m"), edgecolor="#111111",
                   linewidth=1.3, zorder=4.5,
                   path_effects=[pe.withStroke(linewidth=2.8, foreground="white")])
    ax.gridlines(linewidth=0.4, color="#9aa6b2", alpha=0.35, linestyle=":",
                 xlocs=range(LON0, LON1 + 1), ylocs=range(LAT0, LAT1 + 1), zorder=2)

    # 等值線
    lo = np.floor(np.nanmin(field) / interval) * interval
    hi = np.ceil(np.nanmax(field) / interval) * interval
    cs = ax.contour(lon, lat, field, levels=np.arange(lo, hi + interval, interval),
                    colors=INK, linewidths=1.1 if style == "barb" else 1.6, transform=ccrs.PlateCarree(), zorder=4)
    labels = ax.clabel(cs, fmt="%d", fontsize=10, inline=True, inline_spacing=4)
    for t in labels:
        t.set_color(INK)
        t.set_path_effects([pe.withStroke(linewidth=3, foreground="white")])

    if style == "barb":
        # 風羽
        s = slice(None, None, BARB_SKIP)
        ax.barbs(lon[s], lat[s], u[s, s] * MS2KT, v[s, s] * MS2KT,
                 length=4.6, linewidth=0.55, color=INK, zorder=5,
                 sizes=dict(emptybarb=0.12, spacing=0.18, height=0.45),
                 barb_increments=dict(half=5, full=10, flag=50),
                 transform=ccrs.PlateCarree())
    else:
        # 流線 (streamplot 需要緯度遞增，所以翻轉)
        ax.streamplot(lon, lat[::-1], u[::-1], v[::-1], density=STREAM_DENSITY,
                      color="#4a6680", linewidth=0.7, arrowsize=0.9, arrowstyle="->",
                      minlength=0.08, maxlength=6.0, zorder=5,
                      transform=ccrs.PlateCarree())

    # 座標軸刻度
    ax.set_xticks(range(LON0, LON1 + 1), crs=ccrs.PlateCarree())
    ax.set_yticks(range(LAT0, LAT1 + 1), crs=ccrs.PlateCarree())
    ax.xaxis.set_major_formatter(LongitudeFormatter())
    ax.yaxis.set_major_formatter(LatitudeFormatter())
    ax.tick_params(labelsize=11, colors=INK, length=4, color=FRAME)

    # 標題區
    x0 = ax.get_position().x0
    fig.text(x0, 0.975, title, fontsize=24, fontweight="bold", color=INK, va="top")
    fig.text(x0, 0.922,
             f"Valid {fmt_utc(valid)}  |  {local:%m/%d %H:%M} Taipei time",
             fontsize=14, color=INK, va="top")
    fig.text(x0, 0.888,
             f"ECMWF IFS 0.1°  ·  Init {fmt_utc(init)}  ·  +{int(step)} h",
             fontsize=11.5, color=MUTED, va="top")

    # 水平色標
    pos = ax.get_position()
    cax = fig.add_axes([pos.x0, 0.118, pos.width, 0.021])
    cb = fig.colorbar(pm, cax=cax, orientation="horizontal", ticks=LEVELS,
                      extend="max", extendfrac=0.05, spacing="uniform")
    cb.outline.set_edgecolor(FRAME)
    cb.ax.tick_params(labelsize=11, colors=INK, length=0)
    cb.set_label(cbar_label, fontsize=12, color=INK)

    # 註腳
    fig.text(pos.x0, 0.050, f"Contours every {interval} {unit}",
             fontsize=11.5, color=INK, va="top")
    foot = ("Wind barbs (kt)   ·   Half 5    Full 10    Flag 50" if style == "barb"
            else f"Streamlines: {wind_name}   ·   Shading: wind speed (kt)")
    fig.text(pos.x0, 0.024, foot, fontsize=11.5, color=INK, va="top")

    fig.savefig(outpath, dpi=120, facecolor="white")
    plt.close(fig)


steps_h = (sfc.step.values / np.timedelta64(1, "h")).astype(int)
for i, h in enumerate(steps_h):
    msl = sfc.msl.isel(step=i).values / 100.0
    u10, v10 = sfc.u10.isel(step=i).values, sfc.v10.isel(step=i).values
    gh = pl.gh.isel(step=i).values
    u8, v8 = pl.u.isel(step=i).values, pl.v.isel(step=i).values
    for style, sfx, w in (("barb", "", "wind"), ("stream", "_stream", "streamlines")):
        make_figure(msl, u10, v10, h, f"MSLP and 10 m {w}", 1, "hPa", "Wind speed (kt)",
                    os.path.join(OUTDIR, f"mslp_10m{sfx}", f"mslp_10m{sfx}_{DATE}00_f{h:03d}.png"),
                    style=style, wind_name="10 m wind")
        make_figure(gh, u8, v8, h, f"850 hPa height and {w}", 10, "gpm", "Wind speed (kt)",
                    os.path.join(OUTDIR, f"850hPa{sfx}", f"850hPa{sfx}_{DATE}00_f{h:03d}.png"),
                    style=style, wind_name="850 hPa wind")
    print(f"f{h:03d} done")

print("Figures saved to", OUTDIR)

# 畫完後刪除原始 GRIB2 以節省空間 (要保留請設 KEEP_GRIB=1)
if os.environ.get("KEEP_GRIB") != "1":
    for _f in (_sfc_path, os.path.join(DATADIR, f"ifs_0p1_{DATE}00_pl850.grib2")):
        if os.path.exists(_f):
            os.remove(_f)
            print("Deleted", _f)
