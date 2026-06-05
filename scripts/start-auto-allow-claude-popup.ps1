$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$watcher = Join-Path $scriptDir "auto-allow-claude-popup.ps1"
$logDir = Join-Path (Split-Path -Parent $scriptDir) "logs"
$logFile = Join-Path $logDir "auto-allow-claude-popup.log"

if (-not (Test-Path $watcher)) {
  throw "Watcher script not found: $watcher"
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$running = Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe' OR Name = 'pwsh.exe'" |
  Where-Object {
    $_.CommandLine -like "*-File*" -and
    $_.CommandLine -like "*$watcher*" -and
    $_.CommandLine -notlike "*start-auto-allow-claude-popup.ps1*"
  }

if ($running) {
  "[$(Get-Date -Format o)] watcher already running: $($running.ProcessId -join ', ')" | Out-File -Append -Encoding utf8 $logFile
  exit 0
}

"[$(Get-Date -Format o)] starting watcher" | Out-File -Append -Encoding utf8 $logFile

Start-Process -WindowStyle Hidden -FilePath "powershell.exe" -ArgumentList @(
  "-NoProfile",
  "-ExecutionPolicy",
  "Bypass",
  "-File",
  "`"$watcher`"",
  "-PollMs",
  "500"
)
