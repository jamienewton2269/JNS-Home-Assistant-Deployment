$ErrorActionPreference = 'Continue'

"=== SAGE NIKON CLEANUP + DISK AUDIT ==="
"Computer: $env:COMPUTERNAME"
"User: $env:USERNAME"
"PowerShell: $($PSVersionTable.PSVersion)"
""

function FreeGB {
  $d = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
  [math]::Round($d.FreeSpace/1GB,2)
}

$before = FreeGB
"Free space before: $before GB"
""

"=== PROTECTED BMW / ISTA CHECK ==="
$protected = Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue |
  Where-Object { $_.DisplayName -match 'ISTA|BMW|E-Sys|INPA|EDIABAS' } |
  Select-Object DisplayName, DisplayVersion, Publisher
$protected | Format-Table -AutoSize
""

"=== NIKON / CAMERA SOFTWARE TARGETS ==="
$targets = @(
  @{Name='Camera Control Pro 2'; Product='{C00C5AEF-85D0-4418-B1B1-EC6DDE1E2EB8}'},
  @{Name='CameraRC Deluxe'; Product='{A45815E7-634D-4CD3-A63A-85ABE4D15101}'},
  @{Name='Nikon Message Center 2'; Product='{B014EE44-9197-4513-9613-71E6EB1B514E}'},
  @{Name='Nikon Transfer 2'; Product='{3FC564E4-C8EA-4887-AEF3-268962172514}'},
  @{Name='NX Studio'; Product='{32FBAED5-A1FE-4BB9-B727-4DF8F14768D5}'},
  @{Name='Picture Control Utility 2'; Product='{C03DA72C-DE1F-4628-9CA0-53AFAE96C05F}'}
)

$installed = Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue

foreach ($t in $targets) {
  $hit = $installed | Where-Object { $_.DisplayName -eq $t.Name } | Select-Object -First 1
  if ($hit) {
    "Removing: $($t.Name)"
    $p = Start-Process msiexec.exe -ArgumentList @('/x', $t.Product, '/qn', '/norestart') -Wait -PassThru
    "  exit=$($p.ExitCode)"
  } else {
    "Not installed: $($t.Name)"
  }
}

""
"=== VERIFY TARGETS REMOVED ==="
$remaining = Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue |
  Where-Object { $_.DisplayName -match 'Nikon|CameraRC|Camera Control Pro|NX Studio|Picture Control Utility' } |
  Select-Object DisplayName, DisplayVersion, Publisher
if ($remaining) { $remaining | Format-Table -AutoSize } else { "No matching Nikon/camera applications remain." }

""
$after = FreeGB
"Free space after: $after GB"
"Recovered: $([math]::Round($after-$before,2)) GB"
""

"=== LARGE ROOT-LEVEL DIRECTORIES (READ-ONLY AUDIT) ==="
$roots = @('C:\Users','C:\Program Files','C:\Program Files (x86)','C:\ProgramData','C:\Windows')
foreach ($root in $roots) {
  if (Test-Path $root) {
    try {
      $bytes = (Get-ChildItem -LiteralPath $root -Force -File -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
      "{0,-22} {1,10:N2} GB" -f $root, ($bytes/1GB)
    } catch {
      "{0,-22} audit-error: {1}" -f $root, $_.Exception.Message
    }
  }
}

""
"=== USER PROFILE LARGE DIRECTORIES ==="
$userRoot = 'C:\Users\jnewt'
if (Test-Path $userRoot) {
  Get-ChildItem -LiteralPath $userRoot -Directory -Force -ErrorAction SilentlyContinue | ForEach-Object {
    $p=$_.FullName
    try {
      $sum=(Get-ChildItem -LiteralPath $p -Force -File -Recurse -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
      [pscustomobject]@{Folder=$p; GB=[math]::Round($sum/1GB,2)}
    } catch {}
  } | Sort-Object GB -Descending | Select-Object -First 20 | Format-Table -AutoSize
}

""
"=== FINAL BMW / ISTA CHECK ==="
Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue |
  Where-Object { $_.DisplayName -match 'ISTA|BMW|E-Sys|INPA|EDIABAS' } |
  Select-Object DisplayName, DisplayVersion, Publisher |
  Format-Table -AutoSize
