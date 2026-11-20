"""The demo's fake people (scripts.seed_demo + scripts.demo_people): checked without building demo.db
or using the network."""

import os
import pathlib
import re

db = pathlib.Path(__file__).parent / "test_demo_people.db"
db.unlink(missing_ok=True)
os.environ["BACKGROUND_JOBS"] = "false"
os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"

from app import contacts  # noqa: E402
from app.anime import BookStatus, TAGS_BY_CATEGORY, TIER_LABELS  # noqa: E402
from app.matching import LOOKING_LABELS, REGIONS  # noqa: E402
from app.models import Category, Visibility  # noqa: E402
from app.routers.me import MAX_BIO  # noqa: E402
from scripts import demo_people as dp  # noqa: E402
from scripts import seed_demo as s  # noqa: E402


def check(label, cond):
    print(("PASS " if cond else "FAIL ") + label)


names = [p[0] for p in s.FAKE_PEOPLE]
check("24 fake people: the original 4 plus 20 more", len(names) == 24)
check("usernames unique, all demo_ (so remove_demo_people and the snapshot check cover them)",
      len(set(names)) == len(names) and all(n.startswith("demo_") for n in names))
check("display names unique", len({p[1] for p in s.FAKE_PEOPLE}) == len(s.FAKE_PEOPLE))
check("every region is one the settings page offers", all(p[3] in REGIONS for p in s.FAKE_PEOPLE))
check("only 小雨 and 阿哲 are demo's friends", [p[0] for p in s.FAKE_PEOPLE if p[4]] == ["demo_rain", "demo_zhe"])
demo_anime = {q for q, _ in s.DEMO_ANIME}
check("shared ratings only use demo's anime and real tiers",
      all(q in demo_anime and t in TIER_LABELS for p in s.FAKE_PEOPLE for q, t in p[6].items()))
check("everyone says what they're looking for, with real options",
      set(s.LOOKING) == set(names) and all(k in LOOKING_LABELS for v in s.LOOKING.values() for k in v.split(",")))
check("friend requests come from strangers, not existing friends",
      set(s.REQUESTS_TO_DEMO) <= set(names) and not set(s.REQUESTS_TO_DEMO) & {p[0] for p in s.FAKE_PEOPLE if p[4]})
check("every fake person can log in with the demo password", s.LOGIN_PEOPLE == set(names))

# ---------- profiles and collections
P = dp.PROFILES
check("every fake person has a profile, and only they do", set(P) == set(names))
check("bios fit the 200-character limit and say more than the old one-liners",
      all(40 <= len(p["bio"]) <= MAX_BIO for p in P.values()))
check("contacts are valid LINE / Discord / Instagram handles",
      all(k in contacts.BY_KEY and contacts.BY_KEY[k].pattern.fullmatch(v) for p in P.values() for k, v in p["contacts"].items()))
check("everyone leaves at least one contact for friends", all(p["contacts"] for p in P.values()))
check("privacy uses real categories and visibilities",
      all(Category(c) and Visibility(v) for p in P.values() for c, v in p["privacy"].items()))
check("photo palettes are two hex colours", all(len(p["palette"]) == 2 and all(re.fullmatch(r"#[0-9a-f]{6}", c)
      for c in p["palette"]) for p in P.values()))
check("everyone has all five categories", all(p[k] for p in P.values() for k in ("anime", "films", "books", "games", "songs")))
tiers = set(TIER_LABELS)
check("anime: known titles, real tiers and anime tags",
      all(k in dp.ANIME and t in tiers and (g is None or g in TAGS_BY_CATEGORY[Category.anime]) for p in P.values() for k, t, g in p["anime"]))
check("films: known TMDB ids, real tiers and film tags",
      all(k in dp.FILMS and t in tiers and (g is None or g in TAGS_BY_CATEGORY[Category.film]) for p in P.values() for k, t, g in p["films"]))
check("books: known titles, reading status, tiers and book tags",
      all(k in dp.BOOKS and BookStatus(st) and (t is None or t in tiers) and (g is None or g in TAGS_BY_CATEGORY[Category.book])
          for p in P.values() for k, st, t, g in p["books"]))
check("games: known appids, hours this month never more than the total",
      all(a in dp.GAMES and 0 <= this <= total for p in P.values() for a, total, this in p["games"]))
check("songs: artist, title, two months of plays",
      all(len(t) == 4 and t[0] and t[1] and t[2] >= 0 and t[3] >= 0 for p in P.values() for t in p["songs"]))
check("no duplicates inside one person's lists",
      all(len({x[0] for x in p[k]}) == len(p[k]) for p in P.values() for k in ("anime", "films", "books", "games"))
      and all(len({(a, t) for a, t, *_ in p["songs"]}) == len(p["songs"]) for p in P.values()))
check("no two people have the same anime, the same games or the same songs",
      all(len({frozenset(x[0] for x in p[k]) for p in P.values()}) == len(P) for k in ("anime", "games"))
      and len({frozenset((a, t) for a, t, *_ in p["songs"]) for p in P.values()}) == len(P))
total = sum(len(p[k]) for p in P.values() for k in ("anime", "films", "books", "games", "songs"))
check(f"collections are much fuller than before ({total} items in all)", total >= 300)

# ---------- 30+ per category (demo_people.plan)
CATS = ("anime", "films", "books", "games", "songs")
TAG_CAT = {"anime": Category.anime, "films": Category.film, "books": Category.book}
plans = {u: dp.plan(u) for u in P}
check("everyone has a taste profile", set(dp.TASTES) == set(P)
      and all(set(t) == set(CATS) | {"extra"} for t in dp.TASTES.values()))
check("taste styles exist in the pools",
      all(style in pool for t in dp.TASTES.values() for c, pool in (("anime", dp.ANIME_POOL), ("films", dp.FILM_POOL),
          ("books", dp.BOOK_POOL), ("games", dp.GAME_POOL), ("songs", dp.SONG_POOL)) for style in t[c]))
check(f"every person has at least {dp.MIN_PER_CATEGORY} in every category",
      dp.MIN_PER_CATEGORY >= 30 and all(len(pl[c]) >= dp.MIN_PER_CATEGORY for pl in plans.values() for c in CATS))
check("plans are the same on every run", all(dp.plan(u) == plans[u] for u in list(P)[:5]))
check("hand-picked favourites come first",
      all(plans[u]["songs"][:len(p["songs"])] == list(p["songs"]) and len(plans[u]["anime"]) > len(p["anime"]) for u, p in P.items()))
check("generated tiers and tags are real and fit the category",
      all((t is None or t in tiers) and (g is None or g in TAGS_BY_CATEGORY[TAG_CAT[c]])
          for pl in plans.values() for c in TAG_CAT for *_, t, g in pl[c]))
check("generated books have a real status, and 'want' has no rating",
      all(BookStatus(st) and (st != "want" or (t is None and g is None)) for pl in plans.values() for _, st, t, g in pl["books"]))
check("generated games: hours this month never more than the total",
      all(0 <= this <= total for pl in plans.values() for _, total, this in pl["games"]))
check("generated songs: artist, title, two months of plays",
      all(len(x) == 4 and x[0] and x[1] and x[2] >= 0 and x[3] >= 1 for pl in plans.values() for x in pl["songs"][5:]))
check("no duplicates in any plan",
      all(len({repr(x[0]) for x in pl[c]}) == len(pl[c]) for pl in plans.values() for c in ("anime", "films", "books", "games"))
      and all(len({x[:2] for x in pl["songs"]}) == len(pl["songs"]) for pl in plans.values()))
check("no two people have the same collection in any category",
      all(len({frozenset(repr(x[:2]) for x in pl[c]) for pl in plans.values()}) == len(P) for c in CATS))
check("spare items never repeat the plan (used when a lookup finds nothing)",
      all(not {repr(x[0]) for x in dp.spare(u, c)} & {repr(x[0]) for x in plans[u][c]}
          for u in list(P)[:6] for c in ("anime", "films", "books")))
big = sum(len(pl[c]) for pl in plans.values() for c in CATS)
check(f"about {big} items in all", big >= 24 * 5 * 30)
