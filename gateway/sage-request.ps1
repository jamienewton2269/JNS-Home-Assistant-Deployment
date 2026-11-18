$ErrorActionPreference='Continue'
$root='C:\src\JNS-WESTMINSTER-CHIMES'
Write-Output '=== WESTMINSTER AUDIO ASSET DISCOVERY ==='
$roots=@('C:\src\JNS-WESTMINSTER-CHIMES','C:\src\JNS-SHIP-BELLS','C:\src\JNS-Home-Assistant-Deployment')
foreach($dir in $roots) {
 Write-Output "directory_present_$([IO.Path]::GetFileName($dir))=$(Test-Path -LiteralPath $dir)"
 if(Test-Path -LiteralPath $dir) {
  $audio=@(Get-ChildItem -LiteralPath $dir -File -Recurse -ErrorAction SilentlyContinue | Where-Object {$_.Extension.ToLowerInvariant() -in @('.mp3','.wav','.ogg','.flac','.m4a')})
  Write-Output "audio_count_$([IO.Path]::GetFileName($dir))=$($audio.Count)"
  $audio | Select-Object -First 30 | ForEach-Object {Write-Output "audio_name=$($_.Name) bytes=$($_.Length)"}
 }
}
Write-Output 'AUDIO_DISCOVERY_COMPLETE'
