# 友多聞 YODO

跨平台的興趣名片：把你玩的遊戲、追的動畫、聽的音樂放在同一頁，分享給朋友，並做成 IG 限時動態尺寸的 Recap 卡片。

僅限 18 歲以上使用。目前完成 MVP、第二階段（好友、動態、同好推薦）與第三階段的小遊戲。

## 功能

**個人興趣頁** `/u/帳號`
- 分成總覽、遊戲、動畫、音樂四個分頁，可直接用 `#game` 這類連結打開指定分頁
- 每個類別可設定公開範圍：所有人／好友／僅自己（好友功能推出前，「好友」等同僅自己）
- 單一作品可以隱藏；從外部匯入的資料要先確認才會公開

**作品頁** `/u/帳號/w/作品`
- 你的紀錄：總時數或播放次數、排名、加入日期、每月長條圖
- 作品資訊：遊戲取自 Steam 商店頁，動畫取自 AniList，音樂取自 Last.fm（查不到就不顯示）
- 背景用封面模糊加漸層，左右箭頭或鍵盤 ← → 切換作品

**三種類別的資料來源**

| 類別 | 來源 | 怎麼排序 |
|---|---|---|
| 遊戲 | 用 Steam 登入連結帳號，自動匯入遊戲庫與遊玩時數（只匯入玩超過 1 小時的） | 遊玩時數 |
| 動畫 | 用 AniList 搜尋後手動加入，加入時會跳出評價視窗 | 評價等級 |
| 音樂 | 用 Last.fm 登入同步收聽紀錄，或上傳 Google Takeout 的 YouTube Music 紀錄 | 播放次數 |

動畫評價分為「此生必看／大推／還不錯／普通／雷／已棄坑」，另可加一個 ACG 用語標籤（例如 #神作、#胃痛、#我看了什麼）。等級與標籤定義在 `app/anime.py`。

**好友與動態** `/me/friends`、`/feed`
- 雙向好友邀請；興趣頁可加好友、解除好友、封鎖
- 公開範圍設為「好友」的類別只有好友看得到
- 動態會顯示你和好友最近加入或評價的動畫、玩了多久的遊戲、這個月聽了什麼，可以留言
- 同一天、同類型的動作合併成一則，隱藏或不公開的內容不會出現在好友的動態
- 封鎖後雙方互相看不到對方的頁面，也不能再送邀請

**同好推薦** `/match`
- 依共同喜歡的作品配對：越冷門的作品、雙方投入越深（遊玩時數、播放次數、動畫評價），分數越高；同一位歌手也算
- 每位推薦對象附上配對理由當開場話題，例如「你們都在《星露谷物語》玩了超過 200 小時」，冷門的共同喜好會標上「冷門」
- 只用對方設為「所有人」的類別；地區與「想找的對象」相同會加分
- 可以「不感興趣」或檢舉；3 位不同使用者檢舉後，該帳號會先從推薦中移除，等待管理員在 `/admin/reports` 審核
- 不想被推薦的人可以在設定中關閉

**小遊戲** `/games`
- **品味契合度挑戰**：在別人的興趣頁按「測契合度」，先猜再揭曉契合度、你們都愛的作品、對方推薦你的作品
- **猜猜這是誰的收藏**：五題，看三件作品猜是哪位好友的收藏
- **興趣賓果**：每月一張 5×5，部分格子依收藏自動打勾，其他自己點
- **30 天挑戰**：歌曲／動畫／遊戲三種，每天一個題目，從收藏挑作品回答，可發當日限動或 30 天總覽
- **猜誰是臥底**（3–8 人即時）：同一張動畫角色 4×4 表，臥底圈到不同的詞；描述、投票，被抓的臥底猜中平民的詞算平手
- **猜歌對戰**（1 對 1 即時）：5 首歌，依 3／5／10／25／30 秒逐段播放 Apple Music 官方試聽，越早猜中分數越高；題目只挑兩人都有或都可能聽過的歌，揭曉後可用 YouTube 聽完整首
- 結果都能產生分享卡，分享與下載次數會記錄

**風格統計**
- 背景自動查詢每件作品的類型：遊戲用 Steam 商店分類、動畫用 AniList 類型、音樂用 Last.fm 歌曲標籤（沒有時退回歌手標籤）
- 依投入程度加權，在興趣頁顯示每個類別的風格偏好，之後可用於推薦朋友與作品

**Recap 分享卡** `/me/card`
- 時間範圍可選當月、當年、有史以來；「有史以來」會顯示 Steam 總遊玩時數
- 1080×1920 圖片，手機上可直接分享到 IG 限時動態或 Threads，電腦上可下載
- 只有一個類別時會自動放大並顯示更多項目
- 分享與下載次數記錄在 `cardevent` 資料表，作為 MVP 的成效指標

## 技術

- Python 3.11 以上（開發時使用 3.14）
- FastAPI、SQLModel（SQLite）、Jinja2 伺服器端渲染，不需要前端建置流程
- httpx 呼叫外部 API，Pillow 繪製 Recap 卡片

## 安裝與啟動

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

編輯 `.env`，填入下面的設定後啟動：

```powershell
uvicorn app.main:app --reload
```

打開 http://127.0.0.1:8000 。資料表會在第一次啟動時自動建立。

### `.env` 設定

| 變數 | 用途 | 取得方式 |
|---|---|---|
| `SECRET_KEY` | 簽署登入 cookie，請換成隨機字串 | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `DATABASE_URL` | 資料庫位置，預設 `sqlite:///./app.db` | — |
| `STEAM_API_KEY` | 讀取 Steam 遊戲庫 | [steamcommunity.com/dev/apikey](https://steamcommunity.com/dev/apikey)，網域填 `localhost` 即可 |
| `LASTFM_API_KEY` | 讀取 Last.fm 收聽紀錄與歌曲資訊 | [last.fm/api/account/create](https://www.last.fm/api/account/create) |
| `LASTFM_SHARED_SECRET` | Last.fm 登入驗證 | 同上，建立應用程式後會一起拿到 |
| `ADMIN_USERNAMES` | 選填：可以審核檢舉的帳號，逗號分隔 | 例如 `domino` |
| `BACKGROUND_JOBS` | 選填：設為 `false` 關閉背景類型查詢（測試用） | 預設開啟 |
| `CARD_FONT_REGULAR`、`CARD_FONT_BOLD` | 選填：Recap 卡片用的中文字型檔路徑 | 見下方「部署注意事項」 |

AniList 與 Steam 商店頁不需要金鑰。

### 本機測試帳號

```powershell
python -m scripts.seed_demo
```

會建立帳號 `demo` 並加入幾部動畫，密碼寫在 `scripts/seed_demo.py`，只適合本機開發使用。

## 使用者需要知道的事

- **年齡**：註冊時需填出生日期，未滿 18 歲無法註冊。出生日期只用來確認年齡，不會公開。舊帳號第一次登入時會被要求補填；填寫後未滿 18 歲的帳號會被停用，頁面也不再公開，滿 18 歲後可用原帳號登入。

- **Steam**：要把 Steam 個人檔案的「遊戲詳細資料」設為公開才能同步。每月遊玩時數從連結 Steam 後才開始記錄，更早的月份只有累計總時數。
- **Last.fm**：第一次同步會匯入最近 6 個月；如果在 Last.fm 隱藏了最近收聽資訊，會無法同步。
- **YouTube Music**：在 Google Takeout 只勾「YouTube 和 YouTube Music」，並把「記錄」的格式改成 **JSON**（預設是 HTML）。上傳 `觀看記錄/watch-history.json` 與 `music (library and uploads)/music library songs.csv`。只會保留音樂播放，其他影片的觀看紀錄在上傳時就丟棄。
- **重複的歌**：同一首歌同時從 YouTube 和 Last.fm 匯入時，排行只取較高的播放次數，不會相加。

## 專案結構

```
app/
├── main.py            FastAPI 入口、路由註冊
├── models.py          資料表
├── db.py              資料庫連線與啟動時的自動補欄位
├── anime.py           動畫評價等級與標籤
├── music.py           音樂匯入、排行計算
├── sync.py            Steam、Last.fm 同步
├── cards.py           Recap 統計（當月／當年／有史以來）
├── card_render.py     Recap 卡片繪製
├── workinfo.py        作品頁的外部資訊
├── importers/         上傳檔案解析（Google Takeout）
├── services/          外部 API：Steam、AniList、Last.fm
├── routers/           各頁面路由
├── templates/         Jinja 模板
└── static/            CSS 與 JS
scripts/seed_demo.py   本機測試帳號
```

## 部署注意事項

- **資料庫變更**：啟動時只會自動補上「新增的可為空欄位」，改名、改型別或新增必填欄位需要自己處理。改用 PostgreSQL 或正式上線前建議導入 Alembic。
- **字型**：Recap 卡片依序嘗試 Windows 的微軟正黑體、Linux 的 Noto Sans CJK、macOS 的蘋方。Linux 伺服器請安裝 `fonts-noto-cjk`，或用 `CARD_FONT_REGULAR`／`CARD_FONT_BOLD` 指定字型檔，否則中文會顯示成方框。
- **HTTPS**：手機的「分享到 IG／Threads」需要 HTTPS（或 localhost）才能使用。
- **網址**：Steam 與 Last.fm 登入的回傳網址會依實際網域自動產生，上線後記得到兩邊的開發者設定更新網域。

## 接下來

依提案的規劃：

1. **第二階段**：~~好友、動態、同好推薦~~（已完成），接著在校園社團內試行，確認用戶密度足以讓推薦有意義
2. **第三階段**：~~小遊戲~~（已完成）、影視與電子書、更多檔案匯入（Netflix 觀看紀錄等）、作品討論與評分
