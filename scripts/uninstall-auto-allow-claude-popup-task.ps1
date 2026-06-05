param(
  [string]$TaskName = "AdSurf Auto Allow Claude Popup"
)

$ErrorActionPreference = "Stop"

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($task) {
  Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
  Write-Host "Uninstalled scheduled task: $TaskName"
} else {
  Write-Host "Scheduled task not found: $TaskName"
}

$startup = [Environment]::GetFolderPath("Startup")
$cmdPath = Join-Path $startup "AdSurf Auto Allow Claude Popup.cmd"
if (Test-Path $cmdPath) {
  Remove-Item -Path $cmdPath -Force
  Write-Host "Removed Startup launcher: $cmdPath"
}
