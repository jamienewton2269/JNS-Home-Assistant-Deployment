$ErrorActionPreference='Continue'
'=== SAGE FIREFOX INTERACTIVE ACCESS PREFLIGHT ==='
"Computer=$env:COMPUTERNAME"
"RunnerUser=$env:USERNAME"
"RunnerSession=$([System.Diagnostics.Process]::GetCurrentProcess().SessionId)"
'=== INTERACTIVE SESSIONS ==='
try { (query user) | Out-String } catch { "query-user unavailable: $($_.Exception.GetType().Name)" }
'=== FIREFOX PROCESS SESSIONS (NO BROWSER CONTENT) ==='
Get-Process firefox -ErrorAction SilentlyContinue | Group-Object SessionId | ForEach-Object { "Session=$($_.Name) Count=$($_.Count)" }
'=== EXPLORER PROCESS SESSIONS ==='
Get-Process explorer -ErrorAction SilentlyContinue | Group-Object SessionId | ForEach-Object { "Session=$($_.Name) Count=$($_.Count)" }
'=== UI ACCESS TEST ==='
try { Add-Type -AssemblyName System.Windows.Forms; "InteractiveDesktop=$([System.Windows.Forms.SystemInformation]::UserInteractive)" } catch { "WinForms unavailable: $($_.Exception.GetType().Name)" }
'No browser credentials or content accessed.'
