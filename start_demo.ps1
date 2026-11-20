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

# 1. stop every Python server on port 8000 (an earlier demo run, or a dev server on 127.0.0.1:8000,
#    which would otherwise answer http://localhost:8000 instead of the demo). uvicorn --reload and
#    multiprocessing workers keep listening after their parent exits, so children are stopped too.
function Get-PortServers {
    $owners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)
    if ($owners.Count -eq 0) { return @() }
    return @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $p = $_
        @($owners | Where-Object { $p.ProcessId -eq $_ -or $p.ParentProcessId -eq $_ -or $p.CommandLine -match "parent_pid=$_\b" }).Count -gt 0
    })
}

for ($round = 0; $round -lt 3; $round++) {
    $servers = Get-PortServers
    if ($servers.Count -eq 0 -and -not (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)) { break }
    foreach ($p in $servers) {
        if ($p.Name -notmatch '^(python|pythonw|uvicorn)(\.exe)?$') {
            Write-Host "port $Port 被 $($p.Name)（PID $($p.ProcessId)）佔用，不是 Python 伺服器，請先關掉它再執行。" -ForegroundColor Red
            exit 1
        }
    }
    foreach ($p in $servers) {
        Write-Host "停止 port $Port 上的伺服器（PID $($p.ProcessId)）..."
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
    # give Windows a moment to release the port and demo.db
    for ($i = 0; $i -lt 20; $i++) {
        if (-not (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 250
    }
}
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    Write-Host "port $Port 還是被佔用，沒有啟動。請關掉其他開在 port $Port 的伺服器（或重開機）後再執行。" -ForegroundColor Red
    exit 1
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
