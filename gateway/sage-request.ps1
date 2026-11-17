$ErrorActionPreference='Continue'
$root='C:\src\JNS-WESTMINSTER-CHIMES\WestminsterSkill'
Write-Output '=== WESTMINSTER SAFE VALIDATION ==='
$py=Join-Path $root 'lambda\lambda_function.py'
$model=Join-Path $root 'skill-package\interactionModels\custom\en-GB.json'
try {
  $bytes=[IO.File]::ReadAllBytes($py)
  Write-Output "python_readable=$($bytes.Length -gt 0)"
  $python=(Get-Command python -ErrorAction SilentlyContinue)
  Write-Output "python_available=$([bool]$python)"
  if($python) {
    $script='import ast,sys;ast.parse(open(sys.argv[1],encoding="utf-8-sig").read());print("PYTHON_SYNTAX_OK")'
    & $python.Source -c $script $py 2>&1 | ForEach-Object {Write-Output "$_"}
    Write-Output "python_exit=$LASTEXITCODE"
  }
} catch {Write-Output "python_error_type=$($_.Exception.GetType().Name)"}
try {
 $m=[IO.File]::ReadAllText($model) | ConvertFrom-Json
 Write-Output "invocation=$($m.interactionModel.languageModel.invocationName)"
} catch {Write-Output "model_error_type=$($_.Exception.GetType().Name)"}
try {
 & git -c "safe.directory=C:/src/JNS-WESTMINSTER-CHIMES/WestminsterSkill" -C $root status --short 2>&1 | Select-Object -First 20 | ForEach-Object {Write-Output "$_"}
 Write-Output "git_exit=$LASTEXITCODE"
} catch {Write-Output "git_error_type=$($_.Exception.GetType().Name)"}
Write-Output 'VALIDATION_FINISHED'
