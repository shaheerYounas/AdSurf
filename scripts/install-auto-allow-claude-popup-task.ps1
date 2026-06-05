param(
  [string]$TaskName = "AdSurf Auto Allow Claude Popup"
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$launcher = Join-Path $scriptDir "start-auto-allow-claude-popup.ps1"

if (-not (Test-Path $launcher)) {
  throw "Launcher script not found: $launcher"
}

$action = New-ScheduledTaskAction `
  -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$launcher`""

$trigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal `
  -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
  -LogonType Interactive `
  -RunLevel Limited

$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -MultipleInstances IgnoreNew `
  -RestartCount 3 `
  -RestartInterval (New-TimeSpan -Minutes 1)

try {
  Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Force | Out-Null

  Start-ScheduledTask -TaskName $TaskName

  Write-Host "Installed and started scheduled task: $TaskName"
  Write-Host "Launcher: $launcher"
} catch {
  $startup = [Environment]::GetFolderPath("Startup")
  $cmdPath = Join-Path $startup "AdSurf Auto Allow Claude Popup.cmd"
  $cmd = @(
    "@echo off",
    "start """" /min powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""$launcher"""
  ) -join [Environment]::NewLine

  Set-Content -Path $cmdPath -Value $cmd -Encoding ascii
  Start-Process -WindowStyle Hidden -FilePath "powershell.exe" -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    "`"$launcher`""
  )

  Write-Host "Scheduled task failed, installed Startup fallback instead."
  Write-Host "Startup launcher: $cmdPath"
  Write-Host "Reason: $($_.Exception.Message)"
}
