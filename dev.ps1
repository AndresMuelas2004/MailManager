# dev.ps1 - Start PostgreSQL, frontend, and backend without ever blocking.
#
# Usage:  .\dev.ps1   (or `run` from the user profile)
# Invoke with '&', not dot-source ('. .\dev.ps1') -- the script uses 'exit 0'.
#
#   - PostgreSQL: started only if port 5432 is not reachable.
#   - Frontend (npm run dev): launched fire-and-forget in a NEW PowerShell
#     window only if port 5173 is free. The launcher does NOT wait for it.
#   - Backend (uvicorn --reload): runs in THIS terminal so logs are visible.
#     If port 8000 is already in use, the script prints the holding PID and
#     exits cleanly without touching uvicorn.
#   - A background job opens the browser at the frontend URL once BOTH ports
#     (5173 and 8000) are reachable.
#   - Ctrl+C stops the backend; close the frontend window manually.

$ProjectRoot  = $PSScriptRoot
$PgCtl        = 'C:\Program Files\PostgreSQL\16\bin\pg_ctl.exe'
$PgData       = 'C:\Program Files\PostgreSQL\16\data'
$PgLog        = 'C:\Program Files\PostgreSQL\16\data\log\startup.log'
$PgPort       = 5432
$FrontendPort = 5173
$BackendPort  = 8000
$FrontendUrl  = "http://localhost:$FrontendPort"

function Test-PortListening {
    param([int]$Port)
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $iar    = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
        $ok     = $iar.AsyncWaitHandle.WaitOne(500, $false)
        $reachable = $false
        if ($ok) {
            try { $client.EndConnect($iar); $reachable = $true } catch { $reachable = $false }
        }
        $client.Close()
        return $reachable
    } catch { return $false }
}

function Wait-ForPort {
    param([int]$Port, [int]$TimeoutSec = 30)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-PortListening -Port $Port) { return $true }
        Start-Sleep -Milliseconds 400
    }
    return $false
}

# --- 1. PostgreSQL --------------------------------------------------------
Write-Host "[1/3] Checking PostgreSQL on port $PgPort..." -ForegroundColor Cyan
if (Test-PortListening -Port $PgPort) {
    Write-Host '      PostgreSQL already running.' -ForegroundColor Green
} else {
    Write-Host '      Not running, starting...' -ForegroundColor Yellow
    $logDir = Split-Path -Parent $PgLog
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
    Start-Process -FilePath $PgCtl `
                  -ArgumentList @('start', '-D', $PgData, '-l', $PgLog, '-W') `
                  -WindowStyle Hidden | Out-Null
    if (-not (Wait-ForPort -Port $PgPort -TimeoutSec 30)) {
        Write-Host "      ERROR: PostgreSQL did not become reachable on port $PgPort." -ForegroundColor Red
        Write-Host "      Check log: $PgLog" -ForegroundColor Red
        exit 1
    }
    Write-Host '      PostgreSQL started.' -ForegroundColor Green
}

# --- 2. Frontend (new window, fire-and-forget) ----------------------------
Write-Host "[2/3] Starting frontend on port $FrontendPort..." -ForegroundColor Cyan
if (Test-PortListening -Port $FrontendPort) {
    Write-Host "      Port $FrontendPort already in use, skip." -ForegroundColor Green
} else {
    $frontendCmd = "Set-Location '$ProjectRoot\frontend'; npm run dev"
    Start-Process powershell -ArgumentList '-NoExit', '-Command', $frontendCmd | Out-Null
    Write-Host '      Launched in new window.' -ForegroundColor Green
}

# --- 3. Browser auto-open (fires once BOTH frontend and backend respond) --
$browserJob = Start-Job -ScriptBlock {
    param($Url, $FrontPort, $BackPort)
    function Test-Port {
        param([int]$Port)
        try {
            $c   = New-Object System.Net.Sockets.TcpClient
            $iar = $c.BeginConnect('127.0.0.1', $Port, $null, $null)
            $ok  = $iar.AsyncWaitHandle.WaitOne(300, $false)
            $reachable = $false
            if ($ok) { try { $c.EndConnect($iar); $reachable = $true } catch {} }
            $c.Close()
            return $reachable
        } catch { return $false }
    }
    $deadline = (Get-Date).AddSeconds(120)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        if ((Test-Port -Port $FrontPort) -and (Test-Port -Port $BackPort)) {
            $ready = $true
            break
        }
        Start-Sleep -Milliseconds 500
    }
    if ($ready) {
        # Vite may listen() before serving index.html; give it a beat.
        Start-Sleep -Seconds 1
        Start-Process $Url
    }
} -ArgumentList $FrontendUrl, $FrontendPort, $BackendPort

# --- 4. Backend (this terminal) -------------------------------------------
Write-Host "[3/3] Starting backend on port $BackendPort (reload mode)..." -ForegroundColor Cyan
if (Test-PortListening -Port $BackendPort) {
    Write-Host "      Port $BackendPort already in use - skipping uvicorn launch." -ForegroundColor Yellow
    try {
        $conn = Get-NetTCPConnection -LocalPort $BackendPort -State Listen -ErrorAction Stop |
                Select-Object -First 1
        if ($conn) {
            $proc = Get-Process -Id $conn.OwningProcess -ErrorAction Stop
            Write-Host "      Held by PID $($proc.Id) ($($proc.ProcessName))." -ForegroundColor DarkGray
            Write-Host "      Stop-Process -Id $($proc.Id) -Force  # if it's a stale uvicorn" -ForegroundColor DarkGray
        }
    } catch {}
    Write-Host "      Browser will still auto-open once both ports are reachable." -ForegroundColor DarkGray
    try {
        Wait-Job -Job $browserJob -Timeout 130 | Out-Null
    } finally {
        Stop-Job  -Job $browserJob -ErrorAction SilentlyContinue | Out-Null
        Remove-Job -Job $browserJob -Force -ErrorAction SilentlyContinue | Out-Null
    }
    exit 0
}

Write-Host "      App will open at $FrontendUrl once both ports are reachable." -ForegroundColor DarkGray
Write-Host '      Ctrl+C to stop.' -ForegroundColor DarkGray
Write-Host ''

Push-Location "$ProjectRoot\backend"
try {
    $uvicorn = "$ProjectRoot\.venv\Scripts\uvicorn.exe"
    & $uvicorn api.app:app --host 0.0.0.0 --port $BackendPort --reload
}
finally {
    Pop-Location
    if ($browserJob) {
        Stop-Job  -Job $browserJob -ErrorAction SilentlyContinue | Out-Null
        Remove-Job -Job $browserJob -Force -ErrorAction SilentlyContinue | Out-Null
    }
}
