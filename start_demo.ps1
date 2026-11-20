# 友多聞 YODO：一鍵啟動 Demo
#   1. 停掉正在跑的 Demo 伺服器（佔用 port 8000 的 Python）
#   2. 把 demo.db 重置成初始狀態（scripts.reset_demo）
#   3. 用 demo.db + 本機封面（demo_assets）在 0.0.0.0:8000 啟動，讓同一個 Wi-Fi 的手機連進來
#   4. 印出筆電的區網 IP 和手機要開的網址
#
# 用法（在專案資料夾）：powershell -ExecutionPolicy Bypass -File .\start_demo.ps1
# 停止：按 Ctrl+C

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
$Port = 8000
$Python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Host "找不到 .venv\Scripts\python.exe，請先建立虛擬環境並安裝套件（見 README）。" -ForegroundColor Red
    exit 1
}

# 1. stop whatever Python is serving port 8000 (an earlier demo run)
$listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique)
foreach ($procId in $listeners) {
    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($null -eq $proc) { continue }
    if ($proc.ProcessName -match '^(python|pythonw|uvicorn)$') {
        Write-Host "停止舊的 Demo 伺服器（PID $procId）..."
        Stop-Process -Id $procId -Force
    } else {
        Write-Host "port $Port 被 $($proc.ProcessName)（PID $procId）佔用，不是 Demo 伺服器，請先關掉它再執行。" -ForegroundColor Red
        exit 1
    }
}
# give Windows a moment to release demo.db
for ($i = 0; $i -lt 20; $i++) {
    if (-not (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)) { break }
    Start-Sleep -Milliseconds 250
}

# 2. reset demo.db
& $Python -m scripts.reset_demo
if ($LASTEXITCODE -ne 0) {
    Write-Host "重置失敗，沒有啟動伺服器。" -ForegroundColor Red
    exit 1
}

# 3. the laptop's LAN address: private IPv4 addresses (192.168.x, 10.x, 172.16-31.x) on adapters
#    that are up and have a default gateway; VPN adapters such as Hamachi (25.x) are left out
$lan = @(Get-NetIPConfiguration -ErrorAction SilentlyContinue |
    Where-Object { $_.IPv4DefaultGateway -ne $null -and $_.NetAdapter.Status -eq "Up" } |
    ForEach-Object { $_.IPv4Address.IPAddress } |
    Where-Object { $_ -match '^(192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.)' })

Write-Host ""
Write-Host "================ 友多聞 YODO Demo ================" -ForegroundColor Magenta
if ($lan.Count -gt 0) {
    foreach ($ip in $lan) {
        Write-Host ("筆電區網 IP：{0}" -f $ip)
        Write-Host ("手機打開：  http://{0}:{1}/login" -f $ip, $Port) -ForegroundColor Green
    }
} else {
    Write-Host "找不到區網 IP（筆電沒有連上 Wi-Fi？）。筆電本機仍可開 http://localhost:$Port/login" -ForegroundColor Yellow
}
Write-Host ("筆電本機：  http://localhost:{0}/login" -f $Port)
Write-Host "帳號：demo（主手機）、demo_rain 小雨、demo_zhe 阿哲；密碼見 scripts/seed_demo.py"
Write-Host "手機連不上？見 README「Demo 環境」的防火牆說明。按 Ctrl+C 停止。"
Write-Host "==================================================" -ForegroundColor Magenta
Write-Host ""

# 4. start (foreground; Ctrl+C stops it)
$env:DATABASE_URL = "sqlite:///demo.db"
$env:LOCAL_ASSETS_DIR = "demo_assets"
& $Python -m uvicorn app.main:app --host 0.0.0.0 --port $Port
