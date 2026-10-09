from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.auth import CurrentUser
from app.templating import render

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def index(request: Request, me: CurrentUser):
    return render(request, "index.html", me=me)
