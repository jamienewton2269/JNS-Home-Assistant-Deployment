$ErrorActionPreference='Continue'
"=== SAGE NIKON UNINSTALL + DISK PROBE ==="
"Computer: $env:COMPUTERNAME"
""

"=== WINDOWS INSTALLER SERVICE ==="
Get-Service msiserver | Select-Object Name,Status,StartType | Format-Table -AutoSize
""

"=== NIKON/CAMERA UNINSTALL ENTRIES ==="
Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue |
 Where-Object { $_.DisplayName -match 'Nikon|CameraRC|Camera Control Pro|NX Studio|Picture Control Utility' } |
 Select-Object DisplayName,DisplayVersion,PSChildName,UninstallString,QuietUninstallString,InstallLocation |
 Format-List

"=== TOP-LEVEL C: DIRECTORY SIZES ==="
Get-ChildItem C:\ -Force -Directory -ErrorAction SilentlyContinue | ForEach-Object {
 $p=$_.FullName
 try {
   $sum=(Get-ChildItem -LiteralPath $p -Force -File -Recurse -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
   [pscustomobject]@{Folder=$p;GB=[math]::Round($sum/1GB,2)}
 } catch {}
} | Sort-Object GB -Descending | Format-Table -AutoSize

"=== LARGE ROOT FILES ==="
Get-ChildItem C:\ -Force -File -ErrorAction SilentlyContinue |
 Select-Object FullName,@{N='GB';E={[math]::Round($_.Length/1GB,2)}} |
 Sort-Object GB -Descending | Format-Table -AutoSize

"=== VSS / SYSTEM STORAGE ==="
vssadmin list shadowstorage
""
"=== FINAL BMW / ISTA CHECK ==="
Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue |
 Where-Object { $_.DisplayName -match 'ISTA|BMW|E-Sys|INPA|EDIABAS' } |
 Select-Object DisplayName,DisplayVersion,Publisher |
 Format-Table -AutoSize
