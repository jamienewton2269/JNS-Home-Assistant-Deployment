$ErrorActionPreference='Continue'
$root='C:\src\JNS-WESTMINSTER-CHIMES\WestminsterSkill'
Write-Output '=== ALEXA HOSTED RESOURCE TYPE INSPECTION ==='
$p=Join-Path $root 'ask-resources.json'
try {
 $j=Get-Content -LiteralPath $p -Raw | ConvertFrom-Json
 $profile=$j.profiles.'jns-westminster'
 Write-Output "profile_present=$([bool]$profile)"
 foreach($prop in $profile.PSObject.Properties) {
  Write-Output "profile_key=$($prop.Name)"
  if($prop.Value -is [pscustomobject]) {
   Write-Output "nested_keys_$($prop.Name)=$(($prop.Value.PSObject.Properties.Name) -join ',')"
   foreach($sub in $prop.Value.PSObject.Properties) {
    if($sub.Value -is [pscustomobject]) {Write-Output "nested_keys_$($prop.Name)_$($sub.Name)=$(($sub.Value.PSObject.Properties.Name) -join ',')"}
   }
  }
 }
} catch {Write-Output "resource_error_type=$($_.Exception.GetType().Name)"}
Write-Output '=== MEDIA DEPENDENCY CAPABILITY ==='
$py=Join-Path $root 'lambda\lambda_function.py'
$src=[IO.File]::ReadAllText($py)
foreach($term in @('get_s3_presigned_url','s3','bucket','audio','<audio','AudioPlayer','ssml','mp3')) {
 Write-Output ("handler_has_"+($term -replace '[^a-zA-Z0-9]','_')+"="+$src.Contains($term))
}
Write-Output 'RESOURCE_INSPECTION_FINISHED'
