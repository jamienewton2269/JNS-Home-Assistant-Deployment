$ErrorActionPreference='Continue'
$root='C:\src\JNS-WESTMINSTER-CHIMES\WestminsterSkill'
Write-Output '=== WESTMINSTER AUDIO BUILD READINESS ==='
foreach($n in @('ffmpeg','ffprobe','sox','python','pip','git')) {
 $c=Get-Command $n -ErrorAction SilentlyContinue
 Write-Output "tool_$($n)_available=$([bool]$c)"
}
& python -c 'import importlib.util;print("numpy_available="+str(importlib.util.find_spec("numpy") is not None));print("pydub_available="+str(importlib.util.find_spec("pydub") is not None))' 2>&1 | ForEach-Object {Write-Output "$_"}
Write-Output '=== ALEXA HOSTED PROJECT FILES ==='
foreach($rel in @('ask-resources.json','.ask\ask-states.json','skill-package\skill.json','lambda\lambda_function.py','lambda\requirements.txt')) {
 Write-Output "present_$($rel.Replace('\','_').Replace('.','_'))=$(Test-Path (Join-Path $root $rel))"
}
Write-Output '=== AMAZON DEPLOYMENT ACCESS METHODS ==='
foreach($p in @('C:\Program Files\Amazon\AWSCLIV2\aws.exe','C:\Users\jnewt\AppData\Roaming\npm\ask.cmd')) {
 try { $item=Get-Item -LiteralPath $p -ErrorAction Stop; Write-Output "path_$($item.Name)_accessible=true" } catch {Write-Output "path_$([IO.Path]::GetFileName($p))_accessible=false"}
}
Write-Output 'AUDIO_READINESS_FINISHED'
