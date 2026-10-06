param(
  [Parameter(Mandatory=$true)]
  [string]$Token
)

$ErrorActionPreference = 'Stop'
$RepoUrl = 'https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment'
$RunnerDir = 'C:\JNS\actions-runner'

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
  [Security.Principal.WindowsBuiltInRole]::Administrator)) {
  throw 'Run PowerShell as Administrator.'
}

New-Item -ItemType Directory -Force -Path $RunnerDir | Out-Null
Set-Location $RunnerDir

if (-not (Test-Path '.\config.cmd')) {
  $release = Invoke-RestMethod 'https://api.github.com/repos/actions/runner/releases/latest'
  $asset = $release.assets | Where-Object { $_.name -match '^actions-runner-win-x64-.*\.zip$' } | Select-Object -First 1
  if (-not $asset) { throw 'Could not find current Windows x64 Actions runner package.' }
  $zip = Join-Path $env:TEMP $asset.name
  Write-Host "Downloading $($asset.name)..."
  Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zip
  Expand-Archive -Path $zip -DestinationPath $RunnerDir -Force
}

Write-Host 'Registering SAGE runner...'
& .\config.cmd --unattended --url $RepoUrl --token $Token --name SAGE --labels sage --work '_work' --runasservice
if ($LASTEXITCODE -ne 0) { throw "Runner configuration failed with exit code $LASTEXITCODE" }

Get-Service 'actions.runner.*' | Start-Service
Write-Host ''
Write-Host 'Runner service status:'
Get-Service 'actions.runner.*' | Format-Table Name,Status,StartType -AutoSize
