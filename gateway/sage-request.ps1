$ErrorActionPreference='Continue'
$root='C:\src\JNS-WESTMINSTER-CHIMES\WestminsterSkill'
Write-Output '=== ALEXA HOSTED MEDIA CONFIGURATION CHECK ==='
foreach($rel in @('ask-resources.json','.ask\ask-states.json','skill-package\skill.json')) {
 $p=Join-Path $root $rel
 try {
  $json=Get-Content -LiteralPath $p -Raw | ConvertFrom-Json
  Write-Output "file=$rel valid_json=true"
  if($rel -eq 'ask-resources.json') {
   Write-Output "resource_keys=$(($json.PSObject.Properties.Name) -join ',')"
   foreach($prop in $json.PSObject.Properties) {
    Write-Output "resource_$($prop.Name)_keys=$(($prop.Value.PSObject.Properties.Name) -join ',')"
   }
  }
  if($rel -eq 'skill-package\skill.json') {
   Write-Output "manifest_keys=$(($json.manifest.PSObject.Properties.Name) -join ',')"
  }
 } catch {Write-Output "file=$rel valid_json=false error_type=$($_.Exception.GetType().Name)"}
}
Write-Output '=== AUDIO FILE LOCATIONS (NAMES ONLY) ==='
foreach($d in @('lambda','skill-package','assets','media')) {
 $p=Join-Path $root $d
 if(Test-Path $p) {
  Get-ChildItem -LiteralPath $p -Recurse -File -ErrorAction SilentlyContinue | Where-Object {$_.Extension -in @('.mp3','.wav','.ogg')} | Select-Object -First 20 | ForEach-Object {Write-Output "audio=$($_.Name) size=$($_.Length)"}
 }
}
Write-Output 'MEDIA_CONFIGURATION_CHECK_FINISHED'
