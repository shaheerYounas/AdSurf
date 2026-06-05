param(
  [switch]$Click,
  [int]$TimeoutSeconds = 30
)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

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

function Find-ClaudePermissionButton {
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
      if ($name -match $buttonNamePattern) {
        return [pscustomobject]@{
          WindowTitle = $title
          WindowText = $windowText
          ButtonName = $name
          Button = $button
        }
      }
    }
  }

  return $null
}

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
do {
  $match = Find-ClaudePermissionButton
  if ($match) {
    Write-Host "FOUND real matching popup:"
    Write-Host "Window: $($match.WindowTitle)"
    Write-Host "Button: $($match.ButtonName)"

    if ($Click) {
      $pattern = $match.Button.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
      $pattern.Invoke()
      Write-Host "Clicked: $($match.ButtonName)"
    }

    exit 0
  }

  Start-Sleep -Milliseconds 500
} while ((Get-Date) -lt $deadline)

Write-Host "No real Claude permission popup detected within $TimeoutSeconds seconds."
exit 2
