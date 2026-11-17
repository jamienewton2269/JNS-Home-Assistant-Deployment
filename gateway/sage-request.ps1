$ErrorActionPreference='Continue'
$root='C:\src\JNS-WESTMINSTER-CHIMES\WestminsterSkill'
Write-Output '=== WESTMINSTER FEATURE INVENTORY (NO SOURCE OR SECRETS) ==='
$py=Join-Path $root 'lambda\lambda_function.py'
$model=Join-Path $root 'skill-package\interactionModels\custom\en-GB.json'
$src=[IO.File]::ReadAllText($py)
$m=Get-Content -LiteralPath $model -Raw | ConvertFrom-Json
$intentNames=@($m.interactionModel.languageModel.intents | ForEach-Object {$_.name})
Write-Output "intent_count=$($intentNames.Count)"
foreach($term in @('TestConnectionIntent','AudioPlayer','SSML','<audio','westminster','christmas','quiet','schedule','LaunchRequest')) {
 Write-Output ("source_contains_"+($term -replace '[^a-zA-Z0-9]','_')+"="+$src.Contains($term))
}
Write-Output "source_line_count=$(($src -split '`n').Count)"
Write-Output "requirements_present=$(Test-Path (Join-Path $root 'lambda\requirements.txt'))"
$audioExt=@('.mp3','.wav','.ogg','.m4a')
$audio=@(Get-ChildItem -LiteralPath $root -File -Recurse -ErrorAction SilentlyContinue | Where-Object {$audioExt -contains $_.Extension.ToLowerInvariant()})
Write-Output "bundled_audio_count=$($audio.Count)"
Write-Output "bundled_audio_total_bytes=$(($audio | Measure-Object -Property Length -Sum).Sum)"
Write-Output 'INVENTORY_FINISHED_NO_DEPLOYMENT'
