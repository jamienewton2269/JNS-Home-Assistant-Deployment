$ErrorActionPreference='Continue'
$root='C:\src\JNS-WESTMINSTER-CHIMES\WestminsterSkill'
Write-Output '=== WESTMINSTER ACCESS CHECK ==='
Write-Output "identity=$([Security.Principal.WindowsIdentity]::GetCurrent().Name)"
foreach($rel in @('lambda\lambda_function.py','skill-package\interactionModels\custom\en-GB.json')) {
 $p=Join-Path $root $rel
 try {
  $bytes=[IO.File]::ReadAllBytes($p)
  $hash=[Security.Cryptography.SHA256]::Create().ComputeHash($bytes)
  Write-Output ("file="+$rel+" readable=true bytes="+$bytes.Length+" sha256="+[BitConverter]::ToString($hash).Replace('-',''))
  if($rel.EndsWith('.json')) {
   $obj=[Text.Encoding]::UTF8.GetString($bytes) | ConvertFrom-Json
   Write-Output ("invocation="+$obj.interactionModel.languageModel.invocationName)
   Write-Output ("intents="+(($obj.interactionModel.languageModel.intents | ForEach-Object {$_.name}) -join ','))
  }
 } catch {
  Write-Output ("file="+$rel+" readable=false error_type="+$_.Exception.GetType().Name)
 }
}
Write-Output 'ACCESS_CHECK_FINISHED'
