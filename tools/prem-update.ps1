<#
Brings Prem Lab up to date the way "git pull" would; tools\prem-lab.bat runs it before it starts the app. It only updates when that is safe, and never
stands in the way of starting: no Git (a downloaded ZIP), not on a branch that follows one on GitHub, files changed here, offline, or a history
that has gone its own way all mean "start the version you have".

Exit code 10 means it updated (the launcher then starts afresh, as the update may have replaced it); anything else means nothing changed.
#>
$ErrorActionPreference = "Continue"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path ".git") -or -not (Get-Command git -ErrorAction SilentlyContinue)) { exit 0 }
git symbolic-ref -q HEAD *> $null
if ($LASTEXITCODE -ne 0) { exit 0 }
git rev-parse -q --verify '@{upstream}' *> $null
if ($LASTEXITCODE -ne 0) { exit 0 }
if (git status --porcelain --untracked-files=no 2> $null) {
    Write-Host "Not looking for updates: files in $(Get-Location) have been changed here."
    Write-Host ""
    exit 0
}

Write-Host "Looking for updates ..."
# fetching is the only step that uses the network, so it gets a time limit (stopping a fetch is harmless); the merge after it is local
$env:GIT_TERMINAL_PROMPT = "0"
$quiet = Join-Path ([IO.Path]::GetTempPath()) "prem-update-fetch.txt"
$fetch = Start-Process git -ArgumentList "-c", "http.lowSpeedLimit=1000", "-c", "http.lowSpeedTime=10", "fetch", "--quiet" `
    -NoNewWindow -PassThru -RedirectStandardError $quiet
$null = $fetch.Handle   # without this, Windows PowerShell forgets the exit code
if (-not $fetch.WaitForExit(10000)) {
    $fetch.Kill()
    Write-Host "No answer from GitHub, so starting the version you have."
    Write-Host ""
    exit 0
}
if ($fetch.ExitCode -ne 0) {
    Write-Host "Could not reach GitHub (offline?), so starting the version you have."
    Write-Host ""
    exit 0
}

$before = git rev-parse HEAD
git merge-base --is-ancestor '@{upstream}' HEAD
if ($LASTEXITCODE -eq 0) {
    Write-Host "Up to date."
    Write-Host ""
    exit 0
}
git merge --ff-only --quiet '@{upstream}' *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "There is an update, but this copy has changes of its own, so it was not applied. Run git pull in $(Get-Location) to sort it out."
    Write-Host ""
    exit 0
}
Write-Host "Updated. What is new:"
git log --no-merges --format='  - %s' "$before..HEAD" | Select-Object -First 15 | ForEach-Object { Write-Host $_ }
Write-Host ""

# new or changed packages. The launcher runs the project's .venv: uv keeps it in step (with the event data packages if they are installed,
# which a plain "uv sync" would remove); an environment made with pip is installed again, which also turns an old "pip install ." into "-e ."
git diff --quiet $before HEAD -- pyproject.toml uv.lock
$packagesChanged = $LASTEXITCODE -ne 0
if ((Get-Command uv -ErrorAction SilentlyContinue) -and -not (Test-Path ".venv\Scripts\pip.exe")) {
    if ($packagesChanged) {
        $extra = @()
        if (Test-Path ".venv\Lib\site-packages\soccerdata") { $extra = @("--extra", "events") }
        Write-Host "Updating the packages ..."
        uv sync --inexact --quiet @extra
        if ($LASTEXITCODE -ne 0) { Write-Host "Updating the packages failed: run uv sync in this folder." }
    }
}
elseif (Test-Path ".venv\Scripts\pip.exe") {
    Write-Host "Updating the packages ..."
    .venv\Scripts\pip.exe install --quiet -e .
    if ($LASTEXITCODE -ne 0) { Write-Host "Updating the packages failed: run .venv\Scripts\pip install -e . in this folder." }
}
exit 10
