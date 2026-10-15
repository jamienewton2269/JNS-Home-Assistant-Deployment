# JNS ScamShield validation scaffold: audit-only, NOT a customer installer.
[CmdletBinding()]
param(
    [switch]$Audit,
    [string]$ReportPath = (Join-Path $env:TEMP 'scamshield-audit.json')
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not $Audit) { throw 'This source is audit-only. Customer deployment is not implemented or approved.' }
$def = [ordered]@{
    Available = $false
    AMRunningMode = 'Unknown'
    RealTimeProtectionEnabled = $null
    AntivirusEnabled = $null
    BehaviorMonitorEnabled = $null
    IsTamperProtected = $null
    AntivirusSignatureAge = $null
    PUAProtection = $null
    Error = $null
}
try {
    $status = Get-MpComputerStatus -ErrorAction Stop
    $preferences = Get-MpPreference -ErrorAction Stop
    $def.Available = $true
    foreach ($name in @('AMRunningMode','RealTimeProtectionEnabled','AntivirusEnabled','BehaviorMonitorEnabled','IsTamperProtected','AntivirusSignatureAge')) {
        if ($status.PSObject.Properties.Name -contains $name) { $def[$name] = $status.$name }
    }
    if ($preferences.PSObject.Properties.Name -contains 'PUAProtection') { $def.PUAProtection = $preferences.PUAProtection }
} catch { $def.Error = $_.Exception.Message }
$policyTargets = @(
    @{ Browser='Edge'; Path='HKLM:\SOFTWARE\Policies\Microsoft\Edge'; Names=@('DefaultNotificationsSetting','DefaultPopupsSetting','SmartScreenEnabled') },
    @{ Browser='Chrome'; Path='HKLM:\SOFTWARE\Policies\Google\Chrome'; Names=@('DefaultNotificationsSetting','DefaultPopupsSetting') },
    @{ Browser='Windows'; Path='HKLM:\SOFTWARE\Policies\Microsoft\Windows\System'; Names=@('EnableSmartScreen','ShellSmartScreenLevel') }
)
$policies = @(
    foreach ($target in $policyTargets) {
        foreach ($name in $target.Names) {
            $value = $null
            try {
                $entry = Get-ItemProperty -LiteralPath $target.Path -Name $name -ErrorAction Stop
                $value = $entry.$name
            } catch {}
            [pscustomobject]@{ Browser=$target.Browser; Name=$name; Value=$value; Present=($null -ne $value) }
        }
    }
)
$report = [ordered]@{
    Product='JNS ScamShield'; Phase='VALIDATION_ONLY'; Timestamp=(Get-Date).ToUniversalTime().ToString('o')
    Defender=$def; BrowserPolicies=$policies
    Notes=@('No settings changed.','Policy values do not prove browser enforcement.','No customer security status is asserted.')
}
$folder = Split-Path -Parent $ReportPath
if ($folder -and -not (Test-Path -LiteralPath $folder)) { New-Item -Path $folder -ItemType Directory -Force | Out-Null }
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ReportPath -Encoding utf8
Write-Output "ScamShield audit saved to $ReportPath"
