param(
    [string]$Message = ""
)

$ErrorActionPreference = "Stop"

function Invoke-Git {
    git @args
    if ($LASTEXITCODE -ne 0) {
        throw "git $($args -join ' ') failed with exit code $LASTEXITCODE"
    }
}

$repoRoot = git rev-parse --show-toplevel
if ($LASTEXITCODE -ne 0) {
    throw "This folder is not inside a Git repository."
}
Set-Location $repoRoot

Invoke-Git branch --show-current | Out-Null
$branch = git branch --show-current
if (-not $branch) {
    throw "Cannot sync while Git is in detached HEAD state."
}

$remote = git remote get-url origin 2>$null
if (-not $remote) {
    throw "No Git remote named 'origin' is configured."
}

Invoke-Git add -A -- .

$excluded = git diff --cached --name-only | Where-Object {
    $_ -match '(^|/)__pycache__/' -or
    $_ -match '\.py[cod]$' -or
    $_ -match '^\.pytest_cache/' -or
    $_ -match '^\.mypy_cache/' -or
    $_ -match '^\.ruff_cache/' -or
    $_ -match '^run_stdout\.log$' -or
    $_ -match '^run_stderr\.log$' -or
    $_ -match '\.log$' -or
    $_ -match '^ui_screenshot.*\.png$' -or
    $_ -match '^data/'
}

foreach ($path in $excluded) {
    Invoke-Git restore --staged -- $path
}

$staged = git diff --cached --name-only
if (-not $staged) {
    Write-Host "No uploadable changes found. Skipped commit and push."
    Invoke-Git status --short
    exit 0
}

Write-Host "Staged changes:"
$staged | ForEach-Object { Write-Host "  $_" }

if (-not $Message) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm"
    $Message = "chore: sync local changes $timestamp"
}

Invoke-Git commit -m $Message
Invoke-Git push origin $branch

Write-Host "Synced $branch to $remote"
