# 友多聞 YODO：正式版（app.db）上線給評審、觀眾使用。資料全部保留，不重置。
#   1. 確認 port 8001 沒有伺服器在跑，然後把 app.db 備份成 app.db.bak-日期時間，並切換成 WAL 模式（資料不變）
#   2. 在另一個視窗開 cloudflared 通道（https://….trycloudflare.com → port 8001）
#   3. 在畫面上顯示通道網址的 QR Code（也會開一張大圖，方便把筆電轉給評審掃）
#   4. 在這個視窗用 app.db 啟動伺服器：0.0.0.0:8001，不用 --reload
# port 8000 的 Demo 伺服器完全不受影響（這個腳本不會停掉任何伺服器）。
#
# 用法（在專案資料夾）：powershell -ExecutionPolicy Bypass -File .\start_live.ps1
# 停止：在這個視窗按 Ctrl+C（通道視窗會一起關掉）

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
$Port = 8001
$Python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$Db = Join-Path $PSScriptRoot "app.db"

if (-not (Test-Path $Python)) {
    Write-Host "找不到 .venv\Scripts\python.exe，請先建立虛擬環境並安裝套件（見 README）。" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $Db)) {
    Write-Host "找不到 app.db。" -ForegroundColor Red
    exit 1
}

# 1. back up app.db, only while no server is using it
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    Write-Host "port $Port 已經有伺服器在跑（正式版已經開著？）。請先在那個視窗按 Ctrl+C 停掉，再執行一次。" -ForegroundColor Red
    exit 1
}
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backup = "$Db.bak-$stamp"
# SQLite's own backup: one complete, self-contained file even when app.db is in WAL mode
# (a plain file copy could miss changes still waiting in app.db-wal).
# Then switch app.db to WAL (only once; the data is not changed): readers no longer wait for
# writers, which is what made many people at once hit "database is locked".
& $Python -c @"
import sqlite3, sys
src = sqlite3.connect(sys.argv[1]); dst = sqlite3.connect(sys.argv[2])
src.backup(dst); dst.close()
mode = src.execute('PRAGMA journal_mode').fetchone()[0]
if mode != 'wal':
    mode = src.execute('PRAGMA journal_mode=WAL').fetchone()[0]
print(mode)
src.close()
"@ $Db $backup | Set-Variable journal
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $backup)) {
    Write-Host "備份 app.db 失敗，不啟動。" -ForegroundColor Red
    exit 1
}
Write-Host ("已備份 app.db → {0}（{1:N1} MB）；資料庫模式：{2}" -f (Split-Path $backup -Leaf), ((Get-Item $backup).Length / 1MB), $journal)

# 2. cloudflared quick tunnel in its own window
$cloudflared = $null
foreach ($candidate in @($env:CLOUDFLARED, (Join-Path $env:USERPROFILE "cloudflared\cloudflared.exe"))) {
    if ($candidate -and (Test-Path $candidate)) { $cloudflared = $candidate; break }
}
if (-not $cloudflared) {
    $cmd = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($cmd) { $cloudflared = $cmd.Source }
}

$tunnel = $null
$publicUrl = $null
if ($cloudflared) {
    $log = Join-Path $env:TEMP "yodo-live-cloudflared.log"
    Remove-Item $log -ErrorAction SilentlyContinue
    $tunnel = Start-Process -FilePath $cloudflared -PassThru -WindowStyle Minimized `
        -ArgumentList @("tunnel", "--url", "http://localhost:$Port", "--logfile", "`"$log`"", "--loglevel", "info")
    Write-Host "通道啟動中（另一個視窗，已縮到工作列）..."
    for ($i = 0; $i -lt 60 -and -not $publicUrl; $i++) {
        Start-Sleep -Milliseconds 500
        if (Test-Path $log) {
            $m = Select-String -Path $log -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($m) { $publicUrl = $m.Matches[0].Value }
        }
    }
    if (-not $publicUrl) {
        Write-Host "30 秒內沒拿到通道網址（網路被擋？）。伺服器照常啟動，可以先用下面的區網網址。通道紀錄：$log" -ForegroundColor Yellow
    }
} else {
    Write-Host "找不到 cloudflared，這次只開區網。安裝方法見 README「正式版上線」。" -ForegroundColor Yellow
}

# LAN address, as a fallback for phones on the same Wi-Fi
$lan = @(Get-NetIPConfiguration -ErrorAction SilentlyContinue |
    Where-Object { $_.IPv4DefaultGateway -ne $null -and $_.NetAdapter.Status -eq "Up" } |
    ForEach-Object { $_.IPv4Address.IPAddress } |
    Where-Object { $_ -match '^(192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.)' })
$shareUrl = if ($publicUrl) { $publicUrl } elseif ($lan.Count -gt 0) { "http://$($lan[0]):$Port" } else { $null }

# 3. QR code: in this window, and as a big picture to show the judges
Write-Host ""
Write-Host "================ 友多聞 YODO 正式版 ================" -ForegroundColor Magenta
if ($shareUrl) {
    $png = Join-Path $env:TEMP "yodo-live-qr.png"
    & $Python -c @"
import sys, qrcode
url, png = sys.argv[1], sys.argv[2]
qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=2)
qr.add_data(url)
qr.make(fit=True)
qr.print_ascii(invert=True)
big = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=24, border=4)
big.add_data(url)
big.make(fit=True)
big.make_image(fill_color='black', back_color='white').save(png)
"@ $shareUrl $png
    Write-Host ("掃描上面的 QR Code，或打開：{0}" -f $shareUrl) -ForegroundColor Green
    Start-Process $png  # full-size QR in the photo viewer, to turn the laptop toward the judges
}
if ($publicUrl -and $lan.Count -gt 0) { Write-Host ("同一個 Wi-Fi 也可以用：http://{0}:{1}" -f $lan[0], $Port) }
Write-Host ("筆電本機：http://localhost:{0}" -f $Port)
Write-Host "資料庫：app.db（正式資料，不會重置）。按 Ctrl+C 停止伺服器，通道也會一起關掉。"
Write-Host "====================================================" -ForegroundColor Magenta
Write-Host ""

# 4. the server: always app.db, whatever an earlier start_demo.ps1 run left in the environment
$env:DATABASE_URL = "sqlite:///app.db"
$env:LOCAL_ASSETS_DIR = "demo_assets"
Remove-Item Env:BACKGROUND_JOBS -ErrorAction SilentlyContinue
try {
    & $Python -m uvicorn app.main:app --host 0.0.0.0 --port $Port
} finally {
    if ($tunnel -and -not $tunnel.HasExited) {
        Stop-Process -Id $tunnel.Id -Force -ErrorAction SilentlyContinue
        Write-Host "通道已關閉。"
    }
}
