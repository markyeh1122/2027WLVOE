"""把 figures/{DATE}/ 的圖轉成 WebP 放到 site/runs/{DATE}00/，並重建 site/index.html。

用法:
  python3 build_site.py 20261113      加入 / 更新這一報
  python3 build_site.py               只重建網頁 (不轉圖)

網站結構:
  site/index.html            完整網頁 (可直接開啟或放到靜態網頁空間)
  site/artifact.html         給 Claude Artifact 發佈用
  site/runs/{YYYYMMDDHH}/manifest.json
  site/runs/{YYYYMMDDHH}/img/{mslp,850,mslp_s,850_s,sounding}/*.webp
網頁的「初始時間」選單會列出 site/runs/ 底下所有的報。

保留規則 (以網站上最新一報為基準，可用環境變數調整)：
  KEEP_FULL=14  最近 14 天保留完整內容
  KEEP_LITE=30  之後 30 天只留比較圖 (含初始場)、探空圖與文字檔 (刪掉其餘動畫圖)，再舊的整報刪除
  (GitHub Actions 上設為 KEEP_FULL=7、KEEP_LITE=365，見 .github/workflows/daily.yml)
  --run-only    只轉圖不重建網頁 (GitHub Actions 平行產圖用)
"""
import datetime as dt
import glob
import json
import os
import re
import shutil
import sys
import zipfile


HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(HERE, "site")
TEMPLATE = os.path.join(HERE, "site_template.html")

PRODUCTS = {"mslp": "mslp_10m", "850": "850hPa",                  # 風羽
            "mslp_s": "mslp_10m_stream", "850_s": "850hPa_stream"}  # 流線
COMPARE_LEADS = [24, 48, 72, 96, 120]
KEEP_FULL = int(os.environ.get("KEEP_FULL", 14))
KEEP_LITE = int(os.environ.get("KEEP_LITE", 30))


def to_webp(src, dst, q=88):
    from PIL import Image
    Image.open(src).convert("RGB").save(dst, quality=q, method=6)


def add_run(date):
    figdir = os.path.join(HERE, "figures", date)
    run = f"{date}00"
    rundir = os.path.join(SITE, "runs", run)
    steps = None
    for key, sub in PRODUCTS.items():
        outdir = os.path.join(rundir, "img", key)
        os.makedirs(outdir, exist_ok=True)
        for old in glob.glob(os.path.join(outdir, "*.webp")):
            os.remove(old)
        s = []
        for f in sorted(glob.glob(os.path.join(figdir, sub, "*.png"))):
            h = int(re.search(r"_f(\d{3})\.png$", f).group(1))
            to_webp(f, os.path.join(outdir, f"f{h:03d}.webp"))
            s.append(h)
        steps = s if steps is None else sorted(set(steps) & set(s))
        print(f"{run} {key}: {len(s)} frames")

    sounding = None
    meta = os.path.join(figdir, "sounding", "sounding_meta.json")
    if os.path.exists(meta):
        outdir = os.path.join(rundir, "img", "sounding")
        os.makedirs(outdir, exist_ok=True)
        for old in glob.glob(os.path.join(outdir, "*.webp")):
            os.remove(old)
        for f in sorted(glob.glob(os.path.join(figdir, "sounding", "*.png"))):
            to_webp(f, os.path.join(outdir, os.path.basename(f)[:-4] + ".webp"), q=90)
        with open(meta, encoding="utf-8") as fh:
            sounding = json.load(fh)
        # 探空文字檔 (.edt.txt) 與整報打包 zip
        txts = sorted(glob.glob(os.path.join(figdir, "sounding", "txt", "*.edt.txt")))
        if txts:
            txtdir = os.path.join(rundir, "txt")
            os.makedirs(txtdir, exist_ok=True)
            for old in glob.glob(os.path.join(txtdir, "*")):
                os.remove(old)
            zname = f"ECMWF_IFS_sounding_{run}.zip"
            with zipfile.ZipFile(os.path.join(txtdir, zname), "w", zipfile.ZIP_DEFLATED) as zf:
                for t in txts:
                    shutil.copy2(t, txtdir)
                    zf.write(t, os.path.basename(t))
            sounding["zip"] = zname
            print(f"{run} sounding txt: {len(txts)} files + {zname}")
        print(f"{run} sounding: {len(sounding['sites'])} sites x {len(sounding['steps'])} times")

    # 逐 run 比較：有效時間 = 本報初始時間 的前幾報預報 (compare_runs.py 準備的圖)
    compare = []
    t0 = dt.datetime.strptime(date, "%Y%m%d")
    for lead in COMPARE_LEADS:
        old = (t0 - dt.timedelta(hours=lead)).strftime("%Y%m%d")
        srcs = {key: os.path.join(HERE, "figures", old, sub, f"{sub}_{old}00_f{lead:03d}.png")
                for key, sub in PRODUCTS.items()}
        if not all(os.path.exists(s) for s in srcs.values()):
            continue
        for key, src in srcs.items():
            outdir = os.path.join(rundir, "cmp", key)
            os.makedirs(outdir, exist_ok=True)
            to_webp(src, os.path.join(outdir, f"{old}00_f{lead:03d}.webp"))
        compare.append({"init": f"{old}00", "lead": lead})
    print(f"{run} compare: " + ", ".join(f"{c['init']}+{c['lead']}h" for c in compare))

    with open(os.path.join(rundir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump({"init": run, "steps": steps, "sounding": sounding, "compare": compare},
                  fh, ensure_ascii=False)


def prune():
    """依保留規則把舊報改成精簡版或刪除。"""
    runs = sorted(os.path.basename(d) for d in glob.glob(os.path.join(SITE, "runs", "??????????")))
    if not runs:
        return
    newest = dt.datetime.strptime(runs[-1], "%Y%m%d%H")
    for run in runs:
        rundir = os.path.join(SITE, "runs", run)
        age = (newest - dt.datetime.strptime(run, "%Y%m%d%H")).days
        if age >= KEEP_FULL + KEEP_LITE:
            shutil.rmtree(rundir)
            print(f"{run}: 刪除 ({age} 天前)")
        elif age >= KEEP_FULL:
            mf = os.path.join(rundir, "manifest.json")
            with open(mf, encoding="utf-8") as fh:
                m = json.load(fh)
            if m.get("lite"):
                continue
            for key in PRODUCTS:  # 刪掉動畫圖，但保留初始場 f000 給逐 run 比較的「分析場」
                for f in glob.glob(os.path.join(rundir, "img", key, "*.webp")):
                    if os.path.basename(f) != "f000.webp":
                        os.remove(f)
            m.update(lite=True, steps=[])
            with open(mf, "w", encoding="utf-8") as fh:
                json.dump(m, fh, ensure_ascii=False)
            print(f"{run}: 改為精簡版 ({age} 天前)")


def build_html():
    runs = []
    for m in sorted(glob.glob(os.path.join(SITE, "runs", "*", "manifest.json")), reverse=True):
        with open(m, encoding="utf-8") as fh:
            runs.append(json.load(fh))
    with open(TEMPLATE, encoding="utf-8") as fh:
        html = fh.read().replace("/*__MANIFEST__*/null",
                                 json.dumps({"runs": runs}, ensure_ascii=False))
    if not os.environ.get("GITHUB_ACTIONS"):
        with open(os.path.join(SITE, "artifact.html"), "w", encoding="utf-8") as fh:
            fh.write(html)
    open(os.path.join(SITE, ".nojekyll"), "w").close()
    with open(os.path.join(SITE, "index.html"), "w", encoding="utf-8") as fh:
        fh.write('<!doctype html>\n<html lang="zh-Hant">\n<head>\n<meta charset="utf-8">\n'
                 '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                 '<style>body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>\n'
                 '</head>\n<body>\n' + html + '\n</body>\n</html>\n')
    print("Runs on site:", ", ".join(r["init"] for r in runs))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        add_run(sys.argv[1])
        if "--run-only" in sys.argv:
            sys.exit()
    prune()
    build_html()
