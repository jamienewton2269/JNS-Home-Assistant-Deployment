#requires -RunAsAdministrator
[CmdletBinding()]param([switch]$Uninstall)
$ErrorActionPreference='Stop'
$base=Join-Path $env:ProgramData 'JNS\ScamShield'
$task='JNS ScamShield Pilot'
if($Uninstall){
 Unregister-ScheduledTask -TaskName $task -Confirm:$false -ErrorAction SilentlyContinue
 if(Test-Path (Join-Path $base 'ScamShield.ps1')){
  & (Join-Path $base 'ScamShield.ps1') -Mode Restore
 }
 Write-Host 'ScamShield pilot scheduled task removed. Owned browser policies restored where still unchanged.'
 exit
}
$source=Join-Path $PSScriptRoot 'ScamShield.ps1'
if(!(Test-Path $source)){throw "Missing $source"}
New-Item -ItemType Directory -Path $base -Force | Out-Null
Copy-Item -LiteralPath $source -Destination (Join-Path $base 'ScamShield.ps1') -Force
& (Join-Path $base 'ScamShield.ps1') -Mode Enforce | Out-Null
$exe="$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$action=New-ScheduledTaskAction -Execute $exe -Argument ('-NoLogo -NoProfile -NonInteractive -File "{0}" -Mode Enforce' -f (Join-Path $base 'ScamShield.ps1'))
$startup=New-ScheduledTaskTrigger -AtStartup
$hourly=New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Hours 1)
$principal=New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName $task -Action $action -Trigger @($startup,$hourly) -Principal $principal -Force | Out-Null
Write-Host 'Installed pilot scheduled enforcement (startup/hourly). Restart browsers to apply policies.'
& (Join-Path $base 'ScamShield.ps1') -Mode Audit
