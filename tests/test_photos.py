import io
import os
import pathlib

here = pathlib.Path(__file__).parent
db = here / "test_photos.db"
db.unlink(missing_ok=True)
os.environ["BACKGROUND_JOBS"] = "false"
os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User, UserPhoto  # noqa: E402

fails = 0


def check(name, ok, extra=""):
    global fails
    print(("PASS " if ok else "FAIL ") + name + (f"  {extra}" if extra and not ok else ""))
    fails += 0 if ok else 1


def image(fmt="JPEG", size=(1200, 900), color=(200, 80, 160), exif=False):
    img = Image.new("RGB", size, color)
    out = io.BytesIO()
    if exif:
        ex = Image.Exif()
        ex[0x8825] = {2: (25.0, 2.0, 0.0)}  # GPS IFD
        ex[0x0112] = 6  # orientation: rotate 90°
        img.save(out, fmt, exif=ex)
    else:
        img.save(out, fmt)
    return out.getvalue()


def client(name):
    c = TestClient(app)
    c.post("/register", data={"username": name, "email": str(name).lower() + "@test.yodo", "password": "testpass123", "birth_date": "2000-01-01"})
    return c


def avatar_id(name):
    with Session(engine) as s:
        return s.exec(select(User).where(User.username == name)).one().avatar_photo_id


def photo_ids(name):
    with Session(engine) as s:
        uid = s.exec(select(User).where(User.username == name)).one().id
        return [p.id for p in s.exec(select(UserPhoto).where(UserPhoto.user_id == uid).order_by(UserPhoto.position))]


with TestClient(app):
    alice, bob, anon = client("alice"), client("bob"), TestClient(app)

    page = alice.get("/me/photos").text
    check("photo page with add slot", "新增照片" in page and 'name="photo"' in page)
    check("photos page needs login", "/login" in str(anon.get("/me/photos").url))

    r = alice.post("/me/photos", files={"photo": ("a.jpg", image(exif=True), "image/jpeg")})
    check("upload jpeg", "已新增照片" in r.text, r.text[:200])
    first = photo_ids("alice")[0]
    check("first photo becomes avatar", avatar_id("alice") == first)
    served = anon.get(f"/photos/{first}")
    out = Image.open(io.BytesIO(served.content))
    check("served as 4:5 jpeg", served.headers["content-type"] == "image/jpeg" and out.size == (960, 1200))
    check("EXIF (GPS) stripped", not out.getexif())
    check("cacheable", "max-age" in served.headers.get("cache-control", ""))

    alice.post("/me/photos", files={"photo": ("b.png", image("PNG", color=(10, 200, 90)), "image/png")})
    alice.post("/me/photos", files={"photo": ("c.webp", image("WEBP"), "image/webp")})
    alice.post("/me/photos", files={"photo": ("d.jpg", image(), "image/jpeg")})
    check("four photos stored", len(photo_ids("alice")) == 4)
    r = alice.post("/me/photos", files={"photo": ("e.jpg", image(), "image/jpeg")})
    check("fifth rejected", "最多 4 張照片" in r.text and len(photo_ids("alice")) == 4)
    check("no add slot when full", 'name="photo"' not in alice.get("/me/photos").text)

    ids = photo_ids("alice")
    alice.post(f"/me/photos/{ids[2]}/first")
    check("make first reorders and updates avatar", photo_ids("alice")[0] == ids[2] and avatar_id("alice") == ids[2])
    alice.post(f"/me/photos/{ids[2]}/delete")
    check("deleting the avatar promotes the next photo", avatar_id("alice") == photo_ids("alice")[0] and len(photo_ids("alice")) == 3)
    check("can't delete someone else's photo", bob.post(f"/me/photos/{ids[0]}/delete").status_code == 404)
    check("deleted photo 404", anon.get(f"/photos/{ids[2]}").status_code == 404)

    bob.post("/me/photos", files={"photo": ("t.jpg", image(size=(200, 200)), "image/jpeg")})
    check("too small rejected", not photo_ids("bob"))
    r = bob.post("/me/photos", files={"photo": ("x.txt", b"not an image", "text/plain")})
    check("non-image rejected", "讀不懂這張圖片" in r.text and not photo_ids("bob"))
    r = bob.post("/me/photos", files={"photo": ("x.bmp", image("BMP"), "image/bmp")})
    check("unsupported format explained", "只支援 JPG、PNG、WebP" in r.text)

    prof = anon.get("/u/alice").text
    check("profile hero shows photos with carousel", prof.count('src="/photos/') >= 3 and "data-carousel" in prof and "hero-dots" in prof)
    check("visitors don't get the edit button", "編輯照片" not in prof)
    check("owner gets the edit button", "編輯照片" in alice.get("/u/alice").text)
    check("no-photo profile shows initial", "hero-initial" in anon.get("/u/bob").text)
    check("nav avatar uses photo", f'class="nav-avatar" src="/photos/{avatar_id("alice")}"' in alice.get("/feed").text)

    bob.post("/friends/alice/block")
    check("blocked users can't load photos", bob.get(f"/photos/{avatar_id('alice')}").status_code == 404)
    check("owner still loads own photo", alice.get(f"/photos/{avatar_id('alice')}").status_code == 200)

print("TOTAL FAIL", fails)
try:
    db.unlink(missing_ok=True)
except PermissionError:
    pass
