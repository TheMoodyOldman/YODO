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

**拍照找書** `/books/scan`（收藏的書籍分頁有入口）
- 三種方式找到一本書，找到後直接打開它的作品公開頁（簡介、大家的評價），要不要加入收藏由使用者決定
- **掃條碼**：用相機對準封底的 ISBN 條碼，讀到就查詢；條碼在瀏覽器裡解讀（BarcodeDetector，Android 的 Chrome、Edge、Samsung Internet 支援），相機需要 HTTPS 或 localhost
- **拍照**：拍封底、版權頁或封面，依序嘗試：照片裡的條碼 → 照片上印的 ISBN 數字（[Tesseract.js](https://github.com/naptha/tesseract.js) 在瀏覽器裡辨識，免費、所有瀏覽器可用，第一次使用會從 jsDelivr 下載幾 MB 的辨識資料；iPhone 的 HEIC 照片會先用 [heic2any](https://github.com/alexcorvi/heic2any) 在瀏覽器裡轉成 JPEG）→ 有設定金鑰時交給 Claude API 讀出書名、作者與出版社。讀到 ISBN 就直接開那本書；只讀到書名時列出候選書，由使用者選「就是這本」，避免選錯版本或譯本
- **輸入 ISBN**：10 碼或 13 碼都可以，會檢查最後一碼的檢查碼
- ISBN 先查 Google Books（有金鑰時）再查 Open Library；沒有金鑰時順序相反，並多試一次不帶金鑰的 Google Books
- 讀封面書名需要 `ANTHROPIC_API_KEY`；沒設定時仍可掃條碼、拍 ISBN 數字與輸入 ISBN。條碼與數字在使用者的裝置上辨識，照片不會上傳；只有要讀書名時才會把照片縮小、移除 EXIF 後送出，不會保存，每人每小時最多 20 次

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
| `ANTHROPIC_API_KEY` | 選填：拍照找書讀封面與版權頁 | [Claude Console](https://console.anthropic.com) 建立 API 金鑰（依用量付費）；未設定時只能掃條碼或輸入 ISBN。模型可用 `VISION_MODEL` 調整，預設 `claude-haiku-5-5` |
| `SMTP_HOST`／`SMTP_PORT`／`SMTP_USER`／`SMTP_PASSWORD`／`MAIL_FROM` | 寄驗證信與重設密碼信；設定後才會強制驗證電子信箱 | Gmail：開啟兩步驟驗證後到 [應用程式密碼](https://myaccount.google.com/apppasswords) 建立一組，`SMTP_HOST=smtp.gmail.com`、`SMTP_PORT=587`、`SMTP_USER` 與 `MAIL_FROM` 填你的 Gmail |
| `PUBLIC_URL` | 選填：信件裡連結使用的網址（例如 trycloudflare 或正式網域） | 不填就用使用者當下開的網址 |
| `ADMIN_USERNAMES` | 選填：可以審核檢舉的帳號，逗號分隔 | 例如 `domino` |
| `BACKGROUND_JOBS` | 選填：設為 `false` 關閉背景類型查詢（測試用） | 預設開啟 |
| `CARD_FONT_REGULAR`、`CARD_FONT_BOLD` | 選填：Recap 卡片用的中文字型檔路徑 | 見下方「部署注意事項」 |

AniList 與 Steam 商店頁不需要金鑰。

### Demo 環境（demo.db）

Demo 用一個獨立的資料庫 `demo.db`，裡面只有示範帳號 `demo` 和幾個 `demo_` 開頭的假帳號，不會碰到真實使用者的 `app.db`。

**第一次建立**（需要網路，約 30～60 分鐘；網路斷線會自動等待恢復）：

```powershell
.venv\Scripts\python.exe -m scripts.seed_demo
```

會從頭建立快照 `demo.seed.db`，再複製成 `demo.db`。內容包括：
- `demo` 帳號的動畫評價、遊戲時數、音樂播放次數（Recap 有資料）、本季新番勾選，和小雨的私訊。
- 24 個 `demo_` 假帳號（`scripts/demo_people.py`）：每人有自介、照片、聯絡方式，動畫／影視／書／遊戲／音樂各 30 筆以上，依各自口味產生。小雨、阿哲是 demo 的好友（動態、私訊、猜歌），麻糬、雪乃、Ivy 送了好友邀請，其他人是陌生人（探索推薦）。全部可用 demo 的密碼登入。影視需要 `.env` 的 `TMDB_API_KEY`。
- 事先存好的快取：本季新番清單和中文片名、猜歌的試聽片段，Demo 時不用等 AniList、Bangumi、iTunes。

`demo` 的密碼寫在 `scripts/seed_demo.py`，只適合本機和 Demo 使用。

帳號和收藏建好後中斷了：`python -m scripts.seed_demo --finish` 只重跑後面的步驟。iTunes 擋下試聽查詢時：過一陣子執行 `python -m scripts.fill_previews` 補上。

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

### 正式版上線（app.db，給評審、觀眾註冊使用）

正式版用的是 `app.db`，資料全部保留、不會重置。它和 Demo 是兩台獨立的伺服器：正式版在 port 8001，Demo 在 port 8000，可以同時開著，互不影響。

**啟動**（在專案資料夾）：

```powershell
powershell -ExecutionPolicy Bypass -File .\start_live.ps1
```

腳本會依序：

1. 確認 port 8001 沒有伺服器在跑；如果已經有，就不會備份也不會啟動。
2. 把 `app.db` 備份成 `app.db.bak-日期-時間`。用的是 SQLite 自己的備份功能，所以備份是一個完整的檔案。
3. 把 `app.db` 切換成 WAL 模式（只會切換一次，資料不會變），讓很多人同時讀寫時不會出現 database is locked。之後資料夾裡會多出 `app.db-wal` 和 `app.db-shm`，它們是 `app.db` 的一部分，伺服器在跑的時候不要刪掉或搬走。
4. 在另一個視窗開 Cloudflare 臨時通道。這個視窗會縮到工作列，不要關掉它。
5. 在畫面上顯示通道網址的 QR Code，同時開一張大圖，可以直接把筆電轉給評審掃。網址每次啟動都會不一樣。
6. 用 `app.db` 啟動伺服器：`0.0.0.0:8001`，不用 --reload。`DATABASE_URL` 寫死在腳本裡，所以就算之前跑過 `start_demo.ps1` 也不會用錯資料庫。本機有的封面會直接用本機檔案。

**停止**：在執行腳本的視窗按 **Ctrl+C**，通道會跟著關掉。如果通道視窗還在，直接把它關掉就好。

**cloudflared**：這台筆電已經裝好了，放在 `%USERPROFILE%\cloudflared\cloudflared.exe`，腳本會自動找到。換一台電腦的話，用下面的指令安裝，或是把 `CLOUDFLARED` 環境變數設成 cloudflared.exe 的路徑：

```powershell
winget install --id Cloudflare.cloudflared
```

找不到 cloudflared 時，腳本仍然會啟動伺服器，只是改成顯示同一個 Wi-Fi 的區網網址和 QR Code。

**從備份還原**：先按 Ctrl+C 停掉正式版，再執行下面的指令（把檔名換成要還原的那一份）：

```powershell
Remove-Item app.db-wal, app.db-shm -ErrorAction SilentlyContinue; Copy-Item app.db.bak-20261121-090000 app.db -Force
```

**管理員**：`.env` 裡 `ADMIN_USERNAMES` 列出的帳號可以刪除任何人的便利貼、便利貼回覆、短評和作品頁留言。動態牆上的留言只有留言者本人和該則動態的主人能刪。

**信箱驗證**：`.env` 沒有設定寄信（SMTP）時，不會要求驗證信箱，註冊後馬上可以使用。

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
