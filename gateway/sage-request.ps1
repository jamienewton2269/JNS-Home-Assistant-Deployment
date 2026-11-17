$ErrorActionPreference='Continue'
$root='C:\src\JNS-WESTMINSTER-CHIMES\WestminsterSkill'
Write-Output '=== WESTMINSTER PYTHON COMPILATION TEST ==='
$py=Join-Path $root 'lambda\lambda_function.py'
$env:PYTHONPYCACHEPREFIX=Join-Path $env:TEMP 'jns-westminster-pycache'
& python -m py_compile $py 2>&1 | ForEach-Object {Write-Output "$_"}
Write-Output "python_compile_exit=$LASTEXITCODE"
$m=Get-Content -LiteralPath (Join-Path $root 'skill-package\interactionModels\custom\en-GB.json') -Raw | ConvertFrom-Json
Write-Output "invocation=$($m.interactionModel.languageModel.invocationName)"
Write-Output "intents=$(($m.interactionModel.languageModel.intents | ForEach-Object {$_.name}) -join ',')"
& git -c "safe.directory=C:/src/JNS-WESTMINSTER-CHIMES/WestminsterSkill" -C $root status --short 2>&1 | ForEach-Object {Write-Output "$_"}
Write-Output "git_exit=$LASTEXITCODE"
Write-Output 'TEST_FINISHED'
