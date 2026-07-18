param(
    [Parameter(Mandatory = $true)]
    [string]$RepositoryUrl
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git is not installed or is not available in PATH."
}

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

if (-not (Test-Path ".git")) {
    git init -b main
}

git add .
$changes = git status --porcelain
if ($changes) {
    git commit -m "Initial release: DriveFort AI V3"
} else {
    Write-Host "No uncommitted changes found."
}

$existingOrigin = git remote get-url origin 2>$null
if ($LASTEXITCODE -eq 0) {
    git remote set-url origin $RepositoryUrl
} else {
    git remote add origin $RepositoryUrl
}

git push -u origin main
