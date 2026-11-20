"""Who the demo's fake people are: profile details and collections, used by scripts.seed_demo.

Plain data, no app imports. Every person gets all five categories, in amounts and tastes that fit them,
so 探索, profiles and matching show clear differences between people. Titles are looked up when the
demo is seeded: anime on AniList (Chinese names from Bangumi), books on Google Books / Open Library,
films on TMDB when TMDB_API_KEY is set (otherwise the ids and Chinese titles below, without covers).
"""

# ---------- catalogues: what the people below can pick from ----------

# key -> AniList search text (English or romaji titles match best)
ANIME = {
    "frieren": "Frieren", "bocchi": "Bocchi the Rock", "mob": "Mob Psycho 100", "bebop": "Cowboy Bebop",
    "spyfamily": "Spy x Family", "jjk": "Jujutsu Kaisen", "aot": "Attack on Titan", "demonslayer": "Demon Slayer",
    "natsume": "Natsume's Book of Friends", "violet": "Violet Evergarden", "yourname": "Your Name",
    "steinsgate": "Steins;Gate", "haikyu": "Haikyu!!", "chainsaw": "Chainsaw Man", "kaguya": "Kaguya-sama: Love is War",
    "fma": "Fullmetal Alchemist: Brotherhood", "eva": "Neon Genesis Evangelion", "kon": "K-On!",
    "yurucamp": "Laid-Back Camp", "abyss": "Made in Abyss", "oshinoko": "Oshi no Ko",
    "apothecary": "The Apothecary Diaries", "dungeon": "Delicious in Dungeon", "gintama": "Gintama",
    "mushishi": "Mushishi", "toradora": "Toradora!", "codegeass": "Code Geass", "onepunch": "One Punch Man",
    "kiminitodoke": "Kimi ni Todoke", "oddtaxi": "Odd Taxi", "pingpong": "Ping Pong the Animation",
    "march": "March Comes in Like a Lion", "gurren": "Gurren Lagann", "silentvoice": "A Silent Voice",
}

# TMDB id -> (Chinese title, original title, year). Live-action only: TMDB's Japanese animation is filed under 動畫.
FILMS = {
    "movie:603": ("駭客任務", "The Matrix", 1999),
    "movie:27205": ("全面啟動", "Inception", 2010),
    "movie:157336": ("星際效應", "Interstellar", 2014),
    "movie:496243": ("寄生上流", "기생충", 2019),
    "movie:155": ("黑暗騎士", "The Dark Knight", 2008),
    "movie:597": ("鐵達尼號", "Titanic", 1997),
    "movie:862": ("玩具總動員", "Toy Story", 1995),
    "movie:354912": ("可可夜總會", "Coco", 2017),
    "movie:313369": ("樂來越愛你", "La La Land", 2016),
    "movie:278": ("刺激1995", "The Shawshank Redemption", 1994),
    "movie:438631": ("沙丘", "Dune", 2021),
    "movie:872585": ("奧本海默", "Oppenheimer", 2023),
    "movie:545611": ("媽的多重宇宙", "Everything Everywhere All at Once", 2022),
    "movie:299534": ("復仇者聯盟：終局之戰", "Avengers: Endgame", 2019),
    "movie:324857": ("蜘蛛人：新宇宙", "Spider-Man: Into the Spider-Verse", 2018),
    "tv:66732": ("怪奇物語", "Stranger Things", 2016),
    "tv:93405": ("魷魚遊戲", "오징어 게임", 2021),
    "tv:1396": ("絕命毒師", "Breaking Bad", 2008),
    "tv:1399": ("冰與火之歌：權力遊戲", "Game of Thrones", 2011),
    "tv:1668": ("六人行", "Friends", 1994),
}

# key -> book search text (original titles match best on Open Library)
BOOKS = {
    "littleprince": "The Little Prince", "harrypotter": "Harry Potter and the Philosopher's Stone",
    "1984": "Nineteen Eighty-Four Orwell", "animalfarm": "Animal Farm Orwell", "sapiens": "Sapiens Harari",
    "atomic": "Atomic Habits", "threebody": "The Three-Body Problem", "norwegian": "Norwegian Wood Murakami",
    "kafka": "Kafka on the Shore", "hailmary": "Project Hail Mary", "hobbit": "The Hobbit", "dune": "Dune Frank Herbert",
    "alchemist": "The Alchemist Coelho", "nolonger": "No Longer Human Dazai", "kitchen": "Kitchen Banana Yoshimoto",
    "coffee": "Before the Coffee Gets Cold", "namiya": "The Miracles of the Namiya General Store",
    "fastslow": "Thinking, Fast and Slow", "courage": "The Courage to Be Disliked", "martian": "The Martian Andy Weir",
    "readyplayer": "Ready Player One", "normalpeople": "Normal People Sally Rooney", "suspectx": "The Devotion of Suspect X",
}

# Steam appid -> name shown in YODO
GAMES = {
    413150: "星露谷物語", 1245620: "艾爾登法環", 1145360: "Hades", 367520: "窟窿騎士", 105600: "泰拉瑞亞",
    1086940: "柏德之門 3", 582010: "魔物獵人 世界", 504230: "Celeste", 646570: "殺戮尖塔", 1426210: "雙人成行",
    728880: "煮過頭 2", 391540: "Undertale", 292030: "巫師 3：狂獵", 1687950: "女神異聞錄 5 皇家版",
    2161700: "女神異聞錄 3 Reload", 814380: "隻狼：暗影雙死", 374320: "黑暗靈魂 III", 945360: "Among Us",
    1966720: "致命公司", 892970: "英靈神殿", 1794680: "吸血鬼倖存者", 588650: "死亡細胞", 2379780: "Balatro",
    1868140: "潛水員戴夫", 1332010: "浪貓 Stray", 1150690: "OMORI", 774171: "Muse Dash", 553850: "絕地戰兵 2",
}

# ---------- people ----------
# Per person: bio (≤ 200 chars), tagline (on their second photo), palette (photo colours), contacts
# (LINE / Discord / Instagram, all friends-only), privacy (categories not public), and collections:
#   anime / films: (key, tier, tag)    books: (key, status, tier, tag)
#   games: (appid, total hours, hours this month)    songs: (artist, title, plays last month, plays this month)
# Tiers: must_watch great good okay bad dropped. Book status: read reading want. Tags: app.anime per category.

PROFILES = {
    "demo_rain": dict(
        bio="每季新番必追，週末補番到天亮。最近在追藥屋和我推，喜歡聽動畫歌、看劇場版。想找可以一起開猜歌房間、聊劇情的朋友，劇透請先打預防針 🙏",
        tagline="新番雷達・J-POP", palette=("#7c3aed", "#ec4899"),
        contacts={"line": "rain_anime", "instagram": "rain.daily"}, privacy={},
        anime=[("frieren", "must_watch", "神作"), ("apothecary", "great", "好甜"), ("oshinoko", "great", "胃痛"),
               ("bocchi", "great", "笑死"), ("spyfamily", "good", "笑死"), ("dungeon", "great", "治癒"),
               ("kaguya", "good", "好甜"), ("chainsaw", "okay", "獵奇")],
        films=[("tv:66732", "good", "爆米花"), ("movie:313369", "great", "配樂神")],
        books=[("coffee", "read", "great", "療癒"), ("kitchen", "want", None, None)],
        games=[(774171, 40, 6), (1426210, 18, 0)],
        songs=[("YOASOBI", "アイドル", 15, 18), ("Creepy Nuts", "Bling-Bang-Bang-Born", 9, 12)],
    ),
    "demo_zhe": dict(
        bio="熱血番和機器人派，天元突破看了三次還是會哭。平常玩魂系受苦，晚上打 Elden Ring 打到兩點。想找人一起聊 EVA 結局、一起推坑。",
        tagline="熱血・機器人・魂系", palette=("#dc2626", "#f97316"),
        contacts={"discord": "zhe_mecha", "line": "zhe1988"}, privacy={},
        anime=[("gurren", "must_watch", "神作"), ("eva", "great", "我看了什麼"), ("codegeass", "great", "中二"),
               ("aot", "must_watch", "神作"), ("haikyu", "great", "值得二刷"), ("onepunch", "great", "笑死"),
               ("fma", "must_watch", "神作")],
        films=[("movie:155", "must_watch", "神作"), ("movie:299534", "great", "熱血"), ("movie:438631", "great", "配樂神")],
        books=[("threebody", "read", "must_watch", "燒腦"), ("dune", "reading", "great", "慢熱")],
        games=[(1245620, 280, 22), (814380, 150, 0), (374320, 120, 0)],
        songs=[("LiSA", "炎", 8, 10), ("Eve", "廻廻奇譚", 6, 7), ("King Gnu", "SPECIALZ", 10, 14)],
    ),
    "demo_hikari": dict(
        bio="日常系和音樂番都愛，孤獨搖滾讓我買了人生第一把吉他（現在在學 F 和弦）。喜歡安靜的午後、露營和熱可可。想找人一起聊、一起去看樂團表演。",
        tagline="日常系・吉他新手", palette=("#f59e0b", "#f472b6"),
        contacts={"instagram": "hikari.guitar"}, privacy={},
        anime=[("kon", "must_watch", "治癒"), ("yurucamp", "great", "治癒"), ("violet", "great", "值得二刷"),
               ("kiminitodoke", "good", "好甜"), ("natsume", "great", "治癒")],
        films=[("movie:313369", "great", "配樂神"), ("movie:354912", "must_watch", "淚崩")],
        books=[("kitchen", "read", "great", "療癒"), ("norwegian", "read", "good", "文筆好")],
        games=[(413150, 90, 6), (1332010, 12, 0)],
        songs=[("結束バンド", "ギターと孤独と蒼い惑星", 14, 18), ("結束バンド", "あのバンド", 10, 12),
               ("緑黄色社会", "Mela!", 6, 8)],
    ),
    "demo_nana": dict(
        bio="冷門番挖掘中，覺得蟲師和乒乓被嚴重低估。喜歡看完會安靜很久的作品，也讀太宰治和村上春樹。歡迎推薦你心中的冷門神作，我會認真看完。",
        tagline="冷門好作品收集家", palette=("#0f766e", "#22d3ee"),
        contacts={"line": "nana_quiet"}, privacy={"music": "friends"},
        anime=[("mushishi", "must_watch", "神作"), ("pingpong", "must_watch", "神作"), ("oddtaxi", "great", "值得二刷"),
               ("abyss", "great", "胃痛"), ("march", "great", "治癒"), ("gintama", "good", "笑死")],
        films=[("movie:545611", "great", "後勁很強"), ("movie:496243", "must_watch", "反轉")],
        books=[("nolonger", "read", "great", "後勁很強"), ("kafka", "read", "good", "燒腦"),
               ("suspectx", "read", "great", "反轉")],
        games=[(1150690, 30, 0), (391540, 20, 0)],
        songs=[("deca joins", "海浪", 12, 10), ("Radiohead", "Creep", 5, 6)],
    ),
    "demo_mochi": dict(
        bio="星露谷種田第四年，農場有 12 隻雞和一隻叫湯圓的貓。下班就是療癒時間：種田、潛水抓魚、看治癒番。週末想找人一起開多人農場，新手也歡迎！",
        tagline="種田・治癒・慢活", palette=("#65a30d", "#facc15"),
        contacts={"line": "mochi_farm", "instagram": "mochi.farmlife"}, privacy={},
        anime=[("yurucamp", "must_watch", "治癒"), ("natsume", "great", "治癒"), ("dungeon", "great", "治癒"),
               ("spyfamily", "good", "笑死")],
        films=[("movie:862", "great", "療癒"), ("movie:354912", "great", "淚崩")],
        books=[("littleprince", "read", "must_watch", "療癒"), ("coffee", "read", "good", "療癒"),
               ("atomic", "reading", "good", "長知識")],
        games=[(413150, 210, 18), (105600, 40, 0), (1868140, 35, 6)],
        songs=[("盧廣仲", "魚仔", 8, 10), ("宇多田ヒカル", "花束を君に", 5, 7)],
    ),
    "demo_kai": dict(
        bio="魂系受苦愛好者，交界地死了三百次，隻狼一周目打了兩個月。相信「再試一次」是人生哲學。想找可以一起研究 Boss 打法、交流 build 的戰友。",
        tagline="死了再試一次", palette=("#1f2937", "#b45309"),
        contacts={"discord": "kai_tarnished"}, privacy={},
        anime=[("aot", "must_watch", "神作"), ("chainsaw", "great", "獵奇"), ("jjk", "great", "值得二刷"),
               ("mob", "good", "笑死")],
        films=[("movie:155", "must_watch", "神作"), ("movie:438631", "great", "配樂神"), ("movie:157336", "great", "燒腦")],
        books=[("dune", "read", "great", "燒腦")],
        games=[(1245620, 320, 25), (367520, 60, 2), (814380, 210, 0), (374320, 180, 0)],
        songs=[("King Gnu", "SPECIALZ", 12, 15), ("米津玄師", "KICK BACK", 10, 9)],
    ),
    "demo_yuki": dict(
        bio="J-POP 重度使用者，YOASOBI 每首都會唱，KTV 必點アイドル。今年存錢目標是去東京看 Ado 的演唱會！想找人交換歌單、一起追日本歌手的新歌。",
        tagline="KTV 日文歌擔當", palette=("#db2777", "#8b5cf6"),
        contacts={"instagram": "yuki.jpop"}, privacy={},
        anime=[("oshinoko", "must_watch", "胃痛"), ("bocchi", "great", "笑死"), ("kaguya", "great", "好甜"),
               ("spyfamily", "good", "笑死"), ("yourname", "must_watch", "值得二刷")],
        films=[("movie:313369", "great", "配樂神")],
        books=[("kitchen", "want", None, None)],
        games=[(774171, 60, 8)],
        songs=[("YOASOBI", "夜に駆ける", 25, 30), ("YOASOBI", "アイドル", 22, 28), ("YOASOBI", "群青", 10, 12),
               ("Ado", "うっせぇわ", 12, 15), ("Ado", "唱", 18, 20), ("Ado", "新時代", 9, 11),
               ("ヨルシカ", "ただ君に晴れ", 8, 10), ("ヨルシカ", "言って。", 5, 6)],
    ),
    "demo_bean": dict(
        bio="下班就是要玩 Hades 一輪，Roguelite 是我的精神食糧。最近被 Balatro 偷走好多睡眠時間。也愛讀硬科幻，Project Hail Mary 是今年最愛。",
        tagline="再一輪就好", palette=("#4338ca", "#06b6d4"),
        contacts={"discord": "bean.rogue"}, privacy={"anime": "friends"},
        anime=[("onepunch", "good", "笑死"), ("steinsgate", "great", "神作")],
        films=[("movie:545611", "good", "看不懂"), ("movie:157336", "great", "燒腦")],
        books=[("hailmary", "read", "must_watch", "一口氣讀完"), ("martian", "read", "great", "笑出聲")],
        games=[(1145360, 150, 12), (646570, 45, 3), (588650, 70, 4), (1794680, 40, 5), (2379780, 60, 15)],
        songs=[("Billie Eilish", "bad guy", 6, 5)],
    ),
    "demo_lulu": dict(
        bio="演唱會常客，今年已經看了 8 場！五月天、Mrs. GREEN APPLE 都衝過。排隊買周邊很無聊，想找一起排隊、一起應援的朋友。也追動畫，最愛孤獨搖滾。",
        tagline="演唱會才是生活", palette=("#e11d48", "#fb923c"),
        contacts={"instagram": "lulu.livehouse", "line": "lulu_live"}, privacy={},
        anime=[("bocchi", "must_watch", "神作"), ("kon", "great", "治癒"), ("oshinoko", "good", "胃痛")],
        films=[("movie:313369", "must_watch", "配樂神"), ("tv:1668", "great", "笑到肚子痛")],
        books=[("normalpeople", "read", "good", "慢熱")],
        games=[(945360, 30, 2)],
        songs=[("結束バンド", "青春コンプレックス", 20, 22), ("Mrs. GREEN APPLE", "ケセラセラ", 15, 18),
               ("Mrs. GREEN APPLE", "青と夏", 12, 14), ("五月天", "派對動物", 10, 12), ("五月天", "知足", 8, 9),
               ("鄧紫棋", "光年之外", 6, 8), ("Official髭男dism", "Subtitle", 7, 9)],
    ),
    "demo_ken": dict(
        bio="經典番收藏家，星際牛仔看了五遍，EVA 新舊版都追完。家裡有一整面牆的 DVD。喜歡老電影、反烏托邦小說，聊起來會很長，請做好心理準備。",
        tagline="See you space cowboy", palette=("#78350f", "#ca8a04"),
        contacts={"line": "ken_classic"}, privacy={},
        anime=[("bebop", "must_watch", "神作"), ("eva", "great", "我看了什麼"), ("fma", "must_watch", "神作"),
               ("steinsgate", "must_watch", "神作"), ("mushishi", "great", "治癒"), ("gintama", "great", "笑死"),
               ("codegeass", "good", "中二"), ("frieren", "good", "值得二刷")],
        films=[("movie:603", "must_watch", "燒腦"), ("movie:278", "must_watch", "後勁很強"), ("movie:597", "good", "淚崩")],
        books=[("1984", "read", "great", "毛骨悚然"), ("animalfarm", "read", "good", "後勁很強")],
        games=[(292030, 140, 0)],
        songs=[("Coldplay", "Viva La Vida", 4, 5)],
    ),
    "demo_cat": dict(
        bio="養了兩隻貓的吉他手，在小樂團彈節奏吉他。愛聽台灣獨立樂團和日本搖滾，週末常去 live house。玩浪貓 Stray 時兩隻貓一直盯著螢幕看。",
        tagline="貓奴・節奏吉他", palette=("#334155", "#f472b6"),
        contacts={"instagram": "captain.cat.guitar", "discord": "captaincat"}, privacy={},
        anime=[("bocchi", "great", "笑死"), ("kon", "great", "治癒")],
        films=[("movie:313369", "great", "配樂神")],
        books=[("norwegian", "read", "great", "文筆好")],
        games=[(1332010, 10, 0), (774171, 25, 3)],
        songs=[("結束バンド", "青春コンプレックス", 10, 14), ("落日飛車", "My Jinji", 9, 12),
               ("落日飛車", "Burgundy Red", 6, 8), ("deca joins", "海浪", 7, 9), ("草東沒有派對", "山海", 8, 10),
               ("Arctic Monkeys", "Do I Wanna Know?", 5, 6)],
    ),
    "demo_jun": dict(
        bio="RPG 和策略遊戲玩家，最近在柏德之門 3 跑第二輪邪惡路線。也愛奇幻小說和影集，冰與火之歌書和劇都追完了。想找人一起討論劇情選擇和角色。",
        tagline="擲骰子決定人生", palette=("#1e3a8a", "#a855f7"),
        contacts={"discord": "jun.rpg"}, privacy={},
        anime=[("steinsgate", "great", "神作"), ("codegeass", "great", "中二"), ("frieren", "great", "值得二刷")],
        films=[("tv:1399", "great", "演技炸裂"), ("movie:438631", "great", "配樂神")],
        books=[("hobbit", "read", "great", "推坑"), ("dune", "reading", "good", "慢熱")],
        games=[(1086940, 180, 30), (1245620, 70, 0), (292030, 200, 0), (1687950, 120, 0), (2161700, 80, 10)],
        songs=[("久石譲", "Summer", 4, 5)],
    ),
    "demo_mei": dict(
        bio="通勤一小時的上班族，捷運上聽歌、週末補番。愛看甜甜的戀愛番，也愛東野圭吾。最近迷上藥屋少女的貓貓，想找人一起追番聊心得。",
        tagline="通勤族的追番日常", palette=("#be185d", "#fda4af"),
        contacts={"line": "mei_commute"}, privacy={"music": "friends"},
        anime=[("frieren", "must_watch", "神作"), ("apothecary", "must_watch", "好甜"), ("spyfamily", "great", "笑死"),
               ("kaguya", "great", "好甜"), ("haikyu", "good", "值得二刷"), ("kiminitodoke", "great", "好甜"),
               ("toradora", "great", "好甜"), ("dungeon", "good", "治癒")],
        films=[("tv:66732", "good", "爆米花"), ("tv:93405", "good", "毛骨悚然")],
        books=[("namiya", "read", "must_watch", "淚崩"), ("coffee", "read", "great", "療癒"), ("suspectx", "reading", "great", "反轉")],
        games=[(413150, 15, 0)],
        songs=[("YOASOBI", "夜に駆ける", 10, 8), ("米津玄師", "Lemon", 6, 9), ("田馥甄", "小幸運", 5, 7), ("韋禮安", "如果可以", 4, 6)],
    ),
    "demo_hao": dict(
        bio="沙盒建築派，在泰拉瑞亞蓋了一座浮空城。也玩英靈神殿，喜歡和朋友一起從零開始蓋基地。工程師一枚，看書偏好科幻和冒險。",
        tagline="一磚一瓦蓋世界", palette=("#15803d", "#0ea5e9"),
        contacts={"discord": "hao.builder", "line": "hao_build"}, privacy={},
        anime=[("onepunch", "great", "笑死"), ("dungeon", "great", "治癒"), ("fma", "good", "值得二刷")],
        films=[("movie:862", "good", "療癒"), ("movie:324857", "great", "熱血")],
        books=[("readyplayer", "read", "great", "熱血"), ("martian", "read", "good", "長知識")],
        games=[(105600, 260, 15), (413150, 55, 4), (892970, 120, 10)],
        songs=[("周杰倫", "稻香", 6, 8)],
    ),
    "demo_sora": dict(
        bio="Vaundy 和 King Gnu 的粉，什麼風格都能聽：搖滾、R&B、J-POP。喜歡有點怪的動畫和電影，奇巧計程車是我心中的神作。想找人一起去日本音樂祭。",
        tagline="音樂祭存錢中", palette=("#0e7490", "#a3e635"),
        contacts={"instagram": "sora.sounds"}, privacy={},
        anime=[("mob", "great", "值得二刷"), ("chainsaw", "great", "獵奇"), ("jjk", "good", "中二"), ("oddtaxi", "must_watch", "神作")],
        films=[("movie:545611", "must_watch", "後勁很強"), ("movie:27205", "great", "燒腦")],
        books=[("kafka", "reading", "good", "燒腦")],
        games=[(1145360, 30, 3)],
        songs=[("Vaundy", "怪獣の花唄", 22, 25), ("Vaundy", "踊り子", 15, 18), ("King Gnu", "白日", 18, 16),
               ("King Gnu", "SPECIALZ", 10, 12), ("Official髭男dism", "Pretender", 5, 7), ("藤井風", "死ぬのがいいわ", 8, 10)],
    ),
    "demo_pudding": dict(
        bio="雙人遊戲找隊友中！雙人成行、煮過頭都很想玩但缺一個人。個性很好相處、很會吵架又很會和好（遊戲裡）。也愛皮克斯動畫和韓團。",
        tagline="缺一個遊戲隊友", palette=("#f59e0b", "#ef4444"),
        contacts={"line": "pudding_coop", "discord": "puddingcoop"}, privacy={},
        anime=[("spyfamily", "great", "笑死"), ("frieren", "great", "值得二刷"), ("kaguya", "good", "好甜")],
        films=[("movie:354912", "great", "淚崩"), ("movie:862", "great", "療癒"), ("movie:324857", "great", "熱血")],
        books=[("coffee", "want", None, None)],
        games=[(1426210, 35, 6), (728880, 28, 5), (413150, 40, 3), (945360, 20, 2), (1966720, 25, 8)],
        songs=[("NewJeans", "Ditto", 12, 14), ("NewJeans", "Hype Boy", 10, 12), ("IU", "Blueming", 5, 6)],
    ),
    "demo_wen": dict(
        bio="台灣獨立樂團愛好者，草東、落日飛車、deca joins 必聽。大學念文學，喜歡太宰治和村上春樹。週末常在台南的咖啡店看書，歡迎一起去聽團。",
        tagline="獨立樂團・文學系", palette=("#44403c", "#a8a29e"),
        contacts={"instagram": "wen.indie"}, privacy={"anime": "private"},
        anime=[("pingpong", "good", "值得二刷")],
        films=[("movie:496243", "great", "反轉"), ("movie:545611", "good", "後勁很強")],
        books=[("nolonger", "read", "must_watch", "後勁很強"), ("norwegian", "read", "great", "文筆好"),
               ("kafka", "read", "good", "燒腦"), ("kitchen", "reading", "good", "療癒")],
        games=[(1150690, 25, 0)],
        songs=[("草東沒有派對", "大風吹", 30, 28), ("草東沒有派對", "山海", 18, 20), ("草東沒有派對", "爛泥", 10, 12),
               ("落日飛車", "My Jinji", 20, 24), ("deca joins", "海浪", 15, 16), ("告五人", "披星戴月的想你", 12, 15),
               ("老王樂隊", "我還年輕 我還年輕", 8, 10)],
    ),
    "demo_leo": dict(
        bio="什麼都碰一點的雜食系：動畫、遊戲、電影、小說都有涉獵但都不太深。最大的興趣是聽別人分享他們喜歡的東西。在宜蘭工作，假日常去衝浪。",
        tagline="雜食系聽眾", palette=("#0369a1", "#34d399"),
        contacts={"instagram": "leo.yilan.surf"}, privacy={},
        anime=[("mob", "good", "笑死"), ("bebop", "good", "值得二刷"), ("aot", "great", "神作"), ("frieren", "good", "治癒")],
        films=[("movie:603", "good", "燒腦"), ("tv:66732", "good", "爆米花"), ("movie:299534", "good", "爆米花")],
        books=[("alchemist", "read", "good", "療癒"), ("sapiens", "reading", "good", "長知識")],
        games=[(413150, 30, 2), (1145360, 20, 1)],
        songs=[("Coldplay", "Viva La Vida", 6, 7), ("Taylor Swift", "Love Story", 5, 6), ("The Weeknd", "Blinding Lights", 4, 5)],
    ),
    "demo_ivy": dict(
        bio="治癒系動畫和療癒遊戲收集中。在花蓮當幼教老師，下班後最愛窩在沙發看夏目友人帳。喜歡溫柔的故事、手寫信和熱茶，想交可以慢慢聊天的朋友。",
        tagline="溫柔的故事收集中", palette=("#6d28d9", "#a7f3d0"),
        contacts={"line": "ivy_hualien"}, privacy={},
        anime=[("natsume", "must_watch", "治癒"), ("frieren", "must_watch", "治癒"), ("yurucamp", "must_watch", "治癒"),
               ("bocchi", "great", "笑死"), ("violet", "great", "值得二刷"), ("mushishi", "good", "治癒")],
        films=[("movie:354912", "must_watch", "淚崩"), ("movie:862", "great", "療癒"), ("movie:313369", "good", "配樂神")],
        books=[("littleprince", "read", "must_watch", "療癒"), ("kitchen", "read", "great", "療癒"), ("coffee", "read", "great", "淚崩")],
        games=[(413150, 120, 10), (504230, 25, 0), (1332010, 8, 0)],
        songs=[("宇多田ヒカル", "First Love", 7, 9), ("ヨルシカ", "ただ君に晴れ", 5, 6), ("久石譲", "Summer", 6, 8)],
    ),
    "demo_tom": dict(
        bio="殺戮尖塔一千小時，卡牌構築和 Roguelike 的忠實信徒。平常是會計師，喜歡數字和機率，也讀行為經濟學。找人一起研究 Balatro 的高分牌組。",
        tagline="機率就是浪漫", palette=("#14532d", "#eab308"),
        contacts={"discord": "tom.deckbuilder"}, privacy={"music": "private"},
        anime=[("march", "great", "治癒"), ("steinsgate", "good", "神作"), ("onepunch", "good", "笑死")],
        films=[("movie:27205", "great", "燒腦"), ("movie:157336", "great", "燒腦")],
        books=[("fastslow", "read", "great", "燒腦"), ("sapiens", "read", "great", "長知識"), ("atomic", "read", "good", "長知識")],
        games=[(646570, 1000, 20), (1145360, 90, 4), (2379780, 150, 25), (1794680, 30, 0)],
        songs=[("Radiohead", "Creep", 3, 4)],
    ),
    "demo_ann": dict(
        bio="華語流行愛好者，周杰倫每張專輯都能從頭唱到尾，KTV 一定點晴天。偶爾看動畫電影，你的名字是入坑作。在嘉義當護理師，下班最愛唱歌紓壓。",
        tagline="KTV 華語歌后", palette=("#9d174d", "#fbbf24"),
        contacts={"line": "ann_ktv"}, privacy={},
        anime=[("yourname", "great", "值得二刷"), ("spyfamily", "good", "笑死"), ("silentvoice", "great", "胃痛")],
        films=[("movie:597", "great", "淚崩"), ("movie:313369", "good", "配樂神")],
        books=[("namiya", "read", "great", "淚崩")],
        games=[(945360, 10, 0), (413150, 8, 0)],
        songs=[("周杰倫", "晴天", 25, 30), ("周杰倫", "稻香", 12, 14), ("周杰倫", "告白氣球", 15, 18),
               ("五月天", "倔強", 15, 12), ("五月天", "知足", 8, 10), ("告五人", "披星戴月的想你", 8, 10),
               ("田馥甄", "小幸運", 10, 12), ("鄧紫棋", "光年之外", 9, 11), ("蔡依林", "日不落", 5, 6)],
    ),
    "demo_rex": dict(
        bio="魔物獵人老獵人，從 PSP 時代一路打到世界，大劍玩家。最近在絕地戰兵 2 為民主而戰。徵四人固定隊，週五晚上開車，語音聊天很吵但很歡樂。",
        tagline="徵四人固定隊", palette=("#7f1d1d", "#f59e0b"),
        contacts={"discord": "rex.hunter", "line": "rex_mh"}, privacy={},
        anime=[("aot", "great", "神作"), ("demonslayer", "great", "值得二刷"), ("onepunch", "great", "笑死")],
        films=[("movie:299534", "great", "熱血"), ("movie:155", "great", "演技炸裂")],
        books=[("martian", "read", "great", "笑出聲")],
        games=[(582010, 600, 12), (1245620, 150, 8), (553850, 90, 20)],
        songs=[("LiSA", "紅蓮華", 6, 8), ("LiSA", "炎", 4, 5)],
    ),
    "demo_hana": dict(
        bio="動畫歌曲收藏中，最愛 LiSA 和 Aimer 的聲音。每季都會先聽 OP/ED 決定要不要追。RADWIMPS 的新海誠電影歌單循環中。想找人交換動畫歌歌單。",
        tagline="OP 決定追不追", palette=("#c026d3", "#38bdf8"),
        contacts={"instagram": "hana.anisong"}, privacy={},
        anime=[("demonslayer", "must_watch", "神作"), ("yourname", "must_watch", "值得二刷"), ("violet", "great", "值得二刷"),
               ("jjk", "great", "中二"), ("frieren", "great", "神作"), ("bocchi", "good", "笑死")],
        films=[("movie:313369", "good", "配樂神")],
        books=[("kitchen", "want", None, None)],
        games=[(774171, 80, 10), (2161700, 40, 5)],
        songs=[("LiSA", "紅蓮華", 18, 20), ("LiSA", "炎", 12, 14), ("Aimer", "残響散歌", 20, 22), ("Aimer", "カタオモイ", 10, 12),
               ("RADWIMPS", "前前前世", 9, 11), ("RADWIMPS", "すずめ", 8, 10), ("Eve", "廻廻奇譚", 7, 9),
               ("YOASOBI", "夜に駆ける", 6, 5)],
    ),
    "demo_owen": dict(
        bio="剛開始玩 Undertale，求不劇透！大學一年級，資工系，正在把朋友推薦的獨立遊戲一款一款玩完。哈利波特是童年回憶，也剛開始看動畫。",
        tagline="獨立遊戲新手村", palette=("#1d4ed8", "#facc15"),
        contacts={"discord": "owen.newbie"}, privacy={},
        anime=[("onepunch", "good", "笑死"), ("spyfamily", "good", "笑死")],
        films=[("movie:862", "good", "療癒")],
        books=[("harrypotter", "read", "great", "推坑")],
        games=[(391540, 8, 8), (367520, 15, 3), (1150690, 5, 5), (504230, 12, 2)],
        songs=[("RADWIMPS", "前前前世", 4, 6)],
    ),
}

# Second helpings: more of each category, still to each person's taste, so no profile looks thin.
_MORE = {
    "demo_rain": dict(films=[("movie:324857", "great", "熱血")], books=[("namiya", "reading", "great", "淚崩")],
                      games=[(945360, 15, 2)], songs=[("ヨルシカ", "言って。", 6, 8), ("Ado", "新時代", 7, 9)]),
    "demo_zhe": dict(books=[("martian", "read", "great", "熱血")], songs=[("RADWIMPS", "前前前世", 3, 5)]),
    "demo_hikari": dict(films=[("movie:862", "good", "療癒")], books=[("coffee", "read", "great", "療癒")],
                        games=[(774171, 15, 2)]),
    "demo_nana": dict(films=[("movie:278", "great", "後勁很強")], games=[(504230, 18, 0)],
                      songs=[("草東沒有派對", "爛泥", 4, 5)]),
    "demo_mochi": dict(films=[("movie:313369", "good", "配樂神")],
                       songs=[("久石譲", "Summer", 4, 6), ("田馥甄", "小幸運", 3, 4)]),
    "demo_kai": dict(books=[("threebody", "read", "great", "燒腦"), ("1984", "want", None, None)],
                     songs=[("LiSA", "紅蓮華", 5, 6)]),
    "demo_yuki": dict(films=[("tv:1668", "good", "笑到肚子痛"), ("movie:324857", "great", "配樂神")],
                      books=[("namiya", "read", "great", "淚崩")], games=[(2161700, 35, 4), (1426210, 12, 0)]),
    "demo_bean": dict(anime=[("chainsaw", "great", "獵奇")], films=[("movie:27205", "great", "燒腦")],
                      songs=[("Arctic Monkeys", "Do I Wanna Know?", 4, 5), ("Radiohead", "Creep", 2, 3)]),
    "demo_lulu": dict(films=[("movie:354912", "great", "淚崩")],
                      books=[("coffee", "read", "good", "療癒"), ("namiya", "want", None, None)],
                      games=[(1426210, 20, 3), (1966720, 10, 4)]),
    "demo_ken": dict(books=[("alchemist", "read", "good", "值得重讀")], games=[(814380, 90, 0), (374320, 60, 0)],
                     songs=[("Radiohead", "Creep", 5, 6), ("宇多田ヒカル", "First Love", 3, 4)]),
    "demo_cat": dict(anime=[("oddtaxi", "great", "值得二刷")],
                     films=[("movie:545611", "great", "後勁很強"), ("tv:1668", "good", "笑到肚子痛")],
                     books=[("kafka", "reading", "good", "燒腦")], games=[(1150690, 14, 0)]),
    "demo_jun": dict(anime=[("fma", "great", "值得二刷")], films=[("tv:1396", "must_watch", "演技炸裂")],
                     songs=[("Official髭男dism", "Pretender", 3, 4), ("King Gnu", "白日", 2, 3)]),
    "demo_mei": dict(films=[("tv:1668", "great", "笑到肚子痛")], games=[(1426210, 10, 2)]),
    "demo_hao": dict(films=[("movie:157336", "great", "燒腦")], books=[("hobbit", "reading", "good", "推坑")],
                     songs=[("五月天", "倔強", 4, 5), ("周杰倫", "晴天", 3, 4)]),
    "demo_sora": dict(films=[("movie:313369", "good", "配樂神")],
                      books=[("nolonger", "read", "good", "後勁很強"), ("suspectx", "want", None, None)],
                      games=[(1332010, 9, 0), (1966720, 14, 3)]),
    "demo_pudding": dict(books=[("littleprince", "read", "great", "療癒"), ("harrypotter", "read", "good", "推坑")]),
    "demo_wen": dict(anime=[("march", "great", "治癒"), ("mushishi", "good", "治癒")],
                     films=[("movie:313369", "good", "配樂神")], games=[(1332010, 6, 0), (391540, 12, 0)]),
    "demo_leo": dict(games=[(945360, 8, 0)]),
    "demo_tom": dict(films=[("movie:872585", "great", "演技炸裂")],
                     songs=[("久石譲", "Summer", 2, 3), ("Coldplay", "Viva La Vida", 2, 2)]),
    "demo_ann": dict(films=[("tv:93405", "good", "毛骨悚然")],
                     books=[("coffee", "read", "good", "療癒"), ("kitchen", "want", None, None)]),
    "demo_rex": dict(films=[("movie:438631", "great", "配樂神")],
                     books=[("hailmary", "reading", "great", "一口氣讀完"), ("dune", "want", None, None)],
                     songs=[("King Gnu", "SPECIALZ", 4, 5)]),
    "demo_hana": dict(films=[("movie:354912", "great", "淚崩"), ("tv:66732", "good", "爆米花")],
                      books=[("namiya", "read", "great", "淚崩"), ("coffee", "reading", "good", "療癒")]),
    "demo_owen": dict(anime=[("frieren", "good", "值得二刷")],
                      films=[("movie:324857", "great", "熱血"), ("tv:66732", "good", "毛骨悚然")],
                      books=[("hobbit", "reading", "good", "推坑")], songs=[("YOASOBI", "群青", 3, 4), ("Eve", "廻廻奇譚", 2, 3)]),
}
for _username, _extra in _MORE.items():
    for _category, _items in _extra.items():
        PROFILES[_username][_category] = PROFILES[_username][_category] + _items


# =====================================================================================================
# Bigger collections: every person gets 30+ items in each category, picked from the pools below by
# their taste (TASTES), so a J-POP fan's 50 songs look nothing like a 華語 fan's 50. Their hand-picked
# favourites above come first; the rest is filled in deterministically (same result on every seed).
# =====================================================================================================

import random  # noqa: E402

def _split(text: str) -> list[str]:
    return [t.strip() for t in text.split("|") if t.strip()]

# anime: AniList search text by style
ANIME_POOL = {k: _split(v) for k, v in {
    "new": "Frieren|The Apothecary Diaries|Oshi no Ko|Delicious in Dungeon|Solo Leveling|Kaiju No. 8|Dandadan|Blue Lock|"
           "Spy x Family|Chainsaw Man|Bocchi the Rock|Lycoris Recoil|Skip and Loafer|The Dangers in My Heart|Pluto|"
           "Heavenly Delusion|Undead Unluck|Wind Breaker|Mashle|Hell's Paradise|Zom 100|Shangri-La Frontier|Too Many Losing Heroines",
    "healing": "Natsume's Book of Friends|Laid-Back Camp|Mushishi|Aria the Animation|Non Non Biyori|Barakamon|Flying Witch|"
               "March Comes in Like a Lion|Violet Evergarden|Silver Spoon|Somali and the Forest Spirit|Wolf Children|"
               "Spirited Away|My Neighbor Totoro|Kiki's Delivery Service|Hidamari Sketch|Sweetness and Lightning",
    "comedy": "Gintama|Kaguya-sama: Love is War|Grand Blue|Daily Lives of High School Boys|Nichijou|The Disastrous Life of Saiki K.|"
              "Konosuba|One Punch Man|Mob Psycho 100|Asobi Asobase|Tanaka-kun is Always Listless|Hinamatsuri",
    "action": "Jujutsu Kaisen|Attack on Titan|Demon Slayer|My Hero Academia|Hunter x Hunter (2011)|"
              "Fullmetal Alchemist: Brotherhood|Naruto Shippuden|One Piece|Bleach: Thousand-Year Blood War|Fire Force|"
              "Black Clover|Vinland Saga|Dororo|Akame ga Kill|Tokyo Revengers",
    "scifi": "Neon Genesis Evangelion|Gurren Lagann|Code Geass|Steins;Gate|Cowboy Bebop|Ghost in the Shell: Stand Alone Complex|"
             "Psycho-Pass|86|Mobile Suit Gundam: The Witch from Mercury|Darling in the Franxx|Planetes|Cyberpunk: Edgerunners|"
             "Space Brothers|Akira|Mobile Suit Gundam 00",
    "romance": "Toradora!|Kimi ni Todoke|Your Name|A Silent Voice|Horimiya|Clannad: After Story|Your Lie in April|"
               "Weathering with You|Tsuki ga Kirei|My Dress-Up Darling|Fruits Basket|Ouran High School Host Club|"
               "Rascal Does Not Dream of Bunny Girl Senpai|Nisekoi",
    "music": "K-On!|Given|Nodame Cantabile|Carole & Tuesday|Love Live! School Idol Project|Sound! Euphonium|Beck|"
             "Girls Band Cry|Kids on the Slope",
    "dark": "Made in Abyss|Death Note|Monster|Paranoia Agent|Perfect Blue|The Promised Neverland|Erased|Parasyte|"
            "Tokyo Ghoul|Higurashi: When They Cry|Odd Taxi|Serial Experiments Lain",
    "sports": "Haikyu!!|Kuroko's Basketball|Slam Dunk|Ping Pong the Animation|Yuri on Ice|Run with the Wind|"
              "Hajime no Ippo|Free!|Major|Ace of Diamond|The Prince of Tennis",
    "fantasy": "Mushoku Tensei|Re:Zero|That Time I Got Reincarnated as a Slime|Ascendance of a Bookworm|Overlord|"
               "The Rising of the Shield Hero|Sword Art Online|Magi: The Labyrinth of Magic|The Ancient Magus' Bride|Log Horizon",
    "classic": "Sailor Moon|Dragon Ball Z|Rurouni Kenshin|Great Teacher Onizuka|Detective Conan|InuYasha|"
               "Cardcaptor Sakura|Trigun|Samurai Champloo|Hikaru no Go",
}.items()}

# films and series: TMDB search text (needs TMDB_API_KEY), with movie / tv
FILM_POOL = {k: [(t, kind) for t in _split(v)] for k, v, kind in (
    ("blockbuster", "The Avengers|Avengers: Infinity War|Iron Man|Spider-Man: No Way Home|Top Gun: Maverick|Jurassic Park|"
                    "Avatar|Mission: Impossible - Fallout|Furious 7|Star Wars|The Lord of the Rings: The Fellowship of the Ring|"
                    "Harry Potter and the Philosopher's Stone|Pirates of the Caribbean: The Curse of the Black Pearl|"
                    "Guardians of the Galaxy|Black Panther|John Wick|Mad Max: Fury Road", "movie"),
    ("mind", "Tenet|Arrival|Blade Runner 2049|Dune: Part Two|The Prestige|Memento|Shutter Island|Ex Machina|Gravity|"
             "The Truman Show|Inception|Interstellar|The Matrix|Oppenheimer", "movie"),
    ("drama", "Forrest Gump|The Godfather|Schindler's List|Whiplash|The Social Network|Joker|Green Book|12 Angry Men|"
              "The Pursuit of Happyness|Good Will Hunting|Dead Poets Society|The Intouchables|The Shawshank Redemption", "movie"),
    ("romance", "About Time|Before Sunrise|Notting Hill|The Notebook|Pride & Prejudice|Love Actually|Call Me by Your Name|"
                "Eternal Sunshine of the Spotless Mind|Amélie|500 Days of Summer|Crazy Rich Asians|La La Land|Titanic", "movie"),
    ("family", "Up|Inside Out|Zootopia|Spider-Man: Across the Spider-Verse|Finding Nemo|WALL·E|Ratatouille|Frozen|Encanto|"
               "Paddington 2|Shrek|The Lion King|Toy Story|Coco", "movie"),
    ("asian", "那些年，我們一起追的女孩|我的少女時代|返校|孤味|誰先愛上他的|海角七號|陽光普照|周處除三害|"
              "關於我和鬼變成家人的那件事|霸王別姬|花樣年華|無間道|少林足球|Train to Busan|Oldboy|Shoplifters|"
              "Drive My Car|Memories of Murder|Departures", "movie"),
    ("horror", "Get Out|Hereditary|A Quiet Place|The Conjuring|Se7en|Gone Girl|The Silence of the Lambs|It|Us|Midsommar|"
               "Knives Out|Prisoners|Zodiac", "movie"),
    ("series_west", "The Office|Sherlock|Black Mirror|The Crown|Wednesday|The Last of Us|Arcane|House of the Dragon|"
                    "Money Heist|Dark|Peaky Blinders|Brooklyn Nine-Nine|The Mandalorian|Chernobyl|Stranger Things|"
                    "Breaking Bad|Game of Thrones|Friends", "tv"),
    ("series_asia", "Crash Landing on You|Reply 1988|Extraordinary Attorney Woo|The Glory|Alice in Borderland|想見你|"
                    "誰是被害者|華燈初上|茶金|Squid Game|Moving|Twinkling Watermelon", "tv"),
)}

# books: search text (original titles find the right work most often)
BOOK_POOL = {k: _split(v) for k, v in {
    "classic": "The Little Prince|Nineteen Eighty-Four Orwell|Animal Farm Orwell|To Kill a Mockingbird|The Great Gatsby|"
               "Pride and Prejudice Austen|Jane Eyre|The Catcher in the Rye|Brave New World|One Hundred Years of Solitude|"
               "The Old Man and the Sea|Crime and Punishment|Les Misérables|Frankenstein Shelley|Wuthering Heights",
    "japanese": "Norwegian Wood Murakami|Kafka on the Shore|1Q84|No Longer Human Dazai|Kitchen Banana Yoshimoto|"
                "Convenience Store Woman|Before the Coffee Gets Cold|The Miracles of the Namiya General Store|"
                "The Devotion of Suspect X|Malice Higashino|The Travelling Cat Chronicles|I Want to Eat Your Pancreas|"
                "Colorless Tsukuru Tazaki|Strange Weather in Tokyo|Kokoro Natsume Soseki|Snow Country Kawabata",
    "scifi": "The Three-Body Problem|The Dark Forest Liu Cixin|Death's End Liu Cixin|Dune Frank Herbert|Project Hail Mary|"
             "The Martian Andy Weir|Foundation Asimov|Ender's Game|Neuromancer|Do Androids Dream of Electric Sheep|"
             "The Hitchhiker's Guide to the Galaxy|Klara and the Sun|Never Let Me Go|Ready Player One|Fahrenheit 451|"
             "Recursion Blake Crouch",
    "fantasy": "The Hobbit|The Fellowship of the Ring|Harry Potter and the Philosopher's Stone|"
               "Harry Potter and the Prisoner of Azkaban|A Game of Thrones Martin|The Name of the Wind|"
               "Mistborn The Final Empire|The Lion, the Witch and the Wardrobe|American Gods|Good Omens|The Night Circus|"
               "Howl's Moving Castle Diana Wynne Jones|Coraline|The Ocean at the End of the Lane",
    "mystery": "And Then There Were None|Murder on the Orient Express|The Girl with the Dragon Tattoo|Gone Girl Flynn|"
               "The Da Vinci Code|A Study in Scarlet|The Silent Patient|Big Little Lies|The Girl on the Train|"
               "The Hound of the Baskervilles|Rebecca du Maurier|Shutter Island Lehane",
    "selfhelp": "Atomic Habits|The Courage to Be Disliked|Thinking, Fast and Slow|Man's Search for Meaning|"
                "The 7 Habits of Highly Effective People|Deep Work Newport|The Subtle Art of Not Giving|Ikigai|"
                "Mindset Carol Dweck|Grit Angela Duckworth|The Power of Habit|Quiet Susan Cain|"
                "How to Win Friends and Influence People",
    "nonfiction": "Sapiens Harari|Homo Deus|Guns, Germs, and Steel|A Brief History of Time|Educated Tara Westover|"
                  "Steve Jobs Isaacson|Freakonomics|The Selfish Gene|Factfulness|Outliers Gladwell|Becoming Michelle Obama|"
                  "Into the Wild Krakauer|The Immortal Life of Henrietta Lacks|Silent Spring",
    "contemporary": "Normal People Sally Rooney|Me Before You|The Fault in Our Stars|Where the Crawdads Sing|"
                    "Eleanor Oliphant Is Completely Fine|The Kite Runner|A Man Called Ove|The Midnight Library|"
                    "Tomorrow, and Tomorrow, and Tomorrow|Pachinko Min Jin Lee|Little Fires Everywhere|"
                    "The Perks of Being a Wallflower|Wonder Palacio|The Book Thief",
}.items()}

# games: Steam store names (looked up on the Steam store, which gives the appid and the Chinese name)
GAME_POOL = {k: _split(v) for k, v in {
    "cozy": "Stardew Valley|Unpacking|A Short Hike|Spiritfarer|Coral Island|Dorfromantik|Slime Rancher|Littlewood|"
            "Garden Story|Wylde Flowers|PowerWash Simulator|Potion Craft|My Time at Portia|Sun Haven|Cozy Grove",
    "souls": "ELDEN RING|Sekiro: Shadows Die Twice|DARK SOULS III|Hollow Knight|Lies of P|Black Myth: Wukong|"
             "Monster Hunter: World|Monster Hunter Rise|Nioh 2|Devil May Cry 5|God of War|Ghost of Tsushima|"
             "ARMORED CORE VI FIRES OF RUBICON",
    "rpg": "Baldur's Gate 3|The Witcher 3: Wild Hunt|Persona 5 Royal|Persona 3 Reload|FINAL FANTASY VII REMAKE INTERGRADE|"
           "Divinity: Original Sin 2|Cyberpunk 2077|OCTOPATH TRAVELER|DRAGON QUEST XI S|Disco Elysium|Sea of Stars|"
           "Chained Echoes|Metaphor: ReFantazio|Like a Dragon: Infinite Wealth|NieR:Automata",
    "roguelite": "Hades|Hades II|Slay the Spire|Balatro|Dead Cells|Vampire Survivors|The Binding of Isaac: Rebirth|"
                 "Risk of Rain 2|Inscryption|Monster Train|Enter the Gungeon|Brotato|Noita|Cult of the Lamb",
    "sandbox": "Terraria|Valheim|Don't Starve Together|Subnautica|Factorio|RimWorld|Satisfactory|Palworld|The Forest|"
               "Sons Of The Forest|Raft|Grounded|Core Keeper|7 Days to Die",
    "coop": "It Takes Two|Overcooked! 2|Among Us|Lethal Company|Phasmophobia|Fall Guys|Unravel Two|PICO PARK|"
            "Deep Rock Galactic|HELLDIVERS 2|Left 4 Dead 2|Portal 2|Moving Out|Content Warning|PlateUp!",
    "indie": "Undertale|OMORI|Celeste|Stray|DAVE THE DIVER|Outer Wilds|GRIS|Ori and the Will of the Wisps|INSIDE|LIMBO|"
             "Firewatch|What Remains of Edith Finch|Night in the Woods|Oxenfree|To the Moon|Cuphead|"
             "Return of the Obra Dinn|Papers, Please|Doki Doki Literature Club",
    "competitive": "Counter-Strike 2|Dota 2|Apex Legends|PUBG: BATTLEGROUNDS|Rocket League|Overwatch 2|NARAKA: BLADEPOINT|"
                   "Tom Clancy's Rainbow Six Siege|Team Fortress 2|Warframe|Destiny 2|Marvel Rivals",
    "rhythm": "Muse Dash|Hi-Fi RUSH|Beat Saber|Rhythm Doctor|Crypt of the NecroDancer|Sayonara Wild Hearts|Thumper|"
              "A Dance of Fire and Ice|Taiko no Tatsujin: Rhythm Festival|Just Shapes & Beats",
    "strategy": "Sid Meier's Civilization VI|Cities: Skylines|Stellaris|Crusader Kings III|XCOM 2|"
                "Total War: WARHAMMER III|Two Point Hospital|Planet Zoo|Frostpunk|Into the Breach|"
                "Age of Empires II: Definitive Edition|The Sims 4|Euro Truck Simulator 2",
    "horror": "Resident Evil 4|Resident Evil Village|Dead by Daylight|Outlast|Little Nightmares|Detention|"
              "Amnesia: The Bunker|SOMA|The Last of Us Part I|SILENT HILL 2",
}.items()}

# songs: (artist, title) by style
SONG_POOL = {k: [tuple(x.split("/", 1)) for x in _split(v)] for k, v in {
    "jpop": "YOASOBI/夜に駆ける|YOASOBI/アイドル|YOASOBI/群青|YOASOBI/怪物|YOASOBI/祝福|YOASOBI/ハルジオン|Ado/うっせぇわ|"
            "Ado/唱|Ado/新時代|Ado/踊|ヨルシカ/ただ君に晴れ|ヨルシカ/言って。|ヨルシカ/だから僕は音楽を辞めた|ヨルシカ/晴る|"
            "米津玄師/Lemon|米津玄師/KICK BACK|米津玄師/感電|米津玄師/地球儀|米津玄師/馬と鹿|Official髭男dism/Pretender|"
            "Official髭男dism/Subtitle|Official髭男dism/ミックスナッツ|King Gnu/白日|King Gnu/SPECIALZ|King Gnu/一途|"
            "Vaundy/怪獣の花唄|Vaundy/踊り子|Vaundy/東京フラッシュ|Mrs. GREEN APPLE/ケセラセラ|Mrs. GREEN APPLE/青と夏|"
            "Mrs. GREEN APPLE/ダンスホール|Mrs. GREEN APPLE/ライラック|藤井風/死ぬのがいいわ|藤井風/きらり|藤井風/まつり|"
            "あいみょん/マリーゴールド|あいみょん/君はロックを聴かない|あいみょん/ハルノヒ|back number/高嶺の花子さん|"
            "back number/水平線|宇多田ヒカル/First Love|宇多田ヒカル/花束を君に|宇多田ヒカル/One Last Kiss|"
            "Creepy Nuts/Bling-Bang-Bang-Born|Creepy Nuts/オトノケ|緑黄色社会/Mela!|ずっと真夜中でいいのに。/秒針を噛む|"
            "ずっと真夜中でいいのに。/残機|tuki./晩餐歌|RADWIMPS/前前前世|RADWIMPS/スパークル|RADWIMPS/なんでもないや",
    "anisong": "LiSA/紅蓮華|LiSA/炎|LiSA/明け星|Aimer/残響散歌|Aimer/カタオモイ|Aimer/蝶々結び|Eve/廻廻奇譚|Eve/心予報|"
               "RADWIMPS/すずめ|結束バンド/青春コンプレックス|結束バンド/ギターと孤独と蒼い惑星|結束バンド/あのバンド|"
               "結束バンド/星座になれたら|Linked Horizon/紅蓮の弓矢|MAN WITH A MISSION/Raise your flag|SiM/The Rumbling|"
               "Survive Said The Prophet/Mukanjyo|Uru/アンビバレント|milet/Anytime Anywhere|星街すいせい/Stellar Stellar|"
               "TK from 凛として時雨/unravel|fripSide/only my railgun|SPYAIR/オレンジ|KANA-BOON/シルエット",
    "mandopop": "周杰倫/晴天|周杰倫/稻香|周杰倫/告白氣球|周杰倫/七里香|周杰倫/青花瓷|周杰倫/夜曲|周杰倫/簡單愛|周杰倫/說好不哭|"
                "五月天/倔強|五月天/知足|五月天/派對動物|五月天/突然好想你|五月天/溫柔|五月天/頑固|田馥甄/小幸運|"
                "田馥甄/魔鬼中的天使|鄧紫棋/光年之外|鄧紫棋/泡沫|鄧紫棋/句號|蔡依林/日不落|蔡依林/玫瑰少年|蔡依林/怪美的|"
                "林俊傑/江南|林俊傑/修煉愛情|林俊傑/不為誰而作的歌|韋禮安/如果可以|盧廣仲/刻在我心底的名字|孫燕姿/遇見|"
                "孫燕姿/天黑黑|張惠妹/聽海|陳奕迅/十年|陳奕迅/富士山下|陳奕迅/孤勇者|蕭敬騰/王妃|楊丞琳/曖昧|周興哲/你，好不好？|"
                "李榮浩/年少有為|毛不易/消愁|薛之謙/演員|徐佳瑩/身騎白馬|李宗盛/山丘",
    "twindie": "草東沒有派對/大風吹|草東沒有派對/山海|草東沒有派對/爛泥|草東沒有派對/情歌|落日飛車/My Jinji|"
               "落日飛車/Burgundy Red|deca joins/海浪|deca joins/浴室|老王樂隊/我還年輕 我還年輕|茄子蛋/浪子回頭|"
               "茄子蛋/這款自作多情|甜約翰/Kiss Me|傻子與白痴/那些我愛過的人|康士坦的變化球/美好的事可不可以發生在我身上|"
               "滅火器/島嶼天光|美秀集團/電火王|宇宙人/一起去跑步|鄭宜農/玉仔的心|告五人/披星戴月的想你|告五人/愛人錯過|"
               "告五人/唯一|盧廣仲/魚仔|魏如萱/不會不愛",
    "kpop": "NewJeans/Ditto|NewJeans/Hype Boy|NewJeans/OMG|NewJeans/Super Shy|BTS/Dynamite|BTS/Butter|BTS/Spring Day|"
            "IU/Blueming|IU/Good Day|IU/Love wins all|TWICE/TT|TWICE/What is Love?|TWICE/Feel Special|"
            "BLACKPINK/DDU-DU DDU-DU|BLACKPINK/Pink Venom|BLACKPINK/How You Like That|IVE/LOVE DIVE|IVE/I AM|"
            "aespa/Next Level|aespa/Supernova|LE SSERAFIM/ANTIFRAGILE|(G)I-DLE/Queencard|BIGBANG/BANG BANG BANG",
    "western": "Taylor Swift/Love Story|Taylor Swift/Anti-Hero|Taylor Swift/Shake It Off|Taylor Swift/Cruel Summer|"
               "Ed Sheeran/Shape of You|Ed Sheeran/Perfect|The Weeknd/Blinding Lights|The Weeknd/Starboy|Billie Eilish/bad guy|"
               "Billie Eilish/BIRDS OF A FEATHER|Billie Eilish/What Was I Made For?|Coldplay/Viva La Vida|Coldplay/Yellow|"
               "Coldplay/The Scientist|Mark Ronson/Uptown Funk|Bruno Mars/Just the Way You Are|Olivia Rodrigo/drivers license|"
               "Olivia Rodrigo/good 4 u|Dua Lipa/Levitating|Harry Styles/As It Was|Adele/Someone Like You|Adele/Easy On Me|"
               "Imagine Dragons/Believer|Maroon 5/Sugar|Sabrina Carpenter/Espresso|Lady Gaga/Shallow",
    "rock": "Radiohead/Creep|Radiohead/Karma Police|Arctic Monkeys/Do I Wanna Know?|Arctic Monkeys/505|Oasis/Wonderwall|"
            "Oasis/Don't Look Back in Anger|Linkin Park/Numb|Linkin Park/In the End|Nirvana/Smells Like Teen Spirit|"
            "Queen/Bohemian Rhapsody|The Beatles/Hey Jude|The Beatles/Let It Be|Green Day/Boulevard of Broken Dreams|"
            "The Strokes/Last Nite|Muse/Uprising|Red Hot Chili Peppers/Californication|ONE OK ROCK/The Beginning|"
            "ONE OK ROCK/Wherever you are",
    "citypop_jazz": "久石譲/Summer|久石譲/あの夏へ|坂本龍一/Merry Christmas Mr. Lawrence|Bill Evans/Waltz for Debby|"
                    "Chet Baker/My Funny Valentine|Norah Jones/Don't Know Why|Yiruma/River Flows in You|"
                    "Ludovico Einaudi/Nuvole Bianche|Claude Debussy/Clair de lune|Nujabes/Aruarian Dance|Nujabes/Feather|"
                    "竹内まりや/Plastic Love|山下達郎/クリスマス・イブ|山下達郎/Ride on Time|松原みき/真夜中のドア|"
                    "大貫妙子/4:00A.M.|杏里/悲しみがとまらない",
}.items()}

# Each person's taste: weight 0–3 per style (missing = 0, still possible but rare), and extra items for
# the categories they care most about. Categories: anime films books games songs.
_ALL = 1.5
TASTES = {
    "demo_rain": dict(anime={"new": 3, "romance": 2, "comedy": 2, "music": 1}, films={"series_asia": 1, "romance": 1, "blockbuster": 1},
                      books={"contemporary": 1, "japanese": 1}, games={"rhythm": 2, "coop": 1, "cozy": 1},
                      songs={"jpop": 3, "anisong": 2}, extra={"anime": 15}),
    "demo_zhe": dict(anime={"action": 3, "scifi": 3, "classic": 2, "sports": 1}, films={"blockbuster": 3, "mind": 2},
                     books={"scifi": 3, "fantasy": 1}, games={"souls": 3, "rpg": 2, "competitive": 1},
                     songs={"anisong": 2, "rock": 2, "jpop": 1}, extra={"anime": 10}),
    "demo_hikari": dict(anime={"healing": 3, "music": 3, "romance": 1}, films={"romance": 2, "family": 2},
                        books={"japanese": 2, "contemporary": 2}, games={"cozy": 3, "indie": 2, "rhythm": 1},
                        songs={"jpop": 2, "twindie": 1, "anisong": 2, "citypop_jazz": 1}, extra={}),
    "demo_nana": dict(anime={"dark": 3, "classic": 2, "healing": 2, "scifi": 1}, films={"asian": 3, "drama": 2, "mind": 2},
                      books={"japanese": 3, "classic": 2, "mystery": 2}, games={"indie": 3, "horror": 1},
                      songs={"twindie": 2, "rock": 2, "citypop_jazz": 2}, extra={"books": 10}),
    "demo_mochi": dict(anime={"healing": 3, "fantasy": 1, "comedy": 1}, films={"family": 3, "romance": 1},
                       books={"selfhelp": 2, "contemporary": 2, "japanese": 1}, games={"cozy": 3, "sandbox": 2},
                       songs={"mandopop": 2, "citypop_jazz": 2, "jpop": 1}, extra={"games": 10}),
    "demo_kai": dict(anime={"action": 3, "dark": 2}, films={"blockbuster": 2, "mind": 2, "horror": 1},
                     books={"scifi": 2, "fantasy": 2}, games={"souls": 3, "roguelite": 1, "horror": 1},
                     songs={"rock": 2, "anisong": 2, "jpop": 1}, extra={"games": 10}),
    "demo_yuki": dict(anime={"new": 2, "music": 2, "romance": 2}, films={"romance": 2, "series_asia": 1},
                      books={"japanese": 2, "contemporary": 1}, games={"rhythm": 3, "coop": 1},
                      songs={"jpop": 3, "anisong": 2, "citypop_jazz": 1}, extra={"songs": 25}),
    "demo_bean": dict(anime={"comedy": 2, "scifi": 2}, films={"mind": 3, "blockbuster": 1},
                      books={"scifi": 3, "nonfiction": 1}, games={"roguelite": 3, "indie": 2},
                      songs={"western": 2, "rock": 2}, extra={"games": 15}),
    "demo_lulu": dict(anime={"music": 3, "new": 1}, films={"romance": 2, "series_west": 2, "series_asia": 1},
                      books={"contemporary": 2}, games={"coop": 2, "rhythm": 2},
                      songs={"jpop": 2, "mandopop": 2, "kpop": 2, "twindie": 1}, extra={"songs": 20}),
    "demo_ken": dict(anime={"classic": 3, "scifi": 3, "dark": 1}, films={"drama": 3, "mind": 2, "blockbuster": 1},
                     books={"classic": 3, "scifi": 2}, games={"rpg": 2, "souls": 1, "strategy": 1},
                     songs={"citypop_jazz": 3, "rock": 2, "western": 1}, extra={"anime": 15, "films": 10}),
    "demo_cat": dict(anime={"music": 2, "comedy": 1, "healing": 1}, films={"romance": 1, "drama": 1, "series_west": 1},
                     books={"japanese": 2, "contemporary": 1}, games={"indie": 2, "cozy": 2, "rhythm": 1},
                     songs={"twindie": 3, "rock": 3, "jpop": 1}, extra={"songs": 15}),
    "demo_jun": dict(anime={"fantasy": 2, "scifi": 2, "classic": 1}, films={"series_west": 3, "blockbuster": 2},
                     books={"fantasy": 3, "scifi": 2}, games={"rpg": 3, "strategy": 2},
                     songs={"citypop_jazz": 2, "western": 1}, extra={"games": 10, "books": 10}),
    "demo_mei": dict(anime={"romance": 3, "new": 2, "comedy": 2}, films={"series_asia": 2, "romance": 2},
                     books={"japanese": 2, "mystery": 2, "contemporary": 1}, games={"cozy": 1, "coop": 1},
                     songs={"mandopop": 2, "jpop": 2}, extra={"anime": 15}),
    "demo_hao": dict(anime={"comedy": 2, "action": 1, "fantasy": 1}, films={"family": 2, "blockbuster": 2},
                     books={"scifi": 2, "nonfiction": 2}, games={"sandbox": 3, "coop": 2, "strategy": 2},
                     songs={"mandopop": 2, "western": 1}, extra={"games": 10}),
    "demo_sora": dict(anime={"dark": 2, "scifi": 2, "music": 1}, films={"mind": 3, "asian": 1},
                      books={"japanese": 2, "contemporary": 1}, games={"indie": 2, "rhythm": 1},
                      songs={"jpop": 3, "rock": 2, "western": 1}, extra={"songs": 15}),
    "demo_pudding": dict(anime={"comedy": 2, "romance": 1}, films={"family": 3, "series_asia": 1},
                         books={"contemporary": 2, "fantasy": 1}, games={"coop": 3, "cozy": 2},
                         songs={"kpop": 3, "jpop": 1}, extra={"games": 10}),
    "demo_wen": dict(anime={"healing": 1, "dark": 1, "classic": 1}, films={"asian": 3, "drama": 2},
                     books={"japanese": 3, "classic": 3, "contemporary": 2}, games={"indie": 2, "horror": 1},
                     songs={"twindie": 3, "rock": 1, "mandopop": 1}, extra={"books": 15, "songs": 10}),
    "demo_leo": dict(anime=dict.fromkeys(ANIME_POOL, _ALL), films=dict.fromkeys(FILM_POOL, _ALL),
                     books=dict.fromkeys(BOOK_POOL, _ALL), games=dict.fromkeys(GAME_POOL, _ALL),
                     songs=dict.fromkeys(SONG_POOL, _ALL), extra={}),
    "demo_ivy": dict(anime={"healing": 3, "fantasy": 1, "romance": 1}, films={"family": 3, "romance": 2},
                     books={"contemporary": 2, "japanese": 2, "fantasy": 1}, games={"cozy": 3, "indie": 2},
                     songs={"citypop_jazz": 3, "jpop": 1, "mandopop": 1}, extra={"anime": 10}),
    "demo_tom": dict(anime={"comedy": 1, "scifi": 1}, films={"mind": 3, "drama": 1},
                     books={"nonfiction": 3, "selfhelp": 3}, games={"roguelite": 3, "strategy": 3},
                     songs={"western": 1, "rock": 1, "citypop_jazz": 1}, extra={"games": 10, "books": 10}),
    "demo_ann": dict(anime={"romance": 2, "healing": 1}, films={"romance": 2, "asian": 2, "drama": 1},
                     books={"contemporary": 2, "japanese": 2}, games={"coop": 1, "cozy": 1},
                     songs={"mandopop": 3, "kpop": 1}, extra={"songs": 20}),
    "demo_rex": dict(anime={"action": 3, "sports": 1}, films={"blockbuster": 3, "horror": 1},
                     books={"scifi": 2}, games={"souls": 2, "coop": 3, "competitive": 2},
                     songs={"anisong": 2, "rock": 1}, extra={"games": 10}),
    "demo_hana": dict(anime={"new": 2, "action": 2, "music": 2, "romance": 1}, films={"family": 1, "romance": 1, "asian": 1},
                      books={"japanese": 1, "fantasy": 1}, games={"rhythm": 3},
                      songs={"anisong": 3, "jpop": 3}, extra={"songs": 20, "anime": 10}),
    "demo_owen": dict(anime={"comedy": 1, "fantasy": 1, "new": 1}, films={"family": 2, "blockbuster": 1},
                      books={"fantasy": 2, "scifi": 1}, games={"indie": 3, "horror": 1},
                      songs={"anisong": 1, "jpop": 1, "western": 1}, extra={"games": 10}),
}

MIN_PER_CATEGORY = 30
_TIER_LADDER = ["must_watch", "great", "good", "okay", "bad", "dropped"]
_TAGS = {  # positive tags for liked items, the rest for the ones that disappointed (app.anime per category)
    "anime": (["神作", "值得二刷", "等續集", "好甜", "治癒", "笑死", "胃痛", "中二"], ["崩", "爛尾", "腰斬", "我看了什麼"]),
    "films": (["神作", "後勁很強", "值得二刷", "冷門好片", "淚崩", "笑到肚子痛", "療癒", "熱血", "燒腦", "反轉", "演技炸裂", "配樂神"],
              ["看不懂", "爛尾", "拖戲", "劇情殺"]),
    "books": (["神作", "一口氣讀完", "後勁很強", "值得重讀", "推坑", "淚崩", "療癒", "燒腦", "反轉", "文筆好", "長知識"],
              ["難啃", "翻譯可惜", "爛尾", "太長了"]),
}


def _pick(rng: random.Random, pool: dict[str, list], weights: dict[str, float], n: int, skip: set) -> list[tuple]:
    """n items from the pool, mostly from the styles this person weights highly: (item, style weight)."""
    scored: dict = {}
    for style, items in pool.items():
        w = weights.get(style, 0)
        for item in items:
            score = w + rng.random() * 2.6
            if item not in skip and (item not in scored or scored[item][0] < score):
                scored[item] = (score, w)
    ranked = sorted(scored.items(), key=lambda kv: kv[1][0], reverse=True)
    return [(item, w) for item, (_, w) in ranked[:n]]


def _verdict(rng: random.Random, category: str, w: float) -> tuple[str, str | None]:
    """A tier that follows how much the person likes the style, and a tag that fits the tier (or none)."""
    start = max(0, int(round(2 - w * 0.7 + rng.gauss(0, 0.8))))
    tier = _TIER_LADDER[min(start, len(_TIER_LADDER) - 1)]
    good, bad = _TAGS[category]
    if rng.random() < 0.3:
        return tier, None
    return tier, rng.choice(good if tier in ("must_watch", "great", "good") else bad)


def plan(username: str) -> dict[str, list]:
    """Everything this person's collection holds, favourites first. Same result every time.

    anime: (search text, tier, tag)    films: ("tmdb", id) or ("search", text, kind), tier, tag
    books: (search text, status, tier, tag)    games: ("appid", id) or ("name", text), total hours, hours this month
    songs: (artist, title, plays last month, plays this month)
    """
    p, taste = PROFILES[username], TASTES[username]
    out: dict[str, list] = {}

    def count(category: str) -> int:
        top = max(taste[category].values(), default=0)
        r = random.Random(f"{username}:{category}:n")
        return MIN_PER_CATEGORY + int(round(top * 3)) + r.randint(0, 6) + taste["extra"].get(category, 0)

    rng = random.Random(f"{username}:anime")
    fav = [(ANIME[k], t, g) for k, t, g in p["anime"]]
    have = {q for q, _, _ in fav}
    out["anime"] = fav + [(q, *_verdict(rng, "anime", w)) for q, w in
                          _pick(rng, ANIME_POOL, taste["anime"], max(0, count("anime") - len(fav)), have)]

    rng = random.Random(f"{username}:films")
    fav = [(("tmdb", k), t, g) for k, t, g in p["films"]]
    have_titles = {FILMS[k][1] for k, _, _ in p["films"]} | {FILMS[k][0] for k, _, _ in p["films"]}
    skip = {item for items in FILM_POOL.values() for item in items if item[0] in have_titles}
    out["films"] = fav + [(("search", t, kind), *_verdict(rng, "films", w)) for (t, kind), w in
                          _pick(rng, FILM_POOL, taste["films"], max(0, count("films") - len(fav)), skip)]

    rng = random.Random(f"{username}:books")
    fav = [(BOOKS[k], st, t, g) for k, st, t, g in p["books"]]
    have = {q for q, *_ in fav}
    picked = []
    for q, w in _pick(rng, BOOK_POOL, taste["books"], max(0, count("books") - len(fav)), have):
        roll = rng.random()
        if roll < 0.2:
            picked.append((q, "want", None, None))
        else:
            picked.append((q, "reading" if roll < 0.32 else "read", *_verdict(rng, "books", w)))
    out["books"] = fav + picked

    rng = random.Random(f"{username}:games")
    fav = [(("appid", a), total, this) for a, total, this in p["games"]]
    fav_names = {GAMES[a] for a, _, _ in p["games"]}
    games = []
    for name, w in _pick(rng, GAME_POOL, taste["games"], max(0, count("games") - len(fav)), fav_names):
        total = max(2, int(rng.lognormvariate(2.2 + w * 0.6, 0.8)))
        this = 0 if rng.random() < 0.55 else min(total, rng.randint(1, 8 + int(w * 6)))
        games.append((("name", name), total, this))
    out["games"] = fav + games

    rng = random.Random(f"{username}:songs")
    fav = list(p["songs"])
    have = {(a, t) for a, t, *_ in fav}
    songs = []
    for (artist, title), w in _pick(rng, SONG_POOL, taste["songs"], max(0, count("songs") - len(fav)), have):
        top = 4 + int(w * 6)
        songs.append((artist, title, rng.randint(0, top), rng.randint(1, top)))
    out["songs"] = fav + songs
    return out


def spare(username: str, category: str) -> list[tuple]:
    """More items in the same shape as plan()[category], none already in it, best taste match first —
    used to top a collection up when some lookups find nothing (e.g. films without TMDB_API_KEY)."""
    taste, rng = TASTES[username], random.Random(f"{username}:{category}:spare")
    current = plan(username)[category]
    if category == "anime":
        have = {q for q, *_ in current}
        return [(q, *_verdict(rng, "anime", w)) for q, w in _pick(rng, ANIME_POOL, taste["anime"], 999, have)]
    if category == "films":
        have = {h[1:] for h, *_ in current if h[0] == "search"}
        known = [(("tmdb", k), *_verdict(rng, "films", 1)) for k in FILMS if ("tmdb", k) not in {h for h, *_ in current}]
        return known + [(("search", t, kind), *_verdict(rng, "films", w))
                        for (t, kind), w in _pick(rng, FILM_POOL, taste["films"], 999, have)]
    if category == "books":
        have = {q for q, *_ in current}
        return [(q, "read", *_verdict(rng, "books", w)) for q, w in _pick(rng, BOOK_POOL, taste["books"], 999, have)]
    if category == "games":
        have = {h[1] for h, *_ in current if h[0] == "name"} | {GAMES[h[1]] for h, *_ in current if h[0] == "appid"}
        known = [(("appid", a), rng.randint(3, 60), 0) for a in GAMES if ("appid", a) not in {h for h, *_ in current}]
        return known + [(("name", n), rng.randint(3, 60), 0) for n, w in _pick(rng, GAME_POOL, taste["games"], 999, have)]
    return []
