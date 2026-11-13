import os
import pathlib
import re

db = pathlib.Path(__file__).parent / "test_anime.db"
db.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"

from fastapi.testclient import TestClient  # noqa: E402

import app.routers.me as me_router  # noqa: E402
from app.main import app  # noqa: E402
from app.services import anilist  # noqa: E402

FAKE = {i: anilist.Anime(i, f"Show {i}", None, None, 2020, "TV") for i in range(1, 8)}


async def fake_get(anilist_id):
    return FAKE.get(anilist_id)


async def fake_search(text):
    return list(FAKE.values())


anilist.get_anime = fake_get
anilist.search_anime = fake_search
me_router.anilist.get_anime = fake_get
me_router.anilist.search_anime = fake_search


def check(label, cond):
    print(("PASS " if cond else "FAIL ") + label)


def entry_ids(html):
    return dict(re.findall(r'id="entry-(\d+)".*?class="card-title" href="[^"]+">([^<]+)</a>', html, re.S))


with TestClient(app) as alice, TestClient(app) as anon:
    alice.post("/register", data={"username": "alice", "email": str("alice").lower() + "@test.yodo", "password": "testpass123", "birth_date": "2000-01-01"})
    for i in FAKE:
        alice.post("/me/collection/anime", data={"anilist_id": str(i)})
    r = alice.get("/me/collection#anime")
    ids = {title: eid for eid, title in entry_ids(r.text).items()}
    check("7 anime added", len(ids) == 7)
    check("anime rows offer a 評價 button + chip dialog, no stars",
          r.text.count("data-rate data-category=\"anime\"") == 7 and 'class="chip"' in r.text and 'name="rating"' not in r.text)

    verdicts = {"Show 1": ("okay", ""), "Show 2": ("must_watch", "神作"), "Show 3": ("dropped", "廁紙"),
                "Show 4": ("great", "胃痛"), "Show 5": ("bad", "崩"), "Show 6": ("good", "我看了什麼")}
    for title, (tier, tag) in verdicts.items():
        alice.post(f"/me/collection/{ids[title]}/verdict", data={"tier": tier, "tag": tag})
    r = alice.post(f"/me/collection/{ids['Show 7']}/verdict", data={"tier": "legendary", "tag": "<script>"})
    page = alice.get("/me/collection").text
    check("invalid tier/tag ignored, no stars on anime", "#&lt;script" not in page and "legendary" not in page and "★" not in page)

    order = list(entry_ids(page).values())
    check("collection anime sorted by tier", order == ["Show 2", "Show 4", "Show 6", "Show 1", "Show 5", "Show 3", "Show 7"])

    prof = anon.get("/u/alice").text
    overview = prof.split('data-panel="overview"')[1].split('data-panel="anime"')[0]
    over_titles = re.findall(r'<div class="card-title">([^<]+)</div>', overview)  # cards on the profile
    check("profile overview sorted best first", over_titles[:3] == ["Show 2", "Show 4", "Show 6"])
    panel = prof.split('data-panel="anime"')[1]
    headings = re.findall(r'<h3 class="tier-heading">([^<]+?) <', panel)
    check("anime tab grouped by tier, unrated last", headings == ["此生必看", "大推", "還不錯", "普通", "雷", "已棄坑", "未評價"])
    check("tier badge + tag chip rendered", 'class="tier tier-must_watch">此生必看</span>' in prof and "#神作" in prof and "#廁紙" in prof)

    # clearing a verdict
    alice.post(f"/me/collection/{ids['Show 2']}/verdict", data={"tier": "", "tag": ""})
    prof = anon.get("/u/alice").text
    check("clearing tier moves it to 未評價", "此生必看" not in prof.split('data-panel="anime"')[1])

    # recap card ordering follows tiers
    from app.cards import Period, recap_stats
    from app.db import engine
    from app.models import User
    from sqlmodel import Session, select
    with Session(engine) as s:
        u = s.exec(select(User).where(User.username == "alice")).one()
        st = recap_stats(s, u, Period("all", "all"))
        check("recap anime ordered by tier", [w.title for _, w in st.anime][:3] == ["Show 4", "Show 6", "Show 1"])

    # rename + Recap button
    check("site renamed", "<title>alice 的興趣名片 · 友多聞 YODO</title>" in prof and "HsingCode" not in prof)
    check("brand shows 友多聞 YODO", '<span class="brand-zh">友多聞</span> <span class="brand-en">YODO</span>' in prof)
    check("button text is 製作我的 Recap", "製作我的 Recap" in alice.get("/u/alice").text)
