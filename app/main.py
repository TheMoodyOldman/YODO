from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.auth import LoginRequired
from app.config import settings
from app.db import init_db
from app.routers import auth, card, lastfm, me, music, pages, profile, steam, work, youtube

BASE_DIR = Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="友多聞 YODO", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site="lax")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.include_router(pages.router)
app.include_router(auth.router)
app.include_router(me.router)
app.include_router(steam.router)
app.include_router(youtube.router)
app.include_router(lastfm.router)
app.include_router(music.router)
app.include_router(card.router)
app.include_router(profile.router)
app.include_router(work.router)


@app.middleware("http")
async def no_stale_pages(request: Request, call_next):
    """Pages change with every save; make browsers revalidate instead of showing a cached copy."""
    response = await call_next(request)
    if response.headers.get("content-type", "").startswith("text/html") and "cache-control" not in response.headers:
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.exception_handler(LoginRequired)
async def login_required_handler(request: Request, exc: LoginRequired):
    return RedirectResponse(f"/login?next={quote(request.url.path)}", status_code=303)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
