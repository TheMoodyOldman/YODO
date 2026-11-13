import os
import pathlib
import sqlite3
from datetime import date, datetime, timedelta

db = pathlib.Path(__file__).parent / "test_age.db"
db.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"

from fastapi.testclient import TestClient  # noqa: E402

from app.auth import age_on, hash_password  # noqa: E402
from app.importers.youtube import TAIPEI  # noqa: E402
from app.main import app  # noqa: E402

today = datetime.now(TAIPEI).date()


def years_ago(n: int, extra_days: int = 0) -> str:
    try:
        d = today.replace(year=today.year - n)
    except ValueError:
        d = today.replace(year=today.year - n, day=28)
    return (d + timedelta(days=extra_days)).isoformat()


def check(label, cond):
    print(("PASS " if cond else "FAIL ") + label)


def q(sql, *args):
    con = sqlite3.connect(db)
    try:
        r = con.execute(sql, args).fetchall()
        con.commit()
        return r
    finally:
        con.close()


def reg(client, name, birth):
    return client.post("/register", data={"username": name, "email": str(name).lower() + "@test.yodo", "password": "testpass123", "birth_date": birth})


check("age math: birthday today counts", age_on(date(2000, 10, 10), date(2018, 10, 10)) == 18)
check("age math: day before birthday doesn't", age_on(date(2000, 10, 10), date(2018, 10, 9)) == 17)
check("age math: Feb 29 birthday", age_on(date(2004, 2, 29), date(2022, 2, 28)) == 17 and age_on(date(2004, 2, 29), date(2022, 3, 1)) == 18)

with TestClient(app) as c1, TestClient(app) as c2, TestClient(app) as c3, TestClient(app) as legacy, TestClient(app) as kid, TestClient(app) as anon:
    r = anon.get("/register")
    check("sign-up form has birth date with 18-year max", 'name="birth_date"' in r.text and f'max="{years_ago(18)}"' in r.text and "僅限 18 歲以上" in r.text)
    check("landing page states 18+", "僅限 18 歲以上使用" in anon.get("/").text)

    r = c1.post("/register", data={"username": "nobirth", "email": str("nobirth").lower() + "@test.yodo", "password": "testpass123"})
    check("birth date required", r.status_code == 400 and "請填寫出生日期" in r.text)
    r = reg(c1, "teen", years_ago(18, 1))
    check("one day short of 18 refused", r.status_code == 400 and "僅限 18 歲以上使用" in r.text)
    check("refused sign-up stores nothing", q("SELECT COUNT(*) FROM user")[0][0] == 0)
    check("future date refused", "看起來不對" in reg(c1, "future", (today + timedelta(days=1)).isoformat()).text)
    check("garbage refused", "請填寫出生日期" in reg(c1, "garbage", "not-a-date").text)
    r = reg(c2, "adult", years_ago(18))
    check("18th birthday today accepted", r.status_code == 200 and str(r.url).endswith("/me/collection"))
    check("birth date stored, never shown", q("SELECT birth_date FROM user WHERE username='adult'")[0][0] == years_ago(18)
          and years_ago(18) not in anon.get("/u/adult").text)

    # Accounts from before the age check
    for name in ("oldie", "minor"):
        q("INSERT INTO user (username, display_name, password_hash, bio, created_at) VALUES (?, ?, ?, '', ?)",
          name, name.title(), hash_password("testpass123"), datetime.now().isoformat())
    legacy.post("/login", data={"username": "oldie", "password": "testpass123"})
    r = legacy.get("/feed", follow_redirects=False)
    check("legacy account asked for birth date", r.status_code == 303 and r.headers["location"] == "/me/age?next=/feed")
    check("other pages gated too", legacy.get("/u/adult", follow_redirects=False).headers["location"].startswith("/me/age"))
    r = legacy.post("/me/collection/anime", data={"anilist_id": "1"}, follow_redirects=False)
    check("POSTs gated without a next", r.headers["location"] == "/me/age")
    r = legacy.post("/me/age", data={"birth_date": years_ago(30), "next": "/feed"}, follow_redirects=False)
    check("adult confirmation returns to next", r.headers["location"] == "/feed")
    check("then the site works", legacy.get("/feed").status_code == 200)
    check("age form skipped once answered", legacy.get("/me/age", follow_redirects=False).status_code == 303)

    kid.post("/login", data={"username": "minor", "password": "testpass123"})
    r = kid.post("/me/age", data={"birth_date": years_ago(16)})
    check("under-18 legacy user signed out", r.status_code == 403 and "暫時無法使用" in r.text and "帳號和收藏資料都還在" in r.text)
    check("session cleared", kid.get("/me/collection", follow_redirects=False).headers["location"].startswith("/login"))
    r = kid.post("/login", data={"username": "minor", "password": "testpass123"})
    check("locked account can't log in", r.status_code == 400 and "未滿 18 歲" in r.text)
    check("locked account's page hidden", anon.get("/u/minor").status_code == 404)
    c3.post("/register", data={"username": "finder", "email": str("finder").lower() + "@test.yodo", "password": "testpass123", "birth_date": years_ago(25)})
    check("locked account not in search", "@minor" not in c3.get("/me/friends", params={"q": "min"}).text)
    check("can't re-answer to get in", kid.get("/me/age", follow_redirects=False).headers["location"] == "/login")
