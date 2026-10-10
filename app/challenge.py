"""30 天挑戰: one prompt a day, answered with a work from your own collection."""

from datetime import date, datetime

from sqlmodel import Session, col, select

from app.importers.youtube import TAIPEI
from app.models import Category, Challenge, ChallengePick, CollectionEntry, User, Work

DAYS = 30

TITLES = {
    Category.music: "30 天歌曲挑戰",
    Category.anime: "30 天動畫挑戰",
    Category.game: "30 天遊戲挑戰",
}

PROMPTS: dict[Category, list[str]] = {
    Category.music: [
        "你現在最愛的歌", "歌名有數字的歌", "讓你想起夏天的歌", "讓你想起某個人的歌", "聽了就想跳舞的歌",
        "適合通勤時聽的歌", "最近單曲循環的歌", "第一首會唱的動畫歌", "心情不好時會聽的歌", "讓你起雞皮疙瘩的歌",
        "小時候常聽的歌", "最喜歡的翻唱", "冷門但值得被聽見的歌", "適合下雨天聽的歌", "讀書或工作時聽的歌",
        "歌名只有一個字的歌", "想在 KTV 點的歌", "前奏一下就認得的歌", "演唱會最想聽現場的歌", "聽到會哭的歌",
        "讓你想起某部作品的歌", "一首外語歌", "最近才認識的新歌", "睡前會聽的歌", "會讓你想運動的歌",
        "歌詞很有共鳴的歌", "不好意思承認你喜歡的歌", "想推薦給朋友的歌", "讓你想起某個地方的歌", "這個月的主題曲",
    ],
    Category.anime: [
        "入坑的第一部動畫", "現在最愛的動畫", "哭最慘的一部", "最好笑的一部", "最被低估的一部",
        "最想住進去的世界", "作畫最驚豔的一部", "OP 最好聽的一部", "結局最難忘的一部", "看過兩次以上的一部",
        "最想推給新人的一部", "讓你 #胃痛 的一部", "最熱血的一部", "最療癒的一部", "讓你想去聖地巡禮的一部",
        "最好的原創動畫", "最喜歡的劇場版", "最燒腦的一部", "最喜歡的運動番", "戀愛線最甜的一部",
        "反轉最多的一部", "一口氣追完的一部", "最想看續集的一部", "配樂最好聽的一部", "小時候看的一部",
        "最想失憶再看一次的一部", "大家都推但你還沒愛上的一部", "跟朋友一起追過的一部", "世界觀最完整的一部", "你的年度動畫",
    ],
    Category.game: [
        "入坑的第一款遊戲", "現在最常玩的遊戲", "玩最久的遊戲", "最難的遊戲", "最想失憶重玩一次的遊戲",
        "劇情最好的遊戲", "配樂最好的遊戲", "畫面最美的遊戲", "最療癒的遊戲", "最適合跟朋友玩的遊戲",
        "讓你熬夜的遊戲", "最被低估的遊戲", "最想推給新手的遊戲", "讓你想摔手把的遊戲", "最喜歡的獨立遊戲",
        "小時候玩的遊戲", "最想住進去的遊戲世界", "角色塑造最好的遊戲", "買了還沒玩的遊戲", "最燒腦的遊戲",
        "最有成就感的一次通關", "最喜歡的開放世界", "最想看動畫化的遊戲", "玩到哭的遊戲", "最常重開的遊戲",
        "最喜歡的多人遊戲", "解最多成就的遊戲", "最想看續作的遊戲", "最有創意的遊戲", "你的年度遊戲",
    ],
}
assert all(len(p) == DAYS for p in PROMPTS.values())


def parse_kind(value: str) -> Category | None:
    return next((c for c in Category if c.value == value), None)


def today() -> date:
    return datetime.now(TAIPEI).date()


def unlocked_days(ch: Challenge) -> int:
    """Days 1..N are open: day 1 on the start date, one more each day after."""
    return max(0, min(DAYS, (today() - ch.started_on).days + 1))


def get_challenge(session: Session, user: User, kind: Category) -> Challenge | None:
    return session.exec(select(Challenge).where(Challenge.user_id == user.id, Challenge.kind == kind.value)).first()


def picks(session: Session, ch: Challenge) -> dict[int, Work]:
    rows = session.exec(
        select(ChallengePick.day, Work)
        .join(Work, col(Work.id) == ChallengePick.work_id)
        .where(ChallengePick.challenge_id == ch.id)
    ).all()
    return dict(rows)


def owned_entry(session: Session, user: User, kind: Category, work_id: int) -> CollectionEntry | None:
    """Picks must come from the user's own collection (not awaiting import review)."""
    return session.exec(
        select(CollectionEntry)
        .join(Work, col(Work.id) == CollectionEntry.work_id)
        .where(
            CollectionEntry.user_id == user.id,
            CollectionEntry.work_id == work_id,
            Work.category == kind,
            col(CollectionEntry.pending_review).is_(False),
        )
    ).first()


def search_collection(session: Session, user: User, kind: Category, q: str, limit: int = 40) -> list[tuple[CollectionEntry, Work]]:
    query = (
        select(CollectionEntry, Work)
        .join(Work, col(Work.id) == CollectionEntry.work_id)
        .where(CollectionEntry.user_id == user.id, Work.category == kind, col(CollectionEntry.pending_review).is_(False))
    )
    rows = list(session.exec(query).all())
    if q := q.strip().casefold():
        rows = [r for r in rows if q in r[1].title.casefold() or q in (r[1].creator or "").casefold()
                or q in (r[1].original_title or "").casefold()]
    rows.sort(key=lambda r: (r[0].playtime_minutes or 0, r[0].play_count or 0, r[0].added_at), reverse=True)
    return rows[:limit]
