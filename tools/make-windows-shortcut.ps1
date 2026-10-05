<#
Puts a "Prem Lab" shortcut, with the Prem Lab icon, on your Desktop. Double-click it to start the app.

  powershell -ExecutionPolicy Bypass -File tools\make-windows-shortcut.ps1
  powershell -ExecutionPolicy Bypass -File tools\make-windows-shortcut.ps1 -Folder "$env:APPDATA\Microsoft\Windows\Start Menu\Programs"

A .bat file cannot carry an icon of its own, but a shortcut can: the icon lives in the shortcut, which points at tools\icon\prem-lab.ico. If you move the
Prem Lab folder, run this again.
#>
param([string]$Folder = [Environment]::GetFolderPath("Desktop"))

$ErrorActionPreference = "Stop"
$launcher = Join-Path $PSScriptRoot "prem-lab.bat"
$icon = Join-Path $PSScriptRoot "icon\prem-lab.ico"
foreach ($needed in @($launcher, $icon)) {
    if (-not (Test-Path $needed)) { throw "Cannot find $needed" }
}
if (-not (Test-Path $Folder)) { throw "Cannot find the folder $Folder" }

$path = Join-Path $Folder "Prem Lab.lnk"
$link = (New-Object -ComObject WScript.Shell).CreateShortcut($path)
$link.TargetPath = $launcher
$link.WorkingDirectory = Split-Path -Parent $PSScriptRoot
$link.IconLocation = "$icon,0"
$link.Description = "Prem Lab: football analytics that runs on your own computer"
$link.Save()
Write-Host "Shortcut made: $path"
