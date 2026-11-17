$ErrorActionPreference='Stop'
$root='C:\src\JNS-WESTMINSTER-CHIMES\WestminsterSkill'
Write-Output '=== WESTMINSTER SOURCE VALIDATION ==='
$py=Join-Path $root 'lambda\lambda_function.py'
$model=Join-Path $root 'skill-package\interactionModels\custom\en-GB.json'
$code=[IO.File]::ReadAllText($py)
$pyexe=(Get-Command python -ErrorAction Stop).Source
$p=New-Object Diagnostics.ProcessStartInfo
$p.FileName=$pyexe
$p.Arguments='-c "import ast,sys;ast.parse(sys.stdin.read());print(''PYTHON_SYNTAX_OK'')"'
$p.UseShellExecute=$false
$p.RedirectStandardInput=$true
$p.RedirectStandardOutput=$true
$p.RedirectStandardError=$true
$proc=[Diagnostics.Process]::Start($p)
$proc.StandardInput.Write($code)
$proc.StandardInput.Close()
$out=$proc.StandardOutput.ReadToEnd()
$err=$proc.StandardError.ReadToEnd()
$proc.WaitForExit()
Write-Output $out.Trim()
if($proc.ExitCode -ne 0){throw "Python syntax failed: $err"}
$modelObj=Get-Content -LiteralPath $model -Raw | ConvertFrom-Json
if($modelObj.interactionModel.languageModel.invocationName -ne 'westminster chimes'){throw 'Unexpected invocation'}
Write-Output 'INTERACTION_MODEL_JSON_OK'
Write-Output '=== REPOSITORY STATUS ==='
& git -c "safe.directory=$root" -C $root status --short 2>&1 | ForEach-Object {Write-Output "$_"}
if($LASTEXITCODE -ne 0){throw "git status failed"}
Write-Output '=== GIT BRANCH ==='
& git -c "safe.directory=$root" -C $root branch --show-current
Write-Output 'VALIDATION_COMPLETE_NO_DEPLOYMENT'
