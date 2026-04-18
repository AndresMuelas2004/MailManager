# dev.ps1 - Start PostgreSQL (if needed), frontend, and backend
#
# Usage:  .\dev.ps1
#   - Checks PostgreSQL and starts it if it's down.
#   - Opens the frontend (npm run dev) in a new terminal window.
#   - Runs the backend (uvicorn) in THIS terminal so you can see every request.
#   - Ctrl+C stops the backend; close the frontend window manually.

$ProjectRoot = $PSScriptRoot
$PgCtl       = "C:\Program Files\PostgreSQL\16\bin\pg_ctl.exe"
$PgData      = "C:\Program Files\PostgreSQL\16\data"
$PgLog       = "C:\Program Files\PostgreSQL\16\data\log\startup.log"

# --- 1. PostgreSQL --------------------------------------------------------
Write-Host "[1/3] Checking PostgreSQL..." -ForegroundColor Cyan
$null = & $PgCtl status -D $PgData 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "      Not running, starting..." -ForegroundColor Yellow
    & $PgCtl start -D $PgData -l $PgLog | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "      ERROR: could not start PostgreSQL." -ForegroundColor Red
        exit 1
    }
    Write-Host "      PostgreSQL started." -ForegroundColor Green
} else {
    Write-Host "      PostgreSQL already running." -ForegroundColor Green
}

# --- 2. Frontend (new window) ---------------------------------------------
Write-Host "[2/3] Starting frontend (new window)..." -ForegroundColor Cyan
$frontendCmd = "cd '$ProjectRoot\frontend'; npm run dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd

# --- 3. Backend (this terminal) -------------------------------------------
Write-Host "[3/3] Starting backend (reload mode)..." -ForegroundColor Cyan
Write-Host "      Ctrl+C to stop." -ForegroundColor DarkGray
Write-Host ""

Push-Location "$ProjectRoot\backend"
try {
    $uvicorn = "$ProjectRoot\.venv\Scripts\uvicorn.exe"
    & $uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
}
finally {
    Pop-Location
}
