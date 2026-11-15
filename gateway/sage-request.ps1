$ErrorActionPreference='Stop'
$root='C:\Users\jnewt\BSC-RaceBuoy'
if (!(Test-Path -LiteralPath $root)) { throw 'RaceBuoy source missing' }
'=== BSC RACEBUOY SOURCE INVENTORY ==='
Get-ChildItem -LiteralPath $root -File -Filter '*.py' | Sort-Object Name | ForEach-Object {
  $hash=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
  "$($_.Name) bytes=$($_.Length) sha256=$hash"
}
'=== GIT STATUS ==='
if (Test-Path "$root\.git") { git -C $root status --short } else { 'No git metadata in source folder' }
'=== SOURCE ONLY: no modifications performed ==='
