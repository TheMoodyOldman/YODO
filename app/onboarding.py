"""新手教學: a getting-started checklist. Each step ticks itself off from the user's real data, so
there is nothing to keep in sync; the user can hide the card and bring it back from 設定."""

from dataclasses import dataclass

from sqlmodel import Session, col, func, or_, select

from app.models import CollectionEntry, Friendship, Message, Post, Review, User


@dataclass
class Step:
    key: str
    title: str
    text: str
    href: str
    action: str
    done: bool


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
             user.avatar_photo_id is not None),
        Step("profile", "寫一句自我介紹", "填上自介和地區，讓同好知道怎麼開話題。", "/me/settings", "編輯資料",
             bool(user.bio or user.region)),
        Step("collect", "加入 3 個收藏", "同步 Steam、匯入音樂，或搜尋動畫、影視、書籍加入。", "/me/collection", "去加收藏",
             entries >= 3),
        Step("friend", "認識一位同好", "到探索看看品味相近的人，按 ♥ 送出好友邀請。", "/match", "去探索",
             friends >= 1),
        Step("talk", "說點什麼", "寫一則短評、貼一張便利貼，或傳訊息給朋友。", "/discuss", "去討論區",
             posted + messaged >= 1),
    ]


def card(session: Session, user: User) -> list[Step] | None:
    """Steps to show, or None when the card is hidden or everything is done."""
    if user.onboarding_hidden:
        return None
    items = steps(session, user)
    return None if all(s.done for s in items) else items
