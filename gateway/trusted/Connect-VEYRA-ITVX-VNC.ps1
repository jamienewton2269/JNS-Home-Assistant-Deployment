# VEYRA ITVX VNC — Windows PowerShell reconnect
# Creates a local-only SSH tunnel to the existing x11vnc :92 service.
# Does not restart OBS, ITVX, Chrome, VNC or the kiosk.
param(
  [string]$RemoteHostName = 'veyra.home.arpa',
  [string]$SshUser = 'jnsadmin',
  [int]$LocalPort = 15902
)
$ErrorActionPreference = 'Stop'
$RemotePort = 5902
$Address = "127.0.0.1::$LocalPort"

function Test-TcpLocalPort([int]$Port) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $request = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
        if (-not $request.AsyncWaitHandle.WaitOne(250, $false)) { return $false }
        try { $client.EndConnect($request); return $true } catch { return $false }
    } catch { return $false } finally { $client.Close() }
}

if (-not (Get-Command ssh.exe -ErrorAction SilentlyContinue)) {
    throw 'Windows OpenSSH Client (ssh.exe) is unavailable. Enable OpenSSH Client in Windows Optional Features.'
}
Write-Host 'VEYRA ITVX remote desktop (Chrome display :92)' -ForegroundColor Cyan
Write-Host "Host: $RemoteHostName   Remote VNC port: $RemotePort"
Write-Host "Windows viewer address: $Address"
if (Test-TcpLocalPort $LocalPort) {
    Write-Warning "Local port $LocalPort is already in use. No extra SSH tunnel started."
    Write-Warning "If it is an earlier VEYRA tunnel, use $Address in your VNC viewer."
} else {
    $line = "ssh.exe -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -L 127.0.0.1:${LocalPort}:127.0.0.1:${RemotePort} ${SshUser}@${RemoteHostName}"
    Write-Host 'Opening a second PowerShell window for SSH. Supply your SSH password or approved key if prompted.'
    $proc = Start-Process -FilePath 'powershell.exe' -ArgumentList ('-NoExit -NoProfile -Command "' + $line + '"') -PassThru
    $connected = $false
    for ($n = 0; $n -lt 45; $n++) {
        if (Test-TcpLocalPort $LocalPort) { $connected = $true; break }
        if ($proc.HasExited) { break }
        Start-Sleep -Seconds 1
    }
    if (-not $connected) {
        Write-Warning 'SSH tunnel is not listening yet. Check the second window for authentication, host-key or DNS errors.'
        Write-Host "When SSH is connected, open your VNC viewer at $Address"
        return
    }
    Write-Host 'SSH tunnel established.' -ForegroundColor Green
}

$paths = @(
    (Join-Path $env:ProgramFiles 'TigerVNC\vncviewer.exe'),
    (Join-Path $env:ProgramFiles 'TightVNC\tvnviewer.exe'),
    (Join-Path $env:ProgramFiles 'UltraVNC\vncviewer.exe')
)
if (${env:ProgramFiles(x86)}) {
    $paths += (Join-Path ${env:ProgramFiles(x86)} 'TigerVNC\vncviewer.exe')
    $paths += (Join-Path ${env:ProgramFiles(x86)} 'TightVNC\tvnviewer.exe')
}
$viewer = $paths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if ($viewer) {
    # TigerVNC and TightVNC accept host::TCPport.
    if ($viewer -match 'UltraVNC') {
        Write-Host 'UltraVNC found: enter 127.0.0.1::15902 manually in its VNC server field.'
    } else {
        Write-Host "Launching $viewer $Address"
        Start-Process -FilePath $viewer -ArgumentList $Address
    }
} else {
    Write-Host "Open your installed VNC viewer and connect to: $Address" -ForegroundColor Yellow
    Write-Host 'This is a VNC address on the Windows PC, not the Lenovo LAN address.'
}
Write-Host 'Keep the SSH PowerShell window open for the VNC connection.'
