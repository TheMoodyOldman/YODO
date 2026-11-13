import json
import os
import pathlib
import re
import sqlite3
import sys
import time

here = pathlib.Path(__file__).parent
db = here / "test_yt.db"
db.unlink(missing_ok=True)

# Simulate a database created before this change: work table without "creator".
con = sqlite3.connect(db)
con.execute("CREATE TABLE work (id INTEGER PRIMARY KEY, category VARCHAR(5) NOT NULL, source VARCHAR NOT NULL, "
            "external_id VARCHAR NOT NULL, title VARCHAR NOT NULL, original_title VARCHAR, cover_url VARCHAR, year INTEGER)")
con.execute("INSERT INTO work (category, source, external_id, title) VALUES ('anime', 'anilist', '1', 'Old Anime')")
con.commit()
con.close()
os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"

from fastapi.testclient import TestClient  # noqa: E402

from app.importers.youtube import parse_watch_history  # noqa: E402
from app.main import app  # noqa: E402

# Optional: a real Google Takeout export (YouTube 和 YouTube Music folder), as two file arguments or
# YODO_TAKEOUT_DIR. Without it the real-file checks are skipped; the synthetic ones always run.
_takeout = os.environ.get("YODO_TAKEOUT_DIR")
if len(sys.argv) > 2:
    HISTORY, LIBRARY = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
elif _takeout:
    HISTORY = pathlib.Path(_takeout) / "觀看記錄" / "watch-history.json"
    LIBRARY = pathlib.Path(_takeout) / "music (library and uploads)" / "music library songs.csv"
else:
    HISTORY = LIBRARY = None


def check(label, cond):
    print(("PASS " if cond else "FAIL ") + label)


def item(vid, title, channel, t, header="YouTube Music"):
    host = "music.youtube.com" if header == "YouTube Music" else "www.youtube.com"
    return {"header": header, "title": f"Watched {title}", "titleUrl": f"https://{host}/watch?v={vid}",
            "subtitles": [{"name": channel, "url": "https://www.youtube.com/channel/x"}], "time": t,
            "products": ["YouTube"]}


def up(client, history=None, library=None):
    files = {}
    if history is not None:
        files["history"] = ("watch-history.json", history, "application/json")
    if library is not None:
        files["library"] = ("music library songs.csv", library, "text/csv")
    return client.post("/me/youtube/import", files=files)


with TestClient(app) as alice, TestClient(app) as anon:
    con = sqlite3.connect(db)
    cols = [r[1] for r in con.execute("PRAGMA table_info(work)")]
    check("migration added work.creator, kept old rows",
          "creator" in cols and con.execute("SELECT title FROM work").fetchone()[0] == "Old Anime")
    con.close()

    alice.post("/register", data={"username": "alice", "email": str("alice").lower() + "@test.yodo", "password": "testpass123", "birth_date": "2000-01-01"})

    # --- format errors
    r = up(alice, history=b"<html><body>watch history</body></html>")
    check("HTML history rejected with JSON hint", "改成 JSON" in r.text)
    r = up(alice, history=b"not json at all")
    check("garbage history rejected", "無法讀取觀看紀錄" in r.text)
    r = up(alice, library=b"just,one\nrow,here")
    check("bad CSV rejected", "無法讀取音樂收藏" in r.text)
    r = alice.post("/me/youtube/import", files={"history": ("", b"", "application/octet-stream")})
    check("empty submit asks for a file", "請選擇要上傳的檔案" in r.text)
    only_videos = json.dumps([item("aaaaaaaaaaa", "Cat video", "Some Vlogger", "2026-09-01T00:00:00Z", header="YouTube")])
    r = up(alice, history=only_videos.encode())
    check("history without music -> nothing found", "沒有找到音樂" in r.text)

    # --- synthetic data: filtering, month bucketing (Taipei), XSS title
    xss = "Evil');alert(1);//"
    synth = [
        item("AAAAAAAAAA1", "Song A", "Band X - Topic", "2026-09-30T17:00:00Z", header="YouTube"),  # Oct 1 in Taipei
        item("AAAAAAAAAA1", "Song A", "Band X - Topic", "2026-09-10T00:00:00Z"),
        item("AAAAAAAAAA1", "Song A", "Band X - Topic", "2026-09-11T00:00:00Z"),
        item("BBBBBBBBBB2", xss, "band x - Topic", "2026-09-12T00:00:00Z"),
        item("CCCCCCCCCC3", "Song C", "Solo Y - Topic", "2026-09-12T00:00:00Z"),
        item("DDDDDDDDDD4", "Secret vlog", "Private Channel", "2026-09-12T00:00:00Z", header="YouTube"),
    ]
    parsed = parse_watch_history(json.dumps(synth).encode())
    check("non-music video dropped by parser", "DDDDDDDDDD4" not in parsed.tracks and parsed.skipped == 1)
    check("UTC->Taipei month bucketing", parsed.plays[("AAAAAAAAAA1", "2026-10")] == 1 and parsed.plays[("AAAAAAAAAA1", "2026-09")] == 2)

    r = up(alice, history=json.dumps(synth).encode())
    check("synthetic import -> review", str(r.url).endswith("/me/music/review") and "新增 3 首歌" in r.text)
    check("artists grouped case-insensitively", "4 次播放 · 2 首歌" in r.text)
    check("XSS title escaped on review page", "alert(1);//" in r.text and "<script>alert" not in r.text)

    # hide artist "Solo Y" (uncheck), keep Band X; keep all songs
    artist_keys = re.findall(r'name="listed_artist" value="([^"]+)"', r.text)
    song_ids = re.findall(r'name="listed_song" value="(\d+)"', r.text)
    form = {"listed_artist": artist_keys, "artist": [k for k in artist_keys if k != "solo y"],
            "listed_song": song_ids, "song": song_ids}
    r = alice.post("/me/music/review", data=form)
    check("review: unchecked artist hidden", "隱藏了 1 首歌" in r.text)
    page = anon.get("/u/alice").text
    check("profile shows rankings", "最常聽的歌手" in page and "最常聽的歌曲" in page)
    check("hidden artist not on profile", "Solo Y" not in page and "Song C" not in page)
    check("top song first with play count", page.index("Song A") < page.index("Evil") and "3 次" in page)
    check("non-music title never stored", "Secret vlog" not in alice.get("/me/collection").text)

    r = alice.get("/me/collection")
    check("collection delete-confirm uses data attribute",
          "confirm(this.dataset.confirm)" in r.text and "confirm('從收藏移除" not in r.text)

    # --- re-import overlapping export: max per month, no double count
    r = up(alice, history=json.dumps(synth).encode())
    check("re-import same file: no new songs", "沒有新的歌曲" in r.text and "共 5 次播放" in r.text)
    newer = synth + [item("AAAAAAAAAA1", "Song A", "Band X - Topic", "2026-09-20T00:00:00Z")]
    r = up(alice, history=json.dumps(newer).encode())
    check("newer export raises month count by one", "共 6 次播放" in r.text)

    r = alice.post("/me/youtube/clear")
    check("clear removes songs", "已刪除 3 首" in r.text)
    check("profile empty after clear", "Song A" not in anon.get("/u/alice").text)

    # --- real Takeout files (optional)
    if HISTORY is None:
        print("SKIP real Takeout files (set YODO_TAKEOUT_DIR to run them)")
    else:
        t0 = time.perf_counter()
        r = up(alice, history=HISTORY.read_bytes(), library=LIBRARY.read_bytes())
        elapsed = time.perf_counter() - t0
        m = re.search(r"匯入完成：(\d+) 首有播放紀錄，共 (\d+) 次播放。新增 (\d+) 首歌", r.text)
        check(f"real files imported in {elapsed:.1f}s -> review", m is not None and str(r.url).endswith("/me/music/review"))
        if m:
            print(f"     songs with plays={m.group(1)} total plays={m.group(2)} new songs={m.group(3)}")
        n_artists = len(re.findall(r'name="listed_artist"', r.text))
        n_songs = len(re.findall(r'name="listed_song"', r.text))
        check(f"review lists top {n_artists} artists / {n_songs} songs", n_artists == 15 and n_songs == 20)
        ids = re.findall(r'name="listed_song" value="(\d+)"', r.text)
        keys = re.findall(r'name="listed_artist" value="([^"]+)"', r.text)
        alice.post("/me/music/review", data={"listed_artist": keys, "artist": keys, "listed_song": ids, "song": ids})

        t0 = time.perf_counter()
        r = alice.get("/me/collection")
        check(f"collection page caps music list ({time.perf_counter() - t0:.2f}s)",
              r.text.count('class="thumb entry-cover square"') == 50 and "顯示全部" in r.text)
        t0 = time.perf_counter()
        page = anon.get("/u/alice").text
        check(f"profile renders 10+10 rankings ({time.perf_counter() - t0:.2f}s)", page.split('data-panel="music"')[1].count('class="rank"') == 20)
        r = up(alice, history=HISTORY.read_bytes(), library=LIBRARY.read_bytes())
        check("re-importing real files is idempotent", "沒有新的歌曲" in r.text and m and f"共 {m.group(2)} 次播放" in r.text)
