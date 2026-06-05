param(
  [int]$PollMs = 500,
  [switch]$Once,
  [switch]$DryRun,
  [string]$LogPath
)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms

if (-not $LogPath) {
  $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
  $LogPath = Join-Path (Split-Path -Parent $scriptDir) "logs\auto-allow-claude-popup.log"
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $LogPath) | Out-Null

function Write-Log {
  param([string]$Message)
  "[$(Get-Date -Format o)] $Message" | Out-File -Append -Encoding utf8 $LogPath
}

$buttonNamePattern = "^(OK|Ok|Allow|Yes|Continue|Approve)$"
$contextPattern = "(Claude|Claude Code|permission|allow|extension)"
$hostTitlePattern = "(Visual Studio Code|VS Code|Cursor|Windsurf)"

function Get-ElementText {
  param($Element)

  $names = New-Object System.Collections.Generic.List[string]
  if ($Element.Current.Name) {
    $names.Add($Element.Current.Name)
  }

  $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
  $child = $walker.GetFirstChild($Element)
  while ($null -ne $child) {
    if ($child.Current.Name) {
      $names.Add($child.Current.Name)
    }
    $child = $walker.GetNextSibling($child)
  }

  return ($names -join " ")
}

function Invoke-MatchingButton {
  $root = [System.Windows.Automation.AutomationElement]::RootElement
  $windowCondition = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Window
  )
  $buttonCondition = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Button
  )

  $windows = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $windowCondition)
  foreach ($window in $windows) {
    $title = $window.Current.Name
    if ($title -notmatch $hostTitlePattern -and $title -notmatch $contextPattern) {
      continue
    }

    $windowText = Get-ElementText $window
    if ($windowText -notmatch $contextPattern) {
      continue
    }

    $buttons = $window.FindAll([System.Windows.Automation.TreeScope]::Descendants, $buttonCondition)
    foreach ($button in $buttons) {
      $name = $button.Current.Name
      if ($name -notmatch $buttonNamePattern) {
        continue
      }

      if ($DryRun) {
        Write-Log "would press '$name' in '$title'"
        Write-Host "Would press '$name' in '$title'"
        return $true
      }

      $pattern = $button.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
      $pattern.Invoke()
      Write-Log "pressed '$name' in '$title'"
      Write-Host "Pressed '$name' in '$title'"
      return $true
    }
  }

  return $false
}

Write-Log "watcher started"
Write-Host "Watching for Claude Code allow/OK popups. Press Ctrl+C to stop."

do {
  try {
    $pressed = Invoke-MatchingButton
    if ($Once -and $pressed) {
      break
    }
  } catch {
    Write-Log "warning: $($_.Exception.Message)"
    Write-Warning $_.Exception.Message
  }

  if (-not $Once) {
    Start-Sleep -Milliseconds $PollMs
  }
} while (-not $Once)
