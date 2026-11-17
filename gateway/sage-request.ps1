$ErrorActionPreference='Stop'
$root='C:\src\JNS-WESTMINSTER-CHIMES\WestminsterSkill'
Write-Output '=== WESTMINSTER READ-ONLY SOURCE VALIDATION ==='
if (!(Test-Path -LiteralPath $root)) { throw 'Westminster source missing' }
$py=Join-Path $root 'lambda\lambda_function.py'
$model=Join-Path $root 'skill-package\interactionModels\custom\en-GB.json'
foreach ($f in @($py,$model)) { if (!(Test-Path -LiteralPath $f)) { throw "Missing source file" } }
$env:PYTHONDONTWRITEBYTECODE='1'
$src=[IO.File]::ReadAllText($py)
# Validate without importing third-party Alexa packages or writing pycache.
$src | python -c "import ast,sys;ast.parse(sys.stdin.read());print('PYTHON_SYNTAX_OK')"
$modelObj=Get-Content -LiteralPath $model -Raw | ConvertFrom-Json
Write-Output "invocation=$($modelObj.interactionModel.languageModel.invocationName)"
Write-Output ('intent_names=' + (($modelObj.interactionModel.languageModel.intents | ForEach-Object {$_.name}) -join ','))
Write-Output ('python_sha256=' + (Get-FileHash -LiteralPath $py -Algorithm SHA256).Hash)
Write-Output ('model_sha256=' + (Get-FileHash -LiteralPath $model -Algorithm SHA256).Hash)
Write-Output 'VALIDATION_COMPLETE_NO_DEPLOYMENT'
