#requires -Version 5.1
<#
JNS Windows Management Console v5.5.2 hotfix updater

Fixes:
- Extends management-PC enrollment HTTP timeout from 30s to 180s.
- Adds a specific enrollment timeout diagnostic.
- Updates the Windows Manager version labels to v5.5.2.
- Refreshes the bundled JNS Deployment Platform source to the validated
  v5.5.2 GitHub merge commit.
- Preserves the Windows DPAPI vault and all existing private credentials.
#>

[CmdletBinding()]
param(
    [string]$JnsRoot = "C:\Projects\Tools\JNS-HA_WMC",
    [switch]$NoLaunch
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$Version = "5.5.2"
$RepoUrl = "https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment.git"
$PinnedCommit = "43c3edd3d42b714013bfc635be22b5fc3dc8a2e8"

$ManagerRoot = $JnsRoot
$Current = Join-Path $ManagerRoot "current"
$BackupRoot = Join-Path $JnsRoot "backups"
$LogRoot = Join-Path $JnsRoot "logs"
$VersionFile = Join-Path $ManagerRoot "CURRENT_VERSION.txt"

function Section([string]$x) {
    Write-Host "`n===============================================================================" -ForegroundColor DarkCyan
    Write-Host " $x" -ForegroundColor Cyan
    Write-Host "===============================================================================" -ForegroundColor DarkCyan
}
function Pass([string]$x) { Write-Host "[PASS] $x" -ForegroundColor Green }
function Info([string]$x) { Write-Host "[INFO] $x" -ForegroundColor Cyan }
function Warn([string]$x) { Write-Host "[WARN] $x" -ForegroundColor Yellow }

function Write-Utf8NoBom([string]$Path, [string]$Text) {
    $enc = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($Path, $Text, $enc)
}

if (-not (Test-Path -LiteralPath $Current)) {
    throw "Existing JNS Windows Manager not found at $Current."
}

$EnrollmentPy = Join-Path $Current "jns_enrollment.py"
$ManagerPy = Join-Path $Current "JNS_HA_Windows_Manager.pyw"
$TestsDir = Join-Path $Current "tests"
$ResourceRepo = Join-Path $Current "resources\jns_v5_repository"
$Python = Join-Path $Current ".venv\Scripts\python.exe"

foreach ($required in @($EnrollmentPy, $ManagerPy, $TestsDir, $Python)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required Windows Manager component is missing: $required"
    }
}

$Git = (Get-Command git.exe -ErrorAction Stop).Source

New-Item -ItemType Directory -Force -Path $BackupRoot,$LogRoot | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Backup = Join-Path $BackupRoot "WindowsManager_pre_v5.5.2_$stamp"
$Log = Join-Path $LogRoot "JNS_Windows_Manager_v5.5.2_Hotfix_$stamp.log"
Start-Transcript -Path $Log -Force | Out-Null

$TempRoot = Join-Path ([IO.Path]::GetTempPath()) ("JNS-v5.5.2-" + [guid]::NewGuid().ToString("N"))
$TempRepo = Join-Path $TempRoot "repo"

try {
    Section "JNS WINDOWS MANAGER v5.5.2 HOTFIX"
    Info "Manager: $Current"
    Info "DPAPI vault under %APPDATA%\JNS\WindowsManager is not copied, replaced or reset."

    Section "1. BACK UP CURRENT MANAGER SOURCE"
    New-Item -ItemType Directory -Force -Path $Backup | Out-Null
    & robocopy.exe $Current $Backup /E /XD ".venv" "__pycache__" /XF "*.pyc" /NFL /NDL /NJH /NJS /NP | Out-Host
    $rc = $LASTEXITCODE
    if ($rc -gt 7) { throw "Windows Manager source backup failed. robocopy exit code: $rc" }
    Pass "Rollback source copy created at $Backup"

    Section "2. PATCH ENROLLMENT TIMEOUT"
    $text = [IO.File]::ReadAllText($EnrollmentPy)

    if ($text.Contains("timeout: int = 30) -> dict:")) {
        $text = $text.Replace("timeout: int = 30) -> dict:", "timeout: int = 180) -> dict:")
    } elseif (-not $text.Contains("timeout: int = 180) -> dict:")) {
        throw "Could not locate the expected management-PC enrollment timeout definition."
    }

    if (-not $text.Contains("except TimeoutError as exc:")) {
        $needle = "    except error.HTTPError as exc:"
        if (-not $text.Contains($needle)) {
            throw "Could not locate the enrollment HTTP error handler."
        }
        $replacement = @'
    except TimeoutError as exc:
        raise EnrollmentError(
            "Home Assistant enrollment did not complete within 180 seconds. "
            "Check Home Assistant JNS management-PC status before issuing a fresh code."
        ) from exc
    except error.HTTPError as exc:
'@
        $rx = New-Object System.Text.RegularExpressions.Regex([regex]::Escape($needle))
        $text = $rx.Replace($text, $replacement, 1)
    }

    Write-Utf8NoBom $EnrollmentPy $text
    if (-not ([IO.File]::ReadAllText($EnrollmentPy)).Contains("timeout: int = 180) -> dict:")) {
        throw "Enrollment timeout patch did not persist."
    }
    Pass "Enrollment request timeout extended to 180 seconds."

    Section "3. UPDATE WINDOWS MANAGER VERSION LABELS"
    $managerText = [IO.File]::ReadAllText($ManagerPy)
    $managerText = $managerText.Replace('VERSION = "5.5.0"', 'VERSION = "5.5.2"')
    $managerText = $managerText.Replace('VERSION = "5.5.1"', 'VERSION = "5.5.2"')
    $managerText = $managerText.Replace(
        'TARGET_PLATFORM = "JNS Home Assistant Deployment Platform v5.5.0"',
        'TARGET_PLATFORM = "JNS Home Assistant Deployment Platform v5.5.2"'
    )
    $managerText = $managerText.Replace(
        'TARGET_PLATFORM = "JNS Home Assistant Deployment Platform v5.5.1"',
        'TARGET_PLATFORM = "JNS Home Assistant Deployment Platform v5.5.2"'
    )
    Write-Utf8NoBom $ManagerPy $managerText

    Get-ChildItem -LiteralPath $TestsDir -File -Filter "*.py" | ForEach-Object {
        $t = [IO.File]::ReadAllText($_.FullName)
        if ($t.Contains("5.5.0")) {
            $t = $t.Replace("5.5.0", "5.5.2")
            Write-Utf8NoBom $_.FullName $t
        }
        if ($t.Contains("5.5.1")) {
            $t = $t.Replace("5.5.1", "5.5.2")
            Write-Utf8NoBom $_.FullName $t
        }
    }
    Pass "Windows Manager and regression-test version labels updated."

    Section "4. SYNC VALIDATED v5.5.2 PLATFORM SOURCE"
    New-Item -ItemType Directory -Force -Path $TempRoot | Out-Null

    & $Git clone --quiet --no-checkout $RepoUrl $TempRepo
    if ($LASTEXITCODE -ne 0) { throw "Git clone failed." }

    & $Git -C $TempRepo fetch --quiet --depth 1 origin $PinnedCommit
    if ($LASTEXITCODE -ne 0) { throw "Could not fetch pinned JNS v5.5.2 commit." }

    & $Git -C $TempRepo checkout --quiet --detach $PinnedCommit
    if ($LASTEXITCODE -ne 0) { throw "Could not check out pinned JNS v5.5.2 commit." }

    $actualCommit = (& $Git -C $TempRepo rev-parse HEAD).Trim().ToLowerInvariant()
    if ($actualCommit -ne $PinnedCommit.ToLowerInvariant()) {
        throw "Repository integrity check failed. Expected $PinnedCommit, got $actualCommit."
    }

    $manifest = Join-Path $TempRepo "custom_components\jns_deployment\manifest.json"
    $manifestJson = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
    if ([string]$manifestJson.version -ne "5.5.2") {
        throw "Pinned repository does not report JNS integration v5.5.2."
    }

    New-Item -ItemType Directory -Force -Path $ResourceRepo | Out-Null
    & robocopy.exe $TempRepo $ResourceRepo /MIR /XD ".git" "__pycache__" /XF "*.pyc" /NFL /NDL /NJH /NJS /NP | Out-Host
    $rc = $LASTEXITCODE
    if ($rc -gt 7) { throw "Bundled platform source refresh failed. robocopy exit code: $rc" }

    Pass "Bundled platform source pinned to $PinnedCommit"

    Section "5. RUN REGRESSION CHECKS"
    & $Python -m py_compile $EnrollmentPy $ManagerPy
    if ($LASTEXITCODE -ne 0) { throw "Python compile check failed." }

    foreach ($test in @(
        "static_test.py",
        "management_pc_enrollment_test.py",
        "kiss_ui_test.py",
        "background_progress_test.py",
        "v5_compatibility_test.py"
    )) {
        $testPath = Join-Path $TestsDir $test
        if (-not (Test-Path -LiteralPath $testPath)) { throw "Missing regression test: $test" }
        & $Python $testPath
        if ($LASTEXITCODE -ne 0) { throw "Regression check failed: $test" }
    }
    Pass "Windows Manager v5.5.2 regression checks passed."

    Section "6. COMPLETE"
    Set-Content -LiteralPath $VersionFile -Value "5.5.2" -Encoding ASCII
    Write-Host "Windows Manager v5.5.2 hotfix installed." -ForegroundColor Green
    Write-Host ""
    Write-Host "Next: update Home Assistant JNS Deployment Platform to v5.5.2 in HACS and restart Home Assistant." -ForegroundColor Cyan
    Write-Host "Then create a NEW one-time enrollment code and retry ENROLL THIS PC." -ForegroundColor Cyan
    Write-Host "Do not revoke legacy credentials until COMMISSION THIS PC passes deployment + rollback." -ForegroundColor Yellow
    Write-Host "Log: $Log"

    if (-not $NoLaunch) {
        $launcher = Join-Path $JnsRoot "Launch-JNS-Management-Console.ps1"
        if (Test-Path -LiteralPath $launcher) {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $launcher
        }
    }
}
catch {
    Write-Host "`n[FAIL] JNS v5.5.2 Windows Manager hotfix failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Existing DPAPI secrets were not deliberately changed." -ForegroundColor Yellow
    Write-Host "Rollback source copy: $Backup" -ForegroundColor Yellow
    exit 1
}
finally {
    try { Stop-Transcript | Out-Null } catch {}
    Remove-Item -LiteralPath $TempRoot -Recurse -Force -ErrorAction SilentlyContinue
}