#requires -Version 5.1
[CmdletBinding()]
param([ValidateSet('Audit','Enforce','Restore')][string]$Mode='Audit')
$ErrorActionPreference='Stop'
$base=Join-Path $env:ProgramData 'JNS\ScamShield'
$state=Join-Path $base 'owned-policies.json'
$log=Join-Path $base 'events.log'
$policies=@(
 @{Key='SOFTWARE\Policies\Microsoft\Edge';Name='DefaultNotificationsSetting';Value=2},
 @{Key='SOFTWARE\Policies\Microsoft\Edge';Name='DefaultPopupsSetting';Value=2},
 @{Key='SOFTWARE\Policies\Microsoft\Edge';Name='SmartScreenEnabled';Value=1},
 @{Key='SOFTWARE\Policies\Google\Chrome';Name='DefaultNotificationsSetting';Value=2},
 @{Key='SOFTWARE\Policies\Google\Chrome';Name='DefaultPopupsSetting';Value=2}
)
function Log([string]$message) {
 if(!(Test-Path $base)){New-Item $base -ItemType Directory -Force | Out-Null}
 Add-Content -LiteralPath $log -Value ("{0:o} {1}" -f (Get-Date).ToUniversalTime(),$message)
}
function Get-Val($path,$name) {
 try {
  $v=Get-ItemProperty -LiteralPath $path -Name $name -ErrorAction Stop
  return @{Present=$true;Value=[int]$v.$name}
 } catch {return @{Present=$false;Value=$null}}
}
function Ensure-Admin {
 $p=[Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
 if(!$p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'Administrator rights required.'}
}
if($Mode -ne 'Audit'){Ensure-Admin}
$report=[ordered]@{Product='JNS ScamShield';Mode=$Mode;UTC=(Get-Date).ToUniversalTime().ToString('o');Policies=@();Defender=$null;Warning='Pilot only. Browser policies do not prevent every scam. Windows SmartScreen remains under Windows control.'}
if($Mode -eq 'Enforce'){
 if(!(Test-Path $base)){New-Item $base -ItemType Directory -Force | Out-Null}
 $owned=@()
 if(Test-Path $state){$owned=@(Get-Content $state -Raw | ConvertFrom-Json)}
 foreach($p in $policies){
  $key='HKLM:\'+$p.Key
  $v=Get-Val $key $p.Name
  $existing=@($owned | Where-Object {$_.Key -eq $p.Key -and $_.Name -eq $p.Name})
  if($existing.Count -eq 0){
   # Do not overwrite pre-existing managed settings from another owner.
   if($v.Present -and $v.Value -ne $p.Value){Log "SKIP pre-existing $($p.Key)\$($p.Name)";continue}
   if(!$v.Present){$owned+= [pscustomobject]@{Key=$p.Key;Name=$p.Name;OriginalPresent=$false;OriginalValue=$null;Desired=$p.Value}}
  }
  if(!(Test-Path $key)){New-Item -Path $key -Force | Out-Null}
  New-ItemProperty -Path $key -Name $p.Name -Value $p.Value -PropertyType DWord -Force | Out-Null
 }
 # Secure state for subsequent safe restore; do not overwrite original baseline.
 ConvertTo-Json -InputObject @($owned) -Depth 5 | Set-Content -LiteralPath $state -Encoding UTF8
 Log 'Applied browser policies; existing conflicting managed settings were preserved.'
}
if($Mode -eq 'Restore'){
 if(Test-Path $state){
  $owned=@(Get-Content $state -Raw | ConvertFrom-Json)
  foreach($p in $owned){
   $key='HKLM:\'+$p.Key
   $current=Get-Val $key $p.Name
   if($current.Present -and $current.Value -eq [int]$p.Desired){
    if($p.OriginalPresent){New-ItemProperty -Path $key -Name $p.Name -Value ([int]$p.OriginalValue) -PropertyType DWord -Force | Out-Null}
    else{Remove-ItemProperty -LiteralPath $key -Name $p.Name -ErrorAction SilentlyContinue}
   }else{Log "SKIP restore because policy changed externally: $($p.Name)"}
  }
  Remove-Item -LiteralPath $state -Force
  Log 'Restored owned policy values; external changes preserved.'
 }
}
foreach($p in $policies){
 $v=Get-Val ('HKLM:\'+$p.Key) $p.Name
 $report.Policies+= [pscustomobject]@{Key=$p.Key;Name=$p.Name;Current=$v.Value;Present=$v.Present;Desired=$p.Value;Matches=($v.Present -and $v.Value -eq $p.Value)}
}
try{
 $s=Get-MpComputerStatus -ErrorAction Stop
 $pref=Get-MpPreference -ErrorAction Stop
 $report.Defender=[ordered]@{Available=$true;AMRunningMode=$s.AMRunningMode;AntivirusEnabled=$s.AntivirusEnabled;RealTimeProtectionEnabled=$s.RealTimeProtectionEnabled;IsTamperProtected=$s.IsTamperProtected;BehaviorMonitorEnabled=$s.BehaviorMonitorEnabled;AntivirusSignatureAge=$s.AntivirusSignatureAge;PUAProtection=$pref.PUAProtection}
}catch{$report.Defender=[ordered]@{Available=$false;Error=$_.Exception.Message}}
$report | ConvertTo-Json -Depth 7
