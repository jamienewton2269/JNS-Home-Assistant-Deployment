$ErrorActionPreference = 'Continue'
$root = 'C:\src\JNS-WESTMINSTER-CHIMES\WestminsterSkill'
Write-Output '=== WESTMINSTER SAGE DIAGNOSTICS ==='
Write-Output "host=$env:COMPUTERNAME"
Write-Output "runner_identity=$([Security.Principal.WindowsIdentity]::GetCurrent().Name)"
Write-Output "project_exists=$(Test-Path -LiteralPath $root)"
Write-Output "git_command_present=$([bool](Get-Command git -ErrorAction SilentlyContinue))"
Write-Output "python_command_present=$([bool](Get-Command python -ErrorAction SilentlyContinue))"
Write-Output "ask_command_present=$([bool](Get-Command ask -ErrorAction SilentlyContinue))"
Write-Output "npm_command_present=$([bool](Get-Command npm -ErrorAction SilentlyContinue))"
foreach ($p in @('lambda\lambda_function.py','skill-package\interactionModels\custom\en-GB.json','.git')) {
  $f=Join-Path $root $p
  Write-Output "file=$p exists=$(Test-Path -LiteralPath $f)"
}
foreach ($p in @('C:\Users\jnewt\AppData\Roaming\npm\ask.cmd','C:\Users\jnewt\AppData\Roaming\ask','C:\Users\jnewt\.ask')) {
  Write-Output "candidate_exists=$(Test-Path -LiteralPath $p) candidate_type=$(Split-Path -Leaf $p)"
}
if (Get-Command git -ErrorAction SilentlyContinue) {
  Write-Output '=== GIT DIAGNOSTIC ==='
  & git -C $root status --porcelain=v1 2>&1 | Select-Object -First 15 | ForEach-Object { Write-Output "$_" }
  Write-Output "git_exit=$LASTEXITCODE"
}
Write-Output '=== DIAGNOSTICS COMPLETE; NO CHANGES ==='
