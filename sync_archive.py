"""把 GitHub Releases 上的完整封存下載到本機 archive/ (每天由 launchd 自動執行)。

每次執行都會比對 Releases 清單與本機資料夾，把還沒下載的報全部補齊，
所以筆電幾天沒開也不會漏。只用 Python 標準函式庫，不需要登入 GitHub。

用法: python3 sync_archive.py
輸出: ~/2027WLVOE_archive/{YYYYMMDDHH}/ (桌面 2027WLVOE/archive 是它的捷徑)
       (img/、cmp/、txt/、manifest.json)
      archive/sync.log      執行紀錄
"""
import datetime as dt
import json
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile

REPO = "markyeh1122/2027WLVOE"
HERE = os.path.dirname(os.path.abspath(__file__))
# launchd 排程無法讀寫「桌面」(macOS 隱私保護)，所以實際存在家目錄，桌面資料夾內的 archive 是捷徑
ARCHIVE = os.environ.get("WLVOE_ARCHIVE", os.path.expanduser("~/2027WLVOE_archive"))
UA = {"User-Agent": "forecast-archive-sync", "Accept": "application/vnd.github+json"}


def log(msg):
    line = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(line)
    with open(os.path.join(ARCHIVE, "sync.log"), "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def get_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.load(r)


def releases():
    page, out = 1, []
    while True:
        batch = get_json(f"https://api.github.com/repos/{REPO}/releases?per_page=100&page={page}")
        out += batch
        if len(batch) < 100:
            return out
        page += 1


def safe_extract(zpath, run):
    """解壓到 archive/{run}/，只接受該報資料夾底下的檔案。"""
    tmp = tempfile.mkdtemp(dir=ARCHIVE, prefix=".tmp-")
    try:
        with zipfile.ZipFile(zpath) as zf:
            for m in zf.namelist():
                parts = m.replace("\\", "/").split("/")
                if parts[0] != run or ".." in parts or m.startswith("/"):
                    raise ValueError(f"zip 內有不預期的路徑: {m}")
            zf.extractall(tmp)
        dst = os.path.join(ARCHIVE, run)
        if os.path.exists(dst):
            shutil.rmtree(dst)
        os.replace(os.path.join(tmp, run), dst)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    os.makedirs(ARCHIVE, exist_ok=True)
    try:
        rels = releases()
    except Exception as e:  # 沒網路等情況：記錄後結束，下次再補
        log(f"無法取得 Releases 清單：{e}")
        return 1
    new = 0
    for rel in sorted(rels, key=lambda r: r["tag_name"]):
        tag = rel["tag_name"]
        if not tag.startswith("run-"):
            continue
        run = tag[4:]
        if os.path.exists(os.path.join(ARCHIVE, run, "manifest.json")):
            continue
        asset = next((a for a in rel.get("assets", []) if a["name"].endswith("_full.zip")), None)
        if not asset:
            continue
        zpath = os.path.join(ARCHIVE, f".{asset['name']}")
        try:
            req = urllib.request.Request(asset["browser_download_url"], headers={"User-Agent": UA["User-Agent"]})
            with urllib.request.urlopen(req, timeout=300) as r, open(zpath, "wb") as fh:
                shutil.copyfileobj(r, fh)
            safe_extract(zpath, run)
            new += 1
            log(f"{run}: 已下載 ({asset['size'] / 1e6:.0f} MB)")
        except Exception as e:
            log(f"{run}: 下載失敗，下次再試 ({e})")
        finally:
            if os.path.exists(zpath):
                os.remove(zpath)
    log(f"完成：新增 {new} 報，本機共 {sum(1 for d in os.listdir(ARCHIVE) if d.isdigit())} 報")
    return 0


if __name__ == "__main__":
    sys.exit(main())
