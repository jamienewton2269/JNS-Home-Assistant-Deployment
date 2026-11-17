$ErrorActionPreference='Continue'
$root='C:\src\JNS-WESTMINSTER-CHIMES\WestminsterSkill'
Write-Output '=== WESTMINSTER AMAZON DEPLOYMENT READINESS ==='
Write-Output "identity=$([Security.Principal.WindowsIdentity]::GetCurrent().Name)"
Write-Output "project_present=$(Test-Path -LiteralPath $root)"
foreach($name in @('ask','aws','git','npm','node')) {
 $c=Get-Command $name -ErrorAction SilentlyContinue
 Write-Output "tool_$($name)_available=$([bool]$c)"
}
$askPath='C:\Users\jnewt\AppData\Roaming\npm\ask.cmd'
try {Write-Output "user_ask_accessible=$(Test-Path -LiteralPath $askPath -ErrorAction Stop)"} catch {Write-Output 'user_ask_accessible=false'}
try {
 $remote=(& git -c "safe.directory=C:/src/JNS-WESTMINSTER-CHIMES/WestminsterSkill" -C $root remote get-url origin 2>$null)
 if($LASTEXITCODE -eq 0 -and $remote -match '^https://git-codecommit[.]us-east-1[.]amazonaws[.]com/') {Write-Output 'amazon_codecommit_remote_configured=true'} else {Write-Output 'amazon_codecommit_remote_configured=false'}
} catch {Write-Output 'amazon_codecommit_remote_configured=false'}
foreach($rel in @('skill-package\skill.json','skill-package\interactionModels\custom\en-GB.json','lambda\lambda_function.py','lambda\requirements.txt')) {
 Write-Output "source_$($rel.Replace('\','_'))=$(Test-Path -LiteralPath (Join-Path $root $rel))"
}
Write-Output 'READINESS_CHECK_FINISHED_NO_DEPLOYMENT'
