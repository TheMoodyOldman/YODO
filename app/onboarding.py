"""新手教學: the getting-started steps. Each step ticks itself off from the user's real data, so
there is nothing to keep in sync. The same steps drive two views:

- the checklist card on 動態 / 收藏 / your profile (can be hidden, reopened from 設定)
- the interactive tour (static/js/tour.js): a forced start-or-skip dialog on first visit, then a
  floating card that highlights the button to press on each page, with slide transitions."""

from dataclasses import asdict, dataclass

from sqlmodel import Session, col, func, or_, select

from app.models import CollectionEntry, Friendship, Message, Post, Review, User

COLLECT_GOAL = 3
TOUR_STATES = ("active", "done", "skipped")


@dataclass
class Step:
    key: str
    title: str
    text: str
    href: str
    action: str
    done: bool
    # tour: what to highlight (first selector found wins) and how to explain it
    targets: tuple[str, ...] = ()
    hint: str = ""
    progress: str = ""


def _count(session: Session, query) -> int:
    return session.exec(query).one()


def steps(session: Session, user: User) -> list[Step]:
    entries = _count(session, select(func.count()).select_from(CollectionEntry).where(
        CollectionEntry.user_id == user.id, col(CollectionEntry.pending_review).is_(False)))
    friends = _count(session, select(func.count()).select_from(Friendship).where(
        or_(Friendship.requester_id == user.id, Friendship.addressee_id == user.id)))
    posted = _count(session, select(func.count()).select_from(Review).where(Review.user_id == user.id)) + \
        _count(session, select(func.count()).select_from(Post).where(Post.user_id == user.id))
    messaged = _count(session, select(func.count()).select_from(Message).where(Message.sender_id == user.id))
    return [
        Step("photo", "放一張照片", "第一張會變成你的大頭照，推薦卡片也會用它。", "/me/photos", "上傳照片",
             user.avatar_photo_id is not None,
             targets=(".photo-slot.add",), hint="點這個「＋」選一張照片，選好就會自動上傳。"),
        Step("profile", "寫一句自我介紹", "填上自介和地區，讓同好知道怎麼開話題。", "/me/settings", "編輯資料",
             bool(user.bio or user.region),
             targets=('textarea[name="bio"]',), hint="寫一句自我介紹、選你的地區，再按最下面的「儲存」。"),
        Step("collect", f"加入 {COLLECT_GOAL} 個收藏", "同步 Steam、匯入音樂，或搜尋動畫、影視、書籍加入。", "/me/collection#anime", "去加收藏",
             entries >= COLLECT_GOAL,
             targets=('[data-panel="anime"] .search input',),
             hint="搜尋一部喜歡的動畫（中文、英文、日文都可以），按「加入」再選評價。也可以切到其他分頁同步遊戲或音樂。",
             progress=f"已加入 {min(entries, COLLECT_GOAL)} / {COLLECT_GOAL} 個收藏"),
        Step("friend", "認識一位同好", "到探索看看品味相近或新加入的人，按 ♥ 送出好友邀請。", "/match", "去探索",
             friends >= 1,
             targets=(".match-card .round-btn.like", '[data-tour="newcomer-add"]'),
             hint="看到喜歡的人就按 ♥ 送出好友邀請；人還不多時，下面會列出新加入的同好。"),
        Step("talk", "說點什麼", "寫一則短評、貼一張便利貼，或傳訊息給朋友。", "/discuss", "去討論區",
             posted + messaged >= 1,
             targets=(".new-note summary",), hint="打開「貼一張便利貼」，選分類、寫一句話再按「貼上」。"),
    ]


def card(session: Session, user: User) -> list[Step] | None:
    """Checklist steps to show, or None when the card is hidden, the tour is running, or all is done."""
    if user.onboarding_hidden or user.tour_state == "active":
        return None
    items = steps(session, user)
    return None if all(s.done for s in items) else items


def tour_payload(session: Session, user: User) -> dict | None:
    """Data for tour.js: offered once (state None) and while active."""
    if user.tour_state not in (None, "active"):
        return None
    items = steps(session, user)
    if user.tour_state is None and all(s.done for s in items):
        return None  # nothing left to teach
    return {
        "state": user.tour_state,
        "name": user.display_name,
        "steps": [{k: v for k, v in asdict(s).items() if k in ("key", "title", "href", "done", "targets", "hint", "progress")}
                  for s in items],
    }
