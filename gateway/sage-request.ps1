$ErrorActionPreference = 'Stop'
Write-Output '=== SAGE TRANSFER DESTINATION PREFLIGHT ==='
Write-Output "Host: $env:COMPUTERNAME"
$root='\\127.0.0.1\d'
$destination=Join-Path $root 'Knott Migration External'
Write-Output "Share available: $(Test-Path -LiteralPath $root)"
if (-not (Test-Path -LiteralPath $root)) { Write-Output 'RESULT: BLOCKED - local share unavailable to runner'; exit 0 }
try {
  $folder=New-Item -ItemType Directory -Path $destination -Force
  Write-Output "Destination created/available: $(Test-Path -LiteralPath $destination)"
  Write-Output 'RESULT: DESTINATION READY'
} catch {
  Write-Output "RESULT: DESTINATION ERROR ($($_.Exception.GetType().Name))"
  exit 0
}
Write-Output '=== SHAREPOINT ACCESS PREFLIGHT ==='
$syncroots = Get-ChildItem 'Env:' | Where-Object { $_.Name -like '*OneDrive*' } | ForEach-Object { $_.Value } | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
Write-Output "Visible OneDrive sync roots: $(@($syncroots).Count)"
Write-Output 'No confidential SharePoint files or authentication data were read, uploaded, or logged.'
