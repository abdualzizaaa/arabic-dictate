#Requires -Version 5.1
<#
  تثبيت أداة الإملاء العربي على ويندوز (بدون صلاحيات مدير).
  الاستخدام:
    .\install.ps1 [ -WithMeeting ] [ -AddToPath ] [ -AutoStart ]
#>
param(
    [switch]$WithMeeting,
    [switch]$AddToPath,
    [switch]$AutoStart
)

$ErrorActionPreference = "Stop"
$Project = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Project

Write-Host "1/6 - Checking Python"
$pyCmd = $null
$pyArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue) { $pyCmd = "py"; $pyArgs = @("-3") }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $pyCmd = "python" }
else { throw "Python is not installed. Get it from https://www.python.org/downloads/ or run: winget install Python.Python.3.12" }
$version = & $pyCmd @pyArgs --version
Write-Host "   OK  $version"

Write-Host "2/6 - Creating the Python environment"
if (-not (Test-Path ".venv")) {
    & $pyCmd @pyArgs -m venv .venv
}
$venvPython = Join-Path $Project ".venv\Scripts\python.exe"
& $venvPython -m pip install --upgrade pip --quiet
Write-Host "   OK  .venv"

Write-Host "3/6 - Installing packages"
$extras = "whisper,windows"
if ($WithMeeting) { $extras = "$extras,meeting" }
& $venvPython -m pip install -e ".[$extras]"
Write-Host "   OK  installed with: $extras"

Write-Host "4/6 - The global command"
$scriptsDir = Join-Path $Project ".venv\Scripts"
if ($AddToPath) {
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($userPath -notlike "*$scriptsDir*") {
        [Environment]::SetEnvironmentVariable("Path", "$userPath;$scriptsDir", "User")
        Write-Host "   OK  Added to PATH (reopen your terminal to use it anywhere)"
    } else {
        Write-Host "   OK  Already in PATH"
    }
} else {
    Write-Host "   Note: rerun with -AddToPath for a global command, or use:"
    Write-Host "         $scriptsDir\arabic-dictate.exe"
}

Write-Host "5/6 - Auto start with Windows"
if ($AutoStart) {
    $startup = [Environment]::GetFolderPath("Startup")
    $shortcutPath = Join-Path $startup "arabic-dictate.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = Join-Path $scriptsDir "arabic-dictate.exe"
    $shortcut.Arguments = "ensure"
    $shortcut.WindowStyle = 7
    $shortcut.Save()
    Write-Host "   OK  The daemon will start automatically with Windows"
} else {
    Write-Host "   Note: enable with -AutoStart if you want it"
}

Write-Host "6/6 - Doctor"
& $venvPython -m arabic_dictate doctor

Write-Host ""
Write-Host "Done. Next steps:"
Write-Host "  $scriptsDir\arabic-dictate.exe ensure    # start the daemon"
Write-Host "  $scriptsDir\arabic-dictate.exe pull      # optional: best Arabic model (~3GB)"
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "  winget install ffmpeg                    # needed for meeting audio conversion"
}
