"""Fill in the song previews (猜歌對戰) that seed_demo skipped because iTunes was refusing requests.

Updates both demo.seed.db (the snapshot reset_demo restores) and demo.db, then downloads the new
preview files into demo_assets. Safe to run again: songs already checked are skipped. Stop the demo
server first. Needs the network.
Usage: .venv\\Scripts\\python.exe -m scripts.fill_previews
"""

import asyncio
import sqlite3
from datetime import datetime, timezone

from app.services import itunes
from scripts import cache_covers, demo_db

PAUSE = 2.0  # seconds between songs; iTunes allows roughly 20 searches a minute
GIVE_UP_AFTER = 3  # refusals in a row: iTunes is still blocking, try again later


def _now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S.%f")


async def main() -> None:
    dbs = [db for db in (demo_db.SNAPSHOT, demo_db.DEMO_DB) if db.exists()]
    if not dbs:
        print("找不到 demo.seed.db / demo.db，請先執行 python -m scripts.seed_demo")
        return
    with sqlite3.connect(dbs[0]) as con:
        todo = con.execute("SELECT id, creator, title FROM work WHERE category = 'music' "
                           "AND preview_checked_at IS NULL ORDER BY id").fetchall()
    print(f"{len(todo)} 首歌還沒有試聽資料")
    found = refused = 0
    for n, (work_id, creator, title) in enumerate(todo, 1):
        try:
            url = await itunes.find_preview(creator or "", title)
        except itunes.ItunesUnavailable as e:
            refused += 1
            print(f"  iTunes 拒絕：{title}（{e}）")
            if refused >= GIVE_UP_AFTER:
                print(f"⚠ iTunes 還在封鎖，已處理 {n - refused} 首、剩 {len(todo) - n + refused} 首。過 30 分鐘以上再執行一次。")
                break
            await asyncio.sleep(15)
            continue
        refused = 0
        found += bool(url)
        for db in dbs:
            with sqlite3.connect(db) as con:
                con.execute("UPDATE work SET preview_url = ?, preview_checked_at = ? WHERE id = ?", (url, _now(), work_id))
        if n % 20 == 0:
            print(f"  {n}/{len(todo)}…", flush=True)
        await asyncio.sleep(PAUSE)
    print(f"新找到 {found} 首的試聽")
    got, had, failed = await cache_covers.download(cache_covers.collect_urls(dbs[-1]), cache_covers.DEFAULT_DIR)
    print(f"demo_assets：新下載 {got} 個檔案，{had} 個本來就有，{len(failed)} 個失敗")


if __name__ == "__main__":
    asyncio.run(main())
