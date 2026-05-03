# unlock-worktree.ps1
#
# Detects and force-kills processes that hold a lock on a worktree directory.
# Invoked by the /ship skill (Phase 0.5) before any irreversible operation.
#
# Detection passes (in order):
#   1. CIM enumeration of all Win32_Process: a process is flagged if its
#      ExecutablePath lives inside the worktree, or its CommandLine references
#      the worktree as a path token (strict-prefix match — no "C:\foo" matching
#      "C:\foobar").
#   2. handle.exe (Sysinternals) — if available on PATH or bundled at
#      ../bin/handle.exe — catches processes that hold a handle without their
#      executable or command line revealing the path (file watchers, shells
#      with cwd in the worktree, antivirus mid-scan, etc.).
#
# Safety filters:
#   - Excludes the script's own PID and parent PID (the PowerShell that
#     launched it — typically the same shell running /ship).
#   - Excludes a hardcoded list of system / shell / IDE processes so we never
#     kill the user's editor, terminal, or Claude itself, even if they show up
#     in the second pass.
#
# Exit codes:
#   0 — no blocking processes, or all blockers killed cleanly.
#   1 — some blockers detected but could not be killed (caller should warn
#       and continue; final cleanup may still succeed via --force / rm -rf).
#   2 — the worktree path passed in does not exist on disk (caller stops).

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$WorktreePath
)

$ErrorActionPreference = 'Stop'
$OutputEncoding = [System.Text.Encoding]::UTF8

try {
    $WorktreeFull = (Resolve-Path -LiteralPath $WorktreePath -ErrorAction Stop).Path
} catch {
    Write-Output "ERROR: Path '$WorktreePath' does not exist."
    exit 2
}

# Normalise both slash variants so we can match Windows-style and POSIX-style
# paths uniformly (Git Bash / WSL produce forward slashes in cmdlines).
$worktreeBack = ($WorktreeFull -replace '/', '\').TrimEnd('\')
$worktreeFwd  = $worktreeBack -replace '\\', '/'

function Test-IsInsideWorktree {
    param(
        [string]$Path,
        [string]$WorktreeBack,
        [string]$WorktreeFwd
    )
    if ([string]::IsNullOrEmpty($Path)) { return $false }
    $n = $Path.TrimEnd('\', '/')
    if ($n -ieq $WorktreeBack -or $n -ieq $WorktreeFwd) { return $true }
    return $n.StartsWith($WorktreeBack + '\', [System.StringComparison]::OrdinalIgnoreCase) `
        -or $n.StartsWith($WorktreeBack + '/', [System.StringComparison]::OrdinalIgnoreCase) `
        -or $n.StartsWith($WorktreeFwd + '\', [System.StringComparison]::OrdinalIgnoreCase) `
        -or $n.StartsWith($WorktreeFwd + '/', [System.StringComparison]::OrdinalIgnoreCase)
}

$selfPid = $PID
$parentInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $selfPid" -ErrorAction SilentlyContinue
$parentPid = if ($parentInfo) { [int]$parentInfo.ParentProcessId } else { 0 }

# Never-kill list: system processes, shells, terminals, Claude itself, common IDEs.
# Anything not on this list (node, python, uvicorn, vite, pytest, mcp servers, etc.)
# is fair game when it is inside the worktree.
$neverKillNames = @(
    'System', 'Idle',
    'svchost.exe', 'csrss.exe', 'wininit.exe', 'winlogon.exe',
    'lsass.exe', 'services.exe', 'smss.exe', 'fontdrvhost.exe',
    'dwm.exe', 'ctfmon.exe', 'sihost.exe', 'taskhostw.exe', 'RuntimeBroker.exe',
    'explorer.exe', 'WindowsTerminal.exe', 'OpenConsole.exe', 'conhost.exe',
    'powershell.exe', 'powershell_ise.exe', 'pwsh.exe',
    'cmd.exe', 'bash.exe', 'sh.exe',
    'Code.exe', 'Code - Insiders.exe', 'Cursor.exe', 'devenv.exe',
    'sublime_text.exe', 'idea64.exe', 'pycharm64.exe', 'webstorm64.exe', 'rider64.exe',
    'claude.exe', 'Claude.exe'
)

$allProcesses = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue
if (-not $allProcesses) {
    Write-Output "WARNING: could not enumerate processes (CIM unavailable)."
    exit 0
}

$candidates = New-Object System.Collections.Generic.List[object]
$seenPids = New-Object System.Collections.Generic.HashSet[int]

$wbEsc = [Regex]::Escape($worktreeBack)
$wfEsc = [Regex]::Escape($worktreeFwd)
# Match the worktree path followed by a path separator, quote, whitespace,
# or end-of-string — never a continuation character that would mean a
# different directory (rules out "C:\worktree" matching "C:\worktreeold").
$cmdLinePattern = "(?:$wbEsc|$wfEsc)(\\|/|""|'|\s|$)"

foreach ($proc in $allProcesses) {
    $pId = [int]$proc.ProcessId
    if ($pId -eq $selfPid -or $pId -eq $parentPid) { continue }
    if ($neverKillNames -contains $proc.Name) { continue }

    $matchedBy = New-Object System.Collections.Generic.List[string]
    if (Test-IsInsideWorktree -Path $proc.ExecutablePath -WorktreeBack $worktreeBack -WorktreeFwd $worktreeFwd) {
        $matchedBy.Add('ExecutablePath') | Out-Null
    }
    if (-not [string]::IsNullOrEmpty($proc.CommandLine) -and $proc.CommandLine -match $cmdLinePattern) {
        $matchedBy.Add('CommandLine') | Out-Null
    }

    if ($matchedBy.Count -gt 0 -and $seenPids.Add($pId)) {
        $candidates.Add([PSCustomObject]@{
            Pid        = $pId
            Name       = $proc.Name
            ExePath    = $proc.ExecutablePath
            MatchedBy  = ($matchedBy -join ',')
        })
    }
}

# --- Optional second pass: handle.exe (Sysinternals) ---
$handleExe = $null
$cmd = Get-Command -Name 'handle.exe' -ErrorAction SilentlyContinue
if ($cmd) { $handleExe = $cmd.Source }
if (-not $handleExe) {
    $bundled = Join-Path $PSScriptRoot '..\bin\handle.exe'
    if (Test-Path -LiteralPath $bundled) { $handleExe = (Resolve-Path -LiteralPath $bundled).Path }
}

if ($handleExe) {
    Write-Output "Using handle.exe at: $handleExe"
    try {
        $handleOutput = & $handleExe -nobanner -accepteula $worktreeBack 2>&1
        foreach ($line in $handleOutput) {
            $text = "$line"
            # handle.exe lines look like:  "node.exe   pid: 12345  type: File  ..."
            if ($text -match '^(?<name>\S+)\s+pid:\s*(?<pid>\d+)') {
                $hPid = [int]$matches['pid']
                if ($hPid -eq $selfPid -or $hPid -eq $parentPid) { continue }
                if ($seenPids.Contains($hPid)) { continue }
                $hProc = Get-CimInstance Win32_Process -Filter "ProcessId = $hPid" -ErrorAction SilentlyContinue
                if (-not $hProc) { continue }
                if ($neverKillNames -contains $hProc.Name) { continue }
                $seenPids.Add($hPid) | Out-Null
                $candidates.Add([PSCustomObject]@{
                    Pid       = $hPid
                    Name      = $hProc.Name
                    ExePath   = $hProc.ExecutablePath
                    MatchedBy = 'handle.exe'
                })
            }
        }
    } catch {
        Write-Output "WARNING: handle.exe failed: $($_.Exception.Message)"
    }
}

if ($candidates.Count -eq 0) {
    Write-Output "OK: no processes locking '$worktreeBack'."
    exit 0
}

Write-Output "Found $($candidates.Count) process(es) inside '$worktreeBack':"
foreach ($c in $candidates) {
    Write-Output ("  PID {0,-7} {1,-28} [{2}]  {3}" -f $c.Pid, $c.Name, $c.MatchedBy, $c.ExePath)
}

Write-Output ""
Write-Output "Killing processes..."

$killed = 0
$failed = 0
foreach ($c in $candidates) {
    try {
        Stop-Process -Id $c.Pid -Force -ErrorAction Stop
        $killed++
        Write-Output ("  KILLED  PID {0,-7} {1}" -f $c.Pid, $c.Name)
    } catch {
        $failed++
        $msg = $_.Exception.Message
        Write-Output ("  FAILED  PID {0,-7} {1} -- {2}" -f $c.Pid, $c.Name, $msg)
    }
}

# Brief wait so the OS releases handles before deletion attempts later.
Start-Sleep -Milliseconds 500

Write-Output ""
Write-Output "SUMMARY: killed=$killed failed=$failed total=$($candidates.Count)"

if ($failed -gt 0) { exit 1 }
exit 0
