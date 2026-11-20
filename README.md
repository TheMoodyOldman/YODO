# 友多聞 YODO

跨平台的興趣名片：把你玩的遊戲、追的動畫、聽的音樂放在同一頁，分享給朋友，並做成 IG 限時動態尺寸的 Recap 卡片。

僅限 18 歲以上使用。目前完成 MVP、第二階段（好友、動態、同好推薦）與第三階段的小遊戲。

## 功能

**個人興趣頁** `/u/帳號`
- 頂端是可左右滑的照片（最多 4 張，在 `/me/photos` 上傳；第一張是大頭照，伺服器會裁成 4:5 並移除拍攝地點等 EXIF）
- 分成總覽、遊戲、動畫、音樂、影視、書籍分頁，可直接用 `#game` 這類連結打開指定分頁
- 每個類別可設定公開範圍：所有人／好友／僅自己（好友功能推出前，「好友」等同僅自己）
- 單一作品可以隱藏；從外部匯入的資料要先確認才會公開

**作品頁** `/u/帳號/w/作品`
- 你的紀錄：總時數或播放次數、排名、加入日期、每月長條圖
- 作品資訊：遊戲取自 Steam 商店頁，動畫取自 AniList，音樂取自 Last.fm，影視取自 TMDB，書籍取自 Google Books／Open Library（查不到就不顯示）
- 背景用封面模糊加漸層，左右箭頭或鍵盤 ← → 切換作品

**各類別的資料來源**

| 類別 | 來源 | 怎麼排序 |
|---|---|---|
| 遊戲 | 用 Steam 登入連結帳號，自動匯入遊戲庫與遊玩時數（只匯入玩超過 1 小時的） | 遊玩時數 |
| 動畫 | 用中文、英文或日文片名搜尋後加入（AniList，中文片名由 Bangumi 番組計劃對照），加入時會跳出評價視窗 | 評價等級 |
| 音樂 | 用 Last.fm 登入同步收聽紀錄，或上傳 Google Takeout 的 YouTube Music 紀錄 | 播放次數 |
| 影視 | 用 TMDB 搜尋電影、影集後加入，或上傳 Netflix 觀看紀錄 | 評價等級 |
| 書籍 | 用 Google Books（未設定金鑰時改用 Open Library，繁簡中文都會搜尋）搜尋後加入 | 閱讀狀態，再依評價等級 |

動畫評價分為「此生必看／大推／還不錯／普通／雷／已棄坑」，另可加一個 ACG 用語標籤（例如 #神作、#胃痛、#我看了什麼）。影視與書籍用同一組等級，標籤換成各自的用語（例如影視的 #後勁很強、#值得二刷，書籍的 #一口氣讀完、#難啃）；書籍另有「想讀／在讀／讀完」狀態。等級、標籤與狀態定義在 `app/anime.py`。

**好友與動態** `/me/friends`、`/feed`
- 雙向好友邀請；興趣頁可加好友、解除好友、封鎖
- 公開範圍設為「好友」的類別只有好友看得到
- 動態會顯示你和好友最近加入或評價的動畫、玩了多久的遊戲、這個月聽了什麼，可以留言
- 同一天、同類型的動作合併成一則，隱藏或不公開的內容不會出現在好友的動態
- 封鎖後雙方互相看不到對方的頁面，也不能再送邀請

**探索（同好推薦）** `/match`
- 大照片卡片，✕ 不感興趣、♥ 送好友邀請、💞 測契合度
- 依共同喜歡的作品配對：越冷門的作品、雙方投入越深（遊玩時數、播放次數、動畫評價），分數越高；同一位歌手也算
- 每位推薦對象附上配對理由當開場話題，例如「你們都在《星露谷物語》玩了超過 200 小時」，冷門的共同喜好會標上「冷門」
- 只用對方設為「所有人」的類別；地區與「想找的對象」相同會加分
- 可以「不感興趣」或檢舉；3 位不同使用者檢舉後，該帳號會先從推薦中移除，等待管理員在 `/admin/reports` 審核
- 不想被推薦的人可以在設定中關閉

**作品討論與評分** `/w/作品`
- 每件作品有公開頁：大家的等級分布、熱門標籤、收藏人數（遊戲顯示平均遊玩時數）；不換算成分數
- 統計包含所有人的收藏，設為「僅自己」或「好友」的收藏以匿名方式計入；隱藏或待確認的收藏不算
- 短評：每人一則，附上自己的等級與標籤（對方看得到該類別時才顯示），可標記「有雷」先遮住，其他人可按「有同感」
- 留言區：自由留言；短評、留言都可以檢舉，作者與管理員可以刪除
- 個人作品頁有「大家怎麼看」連結；動畫、影視、書籍可以直接從公開頁加入收藏

**討論區** `/discuss`
- 依類別分區、不限作品，以便利貼牆呈現；點開便利貼就是討論串，可回覆
- 便利貼可選顏色、標記有雷；有新回覆的便利貼會排到前面
- 便利貼只在牆上顯示 7 天，之後牆上看不到，但持有連結的人仍可打開、回覆
- 封鎖的雙方互相看不到對方的短評、留言與便利貼

**電子信箱驗證** `/me/verify`
- 註冊要填電子信箱（不公開、不能重複），註冊後寄出驗證信；帳號或電子信箱都能登入，登入頁有「忘記密碼」
- 設定好寄信服務後，沒驗證的帳號仍可瀏覽、管理收藏，但不能加好友、傳訊息、發文、開遊戲房間，避免批量開帳號
- 驗證連結 48 小時內有效、重設密碼連結 60 分鐘內有效且只能用一次；更換信箱需要重新驗證
- 還沒設定寄信服務時不會強制驗證，信件內容（含連結）會印在伺服器終端機，方便本機測試

**私訊** `/me/messages`
- 好友之間一對一聊天；在「附近」回應過彼此的人也能聊。新訊息每 4 秒自動更新，未讀數顯示在「我的」
- 還沒聊過時，會用你們都收藏的作品當開場話題；封鎖後雙方都不能再傳

**附近的人** `/nearby`（在「探索」裡切換）
- 留一句話給附近的人（1／3／5／10 公里內），24 小時後自動消失，可隨時收回
- 附近的人看得到你的名字、興趣和這句話；對方回應後你才知道是誰，並直接開啟私訊
- 只用約略位置：座標在瀏覽器和伺服器都四捨五入到約 1 公里，自己的位置只存在登入工作階段、不進資料庫；別人只看到「約 3 公里內」這種範圍，沒有任何人的精確位置

**聯絡方式與新手教學**
- 設定頁可填 LINE、Discord、Instagram，每個欄位可設「只給好友看」或「不公開」，永遠不會公開給所有人
- 新使用者會在動態、收藏和自己的頁面看到「開始使用 YODO」清單（照片、自介、3 個收藏、認識一位同好、說點什麼），依實際資料自動打勾，可隱藏、可在設定重新打開
- 互動教學：第一次登入會跳出視窗，必須選「開始教學」或「先跳過」；教學中以浮動卡片顯示「第 N 步，共 5 步」與進度，頁面變暗並用光圈標出要按的按鈕，切換頁面時有投影片式的滑動轉場；步驟依實際資料自動完成，可上一步、略過這步或跳過教學，設定裡可重新開始
- 探索在人還少、找不到共同喜好時，會列出「新加入的同好」，讓新使用者也能送出好友邀請

**小遊戲** `/games`
- **品味契合度挑戰**：在別人的興趣頁按「測契合度」，先猜再揭曉契合度、你們都愛的作品、對方推薦你的作品
- **猜猜這是誰的收藏**：五題，看三件作品猜是哪位好友的收藏
- **興趣賓果**：每月一張 5×5，部分格子依收藏自動打勾，其他自己點
- **30 天挑戰**：歌曲／動畫／遊戲三種，每天一個題目，從收藏挑作品回答，可發當日限動或 30 天總覽
- **猜誰是臥底**（3–8 人即時）：同一張動畫角色 4×4 表，臥底圈到不同的詞；描述、投票，被抓的臥底猜中平民的詞算平手
- **猜歌對戰**（1 對 1 即時）：5 首歌，依 3／5／10／25／30 秒逐段播放 Apple Music 官方試聽，越早猜中分數越高；題目只挑兩人都有或都可能聽過的歌，揭曉後可用 YouTube 聽完整首
- 即時遊戲（猜歌、臥底）的房間可以直接邀請好友：對方在任何頁面都會跳出邀請，按「加入」就進房，不用傳連結
- 猜歌優先選兩人都聽過的歌，不夠時依序補上喜歡同一歌手、風格相近、熱門歌曲，最後是只有一人聽過的歌（揭曉時會標示來自誰的收藏）
- 結果都能產生分享卡，分享與下載次數會記錄

**風格統計**
- 背景自動查詢每件作品的類型：遊戲用 Steam 商店分類、動畫用 AniList 類型、音樂用 Last.fm 歌曲標籤（沒有時退回歌手標籤）、影視用 TMDB 類型、書籍用書籍分類
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
| `TMDB_API_KEY` | 搜尋電影與影集、比對 Netflix 紀錄 | [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api)，v3 API Key 或 v4 Read Access Token 都可以 |
| `GOOGLE_BOOKS_API_KEY` | 選填但建議：搜尋書籍（中文書較完整） | [Google Cloud Console](https://console.cloud.google.com/apis/library/books.googleapis.com) 啟用 Books API 後建立 API 金鑰；未設定時改用 Open Library |
| `SMTP_HOST`／`SMTP_PORT`／`SMTP_USER`／`SMTP_PASSWORD`／`MAIL_FROM` | 寄驗證信與重設密碼信；設定後才會強制驗證電子信箱 | Gmail：開啟兩步驟驗證後到 [應用程式密碼](https://myaccount.google.com/apppasswords) 建立一組，`SMTP_HOST=smtp.gmail.com`、`SMTP_PORT=587`、`SMTP_USER` 與 `MAIL_FROM` 填你的 Gmail |
| `PUBLIC_URL` | 選填：信件裡連結使用的網址（例如 trycloudflare 或正式網域） | 不填就用使用者當下開的網址 |
| `ADMIN_USERNAMES` | 選填：可以審核檢舉的帳號，逗號分隔 | 例如 `domino` |
| `BACKGROUND_JOBS` | 選填：設為 `false` 關閉背景類型查詢（測試用） | 預設開啟 |
| `CARD_FONT_REGULAR`、`CARD_FONT_BOLD` | 選填：Recap 卡片用的中文字型檔路徑 | 見下方「部署注意事項」 |

AniList 與 Steam 商店頁不需要金鑰。

### Demo 環境（demo.db）

Demo 用一個獨立的資料庫 `demo.db`，裡面只有示範帳號 `demo` 和幾個 `demo_` 開頭的假帳號，不會碰到真實使用者的 `app.db`。

**第一次建立**（需要網路，約 2 分鐘）：

```powershell
.venv\Scripts\python.exe -m scripts.seed_demo
```

會從頭建立快照 `demo.seed.db`，再複製成 `demo.db`。內容包括：
- `demo` 帳號的動畫評價、遊戲時數、音樂播放次數（Recap 有資料）、本季新番勾選，和小雨的私訊。
- 4 個 `demo_` 假帳號：小雨、阿哲是 demo 的好友（動態、私訊、猜歌），小光、奈奈不是（探索推薦）。
- 事先存好的快取：本季新番清單和中文片名、猜歌的試聽片段，Demo 時不用等 AniList、Bangumi、iTunes。

`demo` 的密碼寫在 `scripts/seed_demo.py`，只適合本機和 Demo 使用。

**一鍵啟動 Demo**（建議）：

```powershell
powershell -ExecutionPolicy Bypass -File .\start_demo.ps1
```

腳本會依序：
1. 停掉佔用 port 8000 的 Python 伺服器，包括上一次的 Demo，以及開在 `127.0.0.1:8000` 的開發伺服器（含 `--reload` 的子程序）。**port 8000 保留給 Demo**：開發伺服器請改用其他 port；不停掉的話，筆電上的 `localhost:8000` 會打開開發伺服器而不是 Demo。停不掉時腳本會直接結束、不啟動。
2. 重置 `demo.db`。
3. 用 `demo.db` 和本機封面，在 `0.0.0.0:8000` 啟動，讓同一個 Wi-Fi 的手機連得進來。
4. 印出筆電的區網 IP 和手機要開的網址，例如 `http://192.168.50.183:8000/login`。

按 Ctrl+C 停止。

**手機連不上時（Windows 防火牆）**：

Windows 會擋掉「公用網路」上別人連進筆電的連線，學校、咖啡廳的 Wi-Fi 通常都被設成公用網路。依序試：

1. 第一次執行時如果跳出「Windows 安全性警示」，勾選允許存取後按「允許」。
2. 把這個 Wi-Fi 改成私人網路：設定 → 網路和網際網路 → Wi-Fi → 點目前連線的網路 → 網路設定檔類型選「私人網路」。
3. 還是不行的話，用**系統管理員身分**開 PowerShell，只開放同一個網段連 port 8000：

   ```powershell
   New-NetFirewallRule -DisplayName "YODO Demo 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -RemoteAddress LocalSubnet -Action Allow
   ```

   Demo 結束後刪掉這條規則：

   ```powershell
   Remove-NetFirewallRule -DisplayName "YODO Demo 8000"
   ```

4. 有些場地的 Wi-Fi 會隔離裝置，手機彼此、手機和筆電都連不到，這時防火牆設定也沒用。改用一支手機開熱點，讓筆電和其他手機都連這個熱點，再執行一次 `start_demo.ps1`（IP 會變）。

先在現場用一支手機打開印出的網址測試一次。

**手動啟動**（不重置、只開給本機）：

```powershell
$env:DATABASE_URL = "sqlite:///demo.db"; $env:LOCAL_ASSETS_DIR = "demo_assets"; .venv\Scripts\uvicorn.exe app.main:app --port 8000
```

封面和試聽片段在 `seed_demo` 時會一起下載到 `demo_assets/`（約 13 MB，不進 git）。只想重新下載時：

```powershell
.venv\Scripts\python.exe -m scripts.cache_covers
```

本機找不到的檔案會照常連網讀取，所以就算少了幾張也不會壞掉。手機透過 Cloudflare 臨時網址連進來時，通道本身仍需要網路；現場沒有網路的話，改用同一個 Wi-Fi 的區網網址。

**每次 Demo 前重置**（不需要網路，一秒內完成；先按 Ctrl+C 停掉伺服器）：

```powershell
.venv\Scripts\python.exe -m scripts.reset_demo
```

會把 `demo.db` 還原成快照的狀態：上次 Demo 新增的勾選、訊息、照片、遊戲房間都會清掉，demo 帳號關掉的本季新番橫幅也會重新出現。

**清掉其他資料庫裡的假帳號**：如果不小心把 `demo_` 假帳號加進了其他資料庫，可以先預覽、確認後再刪除（只刪 `demo_` 開頭的帳號和連到它們的資料，作品本身保留；請先備份）：

```powershell
.venv\Scripts\python.exe -m scripts.remove_demo_people           # 預覽會刪掉什麼
.venv\Scripts\python.exe -m scripts.remove_demo_people --apply   # 真的刪除
```

### 執行測試

```powershell
.venv\Scripts\python.exe tests\run_all.py           # 全部
.venv\Scripts\python.exe tests\run_all.py season    # 只跑名稱含 season 的
```

每個 `tests/test_*.py` 都是獨立腳本，各自用一個暫時的 SQLite 檔（`tests/*.db`，不會進 git），外部 API 都在測試裡用假的回應取代。
`test_youtube.py` 另外可以拿真的 Google Takeout 檔案測試：把環境變數 `YODO_TAKEOUT_DIR` 設成「YouTube 和 YouTube Music」資料夾，沒設定就跳過那幾項。

## 使用者需要知道的事

- **年齡**：註冊時需填出生日期，未滿 18 歲無法註冊。出生日期只用來確認年齡，不會公開。舊帳號第一次登入時會被要求補填；填寫後未滿 18 歲的帳號會被停用，頁面也不再公開，滿 18 歲後可用原帳號登入。

- **Steam**：要把 Steam 個人檔案的「遊戲詳細資料」設為公開才能同步。每月遊玩時數從連結 Steam 後才開始記錄，更早的月份只有累計總時數。
- **Last.fm**：第一次同步會匯入最近 6 個月；如果在 Last.fm 隱藏了最近收聽資訊，會無法同步。
- **YouTube Music**：在 Google Takeout 只勾「YouTube 和 YouTube Music」，並把「記錄」的格式改成 **JSON**（預設是 HTML）。上傳 `觀看記錄/watch-history.json` 與 `music (library and uploads)/music library songs.csv`。只會保留音樂播放，其他影片的觀看紀錄在上傳時就丟棄。
- **重複的歌**：同一首歌同時從 YouTube 和 Last.fm 匯入時，排行只取較高的播放次數，不會相加。
- **Netflix**：在 Netflix 網頁版「帳戶」→ 選擇個人檔案 →「觀看記錄」→ 最下方「全部下載」，上傳 `NetflixViewingHistory.csv`。影集的每一集合併成一部作品，看幾集算幾次；日本動畫會對照到 AniList 放進「動畫」類別，片名用 Netflix 台灣的譯名；一次最多比對 150 部，比對到的作品要先確認才會公開。重複上傳不會重複計算。

## 專案結構

```
app/
├── main.py            FastAPI 入口、路由註冊
├── models.py          資料表
├── db.py              資料庫連線與啟動時的自動補欄位
├── anime.py           動畫、影視、書籍的評價等級、標籤與閱讀狀態
├── community.py       作品討論與評分、討論區
├── messages.py        私訊
├── nearby.py          附近的人（只用約略位置）
├── contacts.py        LINE／Discord／Instagram 聯絡方式
├── onboarding.py      新手教學清單
├── seasonal.py        本季新番快速勾選（AniList 當季清單、勾選、季別標籤）
├── catalog.py         外部清單的資料庫快取（重開伺服器或 API 失敗時沿用）
├── local_assets.py    Demo 模式：封面與試聽片段優先從本機資料夾讀取（LOCAL_ASSETS_DIR）
├── anime_search.py    中文動畫搜尋與中文片名（Bangumi → AniList）
├── zh.py              繁簡轉換（OpenCC）
├── music.py           音樂匯入、排行計算
├── netflix.py         Netflix 觀看紀錄匯入
├── sync.py            Steam、Last.fm 同步
├── cards.py           Recap 統計（當月／當年／有史以來）
├── card_render.py     Recap 卡片繪製
├── workinfo.py        作品頁的外部資訊
├── importers/         上傳檔案解析（Google Takeout）
├── services/          外部 API：Steam、AniList、Bangumi、Last.fm、iTunes、TMDB、Google Books／Open Library
├── routers/           各頁面路由
├── templates/         Jinja 模板
└── static/            CSS 與 JS
scripts/               Demo 環境：seed_demo（建立 demo.db）、reset_demo（重置）、cache_covers（下載封面）、remove_demo_people
tests/                 整合測試（run_all.py 一次跑完）
```

## 在手機上測試、讓組員一起註冊

**同一個 Wi‑Fi（最快）**：讓伺服器聽所有網路介面，再用手機開電腦的區網 IP（`ipconfig` 裡的 IPv4，例如 `http://192.168.x.x:8000`）。第一次啟動時 Windows 防火牆會詢問，請允許「私人網路」。

```
./.venv/Scripts/uvicorn.exe app.main:app --host 0.0.0.0 --port 8000 --reload
```

限制：這是 HTTP，手機瀏覽器不允許「附近 → 使用目前位置」（可以改選地區），系統分享面板也可能無法使用；只有同一個網路的人連得到。

**不同網路／遠端組員（HTTPS 通道）**：用 Cloudflare 的免費快速通道產生一個 `https://….trycloudflare.com` 網址，手機和組員在任何地方都能開，HTTPS 下定位與分享都能用。

```
./.venv/Scripts/uvicorn.exe app.main:app --port 8000 --proxy-headers --forwarded-allow-ips "*"
```

```
cloudflared tunnel --url http://localhost:8000
```

`--proxy-headers` 讓 Steam／Last.fm 登入的回傳網址使用通道的 https 網址。快速通道的網址每次啟動都會變，電腦關機或關掉指令就無法連線；資料都存在這台電腦的 SQLite。長期給多人使用請改成正式部署（見下方）。

組員打開網址後點「註冊」即可，需填出生日期（未滿 18 歲無法註冊）；註冊後互加好友就能測試私訊、動態、契合度與即時小遊戲。

## 部署注意事項

- **資料庫變更**：啟動時只會自動補上「新增的可為空欄位」，改名、改型別或新增必填欄位需要自己處理。改用 PostgreSQL 或正式上線前建議導入 Alembic。
- **字型**：Recap 卡片依序嘗試 Windows 的微軟正黑體、Linux 的 Noto Sans CJK、macOS 的蘋方。Linux 伺服器請安裝 `fonts-noto-cjk`，或用 `CARD_FONT_REGULAR`／`CARD_FONT_BOLD` 指定字型檔，否則中文會顯示成方框。
- **HTTPS**：手機的「分享到 IG／Threads」需要 HTTPS（或 localhost）才能使用。
- **網址**：Steam 與 Last.fm 登入的回傳網址會依實際網域自動產生，上線後記得到兩邊的開發者設定更新網域。

## 接下來

依提案的規劃：

1. **第二階段**：~~好友、動態、同好推薦~~（已完成），接著在校園社團內試行，確認用戶密度足以讓推薦有意義
2. **第三階段**：~~小遊戲、影視與電子書、Netflix 觀看紀錄匯入、作品討論與評分~~（已完成）


## Kobo 看過的書快速匯入

入口：我的收藏 → 書籍（`/me/collection#book`）。選檔、貼上書單和錯誤提示都直接整合在此分頁，不需要再開 Kobo 獨立頁。舊 `/me/kobo` 網址會導回書籍分頁。

- 有 Kobo 閱讀器：USB 連接後選取 `.kobo/KoboReader.sqlite`，瀏覽器自動整理書單，再確認一次公開哪些書。
- 預設只帶入「讀完＋在讀」，可改成只要讀完，或全部含未讀。`ReadStatus` 0／1／2 分別對應想讀／在讀／讀完；不會把所有購書紀錄當成讀完。
- 沒有閱讀器：每行貼一本書，可貼試算表的「書名 Tab 作者」兩欄，再選閱讀狀態，一次批次加入。
- 新書沿用匯入確認清單，確認前不會出現在公開名片；取消勾選的書設為隱藏。既有收藏的評價、閱讀狀態和隱私不會被覆蓋。
- 完全相同的書名＋作者跨來源重用，重複匯入不新增重複收藏。ISBN 存在時使用 Open Library 封面，無封面也能加入；不會自動以模糊搜尋結果替換書籍。

這是**本機書櫃資料匯入**，不是 Kobo 官方 OAuth 帳號連結，不會持續同步。手機 Kobo App 沒有閱讀器的檔案入口；也不能保證設備已刪除、未同步或特定韌體未提供的書籍會出現在檔案中。官方支援筆記匯出，但筆記清單不等於完整已讀書櫃，因此本功能不將筆記內容當成讀完證明。

### 資料與依賴

Kobo 原始 SQLite 僅在瀏覽器的本機 WebAssembly 解析，不上傳伺服器。檔案欄位沒有表單名稱；送出的只有白名單書籍資料（書名、作者、ISBN、閱讀狀態），不包含電子書內容、劃線、筆記、帳號或裝置識別。伺服器再驗證大小、筆數與欄位，並沿用登入者身分與收藏隱私。

解析器為 `app/static/vendor/sql.js/` 中固定版本的 sql.js（版本見 VERSION，MIT 授權同目錄 LICENSE），從官方 npm 套件下載並驗證 SHA-512。所有資源由本站提供，只有 Kobo 區塊出現在畫面時才下載 WASM，其他收藏分頁不預先載入；執行時不需要第三方 CDN、不需要新增伺服器套件，也不需要使用者申請金鑰。

若要更新解析器，請使用官方 sql.js 發布，保留 LICENSE，並一起更新 JS 與 WASM 檔案。閱讀器資料庫欄位依韌體可能不同；缺少必要欄位時會提示改用貼上書單，不會猜測狀態。

### 驗證

`tests/test_kobo.py`：登入保護、批次匯入、重複與跨來源去重、既有資料保留、公開確認、使用者隔離、無效／超量資料、書籍詳情頁。會呼叫 `tests/kobo_reader.cjs`，用虛構 SQLite 驗證實際 WASM 解析、章節過濾、讀完／在讀／未讀及敏感欄位不外傳；執行此套測試需有 Node.js。

已用實際瀏覽器與虛構 Kobo SQLite 完成選檔 → 本機解析 → 確認 → 公開名片流程，另驗證取消勾選後隱藏、無效檔案錯誤恢復及批次貼上。伺服器請求記錄確認未上傳原始 SQLite 或假敏感欄位；本次書櫃請求僅 345 bytes。驗證紀錄見 `tests/evidence/kobo-feasibility.json`，畫面見 `tests/evidence/kobo-review.jpg`。

目前仍未用真人閱讀器檔案驗證。可用個人閱讀器實測本機解析與狀態；請勿將真實 KoboReader.sqlite 放入 Git repo、issue 或公開測試附件。

參考：[Kobo 官方筆記匯出說明](https://help.kobo.com/hc/en-us/articles/29991333812631-Export-annotations-from-your-books)、[KoboReader 欄位查詢範例](https://gist.github.com/ozgurkalan/730f76e2ca7df552151c09a1df8d36bd)、[sql.js 原始專案](https://github.com/sql-js/sql.js)。


## 各平台書單與 Google 書櫃匯入

入口同樣在 **我的收藏 → 書籍**。Readmoo、博客來、HyRead、Pubu 等平台可複製可取得的書名清單，每行一本；若有作者，可貼試算表的書名、作者兩欄（Tab 分隔）。選擇這份清單的閱讀狀態後批次加入。不需要提供平台密碼；這是通用文字匯入，不是各平台官方帳號連結，也不會自動抓取那些平台的私人書櫃。

Google 書櫃則提供一次性的 OAuth 授權入口。一般使用者只要登入 Google、授權，再確認收藏；不需要自行申請金鑰。新書一律先進入隱私確認清單，既有收藏的閱讀狀態、評價、隱藏設定不覆蓋。相同來源 ID 或完全一致的書名與作者會沿用既有作品；不使用模糊搜尋猜測作品。

### 網站管理者的一次性 Google 設定

1. 在 Google Cloud 專案啟用 Books API，設定 Google Auth Platform 的同意畫面與 OAuth Web application 用戶端。
2. 在部署環境設定 `GOOGLE_BOOKS_CLIENT_ID`、`GOOGLE_BOOKS_CLIENT_SECRET`，以及 `GOOGLE_BOOKS_REDIRECT_URI`（例如 `https://your-domain/me/google-books/callback`）；後者須與 Google 登記的重新導向 URI 完全一致。未指定時使用 `PUBLIC_URL` 或目前請求網址產生。正式環境應明確設定 HTTPS callback。
3. 尚在 Testing 模式時，把實際測試 Google 帳號加入測試使用者。對外發布前需按 Google Console 的要求處理應用程式驗證與隱私權政策。未設定 OAuth 用戶端時，頁面會停用 Google 按鈕，貼上與 Kobo 仍可用。

不要將 client secret 或使用者的 access token 放進 Git。程式只把 OAuth state、PKCE verifier、登入者 ID、10 分鐘期限等暫存於簽章 session；access token 僅用於當次伺服器記憶體中的 API 請求，不寫入 session、資料庫或檔案，不申請離線 refresh token。這是單次匯入，沒有背景同步，也不會顯示為永久綁定帳號。

預設讀取 Google 書架 4（讀過）、3（正在讀）；勾選擴充項目後，另讀取 2（想讀）、1（已購買）、7（我的電子書）。購買與電子書清單的作品保留未知閱讀狀態，不會自動當成讀完。每次最多 1000 本，以每頁 40 本分頁讀取；任何一頁失敗時整次不寫入資料庫。Google Books API 的書櫃不保證包含完整 Play 圖書購買、上傳或閱讀紀錄；空書架時可改用貼上清單。

Google Books 僅提供 `https://www.googleapis.com/auth/books` 授權範圍，包含管理書櫃的權限；頁面會明確說明，本實作只呼叫 GET 書櫃讀取，不新增或刪除遠端書籍。官方參考：[授權與書架 ID](https://developers.google.com/books/docs/v1/using)、[分頁讀取私人書架](https://developers.google.com/books/docs/v1/reference/mylibrary/bookshelves/volumes/list)。

驗證：`tests/test_book_import.py` 使用獨立虛構資料庫與模擬 Google OAuth/API 回應，涵蓋分頁、來源重複、閱讀狀態、授權失效、重放及失敗不寫入。尚未設定正式 Google OAuth 用戶端，真人 Google 帳號授權與 Play 圖書涵蓋程度仍待實測；不將模擬測試當成實際帳號連線成功。


## 容器部署與上線驗收

提供 `Dockerfile`、`compose.yaml` 與 `scripts/serve.py`。容器只複製程式，不帶入本機 .env、資料庫、測試帳號或 Kobo 檔案。使用 Python 3.12、非 root 使用者、中文字型、單一 SQLite worker，健康檢查為 `/health`。照片保存在資料庫，SQLite 與照片都需保留 `/data` 的持久化磁碟；**不要使用會在重啟後清空檔案的主機方案**。Render 的持久化磁碟目前需付費服務，這份變更沒有建立或購買任何主機。

在支援持久化磁碟的容器主機設定：

- `SECRET_KEY`：管理者建立至少 32 字元的隨機值並穩定保存；啟動程式拒絕空值或短值，不會輸出金鑰。
- `PUBLIC_URL=https://正式網址`、`SESSION_HTTPS_ONLY=true`；單機 HTTP 驗收才設為 false。
- `DATABASE_URL=sqlite:////data/app.db`（容器預設），將 `/data` 掛載為持久化磁碟，維持單個服務實例。增加實例前須另處理 SQLite 與遊戲狀態同步。
- Google 的三個 OAuth 設定如上節；先註冊正式 callback，再在後台填入 secret，不將 secret 交給一般用戶。反向代理的來源只有在確認可信時才設定 `FORWARDED_ALLOW_IPS`；不要直接信任任意外部請求。

本機 Docker 可執行 `docker compose up --build -d`；先在管理者的私有環境設定上述值。Compose 只綁定 127.0.0.1:8000，正式對外服務另接 HTTPS 反向代理。Google callback 使用同一個網域登入及返回，避免 localhost/127.0.0.1 混用。啟動停用 access log，避免 OAuth callback 的 code 出現在請求紀錄；主機或反向代理也應遮蔽此路徑的查詢參數。

驗收順序：`/health` → 註冊／登入 → 貼上書單 → 隱私確認 → 名片 → Google 授權讀取 → 重複匯入 → 取消授權 → 服務重啟後收藏仍在。Google 未提供用戶端與可登入測試者前只能完成模擬驗證；Kobo 未提供閱讀器時使用合成 SQLite 測試，不宣稱已驗證所有實體韌體。此次 Windows Docker 引擎未啟動，映像建置需在有 Linux 容器引擎的主機補驗。

部署文件參考：[Google Web OAuth](https://developers.google.com/identity/protocols/oauth2/web-server)、[Render 持久化磁碟](https://render.com/docs/disks)。
