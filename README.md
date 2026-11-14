# 2027冬季背風渦旋觀測實驗 — ECMWF IFS 0.1° 短期預報網站

每天 UTC 09:00 由 GitHub Actions 自動下載 ECMWF IFS 0.1° 00Z 預報 (Google Cloud open data)，
繪製 21–26°N、118–125°E 的天氣圖動畫、5 個點的預報探空與逐 run 比較，發佈到 GitHub Pages。

| 程式 | 用途 |
|---|---|
| `download_ecmwf.py` | 下載 MSLP、10 m 風、850 hPa 高度與風 (0–120 h，每 3 h) |
| `download_sounding.py` | 下載探空用多層資料 (0/24/…/120 h) |
| `plot_ecmwf.py` | 畫天氣圖 (風羽版與流線版)，畫完刪除 GRIB2 |
| `plot_sounding.py` | 畫 Skew-T 探空圖並輸出 `.edt.txt` |
| `compare_runs.py` | 準備前 24–120 h 各報在本報初始時間的預報圖 |
| `build_site.py` | 轉成 WebP、套用保留規則、產生 `site/index.html` |

- 手動補跑：Actions → Daily forecast → Run workflow，輸入日期 (YYYYMMDD)。
- 保留規則：最近 14 天完整，之後 30 天只留比較圖與探空 (`KEEP_FULL` / `KEEP_LITE`)。
- 本機執行：`conda env create -f environment.yml`，依上表順序執行，再 `python3 build_site.py YYYYMMDD`。
