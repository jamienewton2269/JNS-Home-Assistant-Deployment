$ErrorActionPreference = 'Continue'

"=== SAGE CONNECTION TEST ==="
"Computer: $env:COMPUTERNAME"
"User: $env:USERNAME"
"PowerShell: $($PSVersionTable.PSVersion)"
"OS:"
Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, BuildNumber, OSArchitecture
""
"Disk:"
Get-PSDrive C | Select-Object Name,
  @{Name='UsedGB';Expression={[math]::Round($_.Used/1GB,2)}},
  @{Name='FreeGB';Expression={[math]::Round($_.Free/1GB,2)}}
""
"GitHub runner service:"
Get-Service | Where-Object { $_.Name -like 'actions.runner.*' } | Select-Object Name, Status, StartType

# trigger-after-runner-connected
