$ErrorActionPreference = 'Stop'
$root = 'C:\src\JNS-WESTMINSTER-CHIMES\WestminsterSkill'
Write-Output '=== WESTMINSTER SAGE READ-ONLY PREFLIGHT ==='
Write-Output "host=$env:COMPUTERNAME"
Write-Output "project_exists=$(Test-Path -LiteralPath $root)"
$ask = Join-Path $env:APPDATA 'npm\ask.cmd'
Write-Output "ask_cli_exists=$(Test-Path -LiteralPath $ask)"
if (Test-Path -LiteralPath $root) {
  Write-Output '=== GIT STATUS ==='
  git -C $root status --short
  Write-Output '=== LOCAL SOURCE ==='
  foreach ($p in @('lambda\lambda_function.py','skill-package\interactionModels\custom\en-GB.json')) {
    $f = Join-Path $root $p
    if (Test-Path -LiteralPath $f) {
      $hash = (Get-FileHash -LiteralPath $f -Algorithm SHA256).Hash
      Write-Output "$p exists=true sha256=$hash"
    } else { Write-Output "$p exists=false" }
  }
  Write-Output '=== GIT REMOTES (HOSTS ONLY) ==='
  git -C $root remote | ForEach-Object { Write-Output "remote=$_" }
}
Write-Output '=== NO DEPLOYMENT PERFORMED ==='
