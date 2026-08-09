param(
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$FrontendRoot = Join-Path $RepoRoot "frontend"
$BackendRoot = Join-Path $RepoRoot "backend"
$PythonPath = Join-Path $RepoRoot "venv\Scripts\python.exe"
$LogRoot = Join-Path $RepoRoot "data\runtime"
New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null

$address = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" -and $_.InterfaceAlias -notmatch "Loopback|vEthernet|Virtual" } |
    Sort-Object InterfaceMetric |
    Select-Object -First 1 -ExpandProperty IPAddress
if (-not $address) {
    throw "No LAN IPv4 address was found. Connect this computer to Wi-Fi first."
}

function Test-ListeningPort([int]$Port) {
    return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

if (-not $NoStart) {
    if (-not (Test-ListeningPort 8000)) {
        if (-not (Test-Path $PythonPath)) { throw "Python virtual environment not found at $PythonPath." }
        Start-Process -FilePath $PythonPath -WorkingDirectory $BackendRoot -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000") -WindowStyle Hidden -RedirectStandardOutput (Join-Path $LogRoot "backend-lan.log") -RedirectStandardError (Join-Path $LogRoot "backend-lan-error.log")
    }
    if (-not (Test-ListeningPort 5173)) {
        Start-Process -FilePath "npm.cmd" -WorkingDirectory $FrontendRoot -ArgumentList @("run", "dev:lan") -WindowStyle Hidden -RedirectStandardOutput (Join-Path $LogRoot "frontend-lan.log") -RedirectStandardError (Join-Path $LogRoot "frontend-lan-error.log")
    }
}

$deadline = (Get-Date).AddSeconds(15)
while ((Get-Date) -lt $deadline -and (-not (Test-ListeningPort 5173) -or -not (Test-ListeningPort 8000))) {
    Start-Sleep -Milliseconds 500
}

$desktopUrl = "http://127.0.0.1:5173"
$mobileUrl = "http://${address}:5173"
Write-Host ""
Write-Host "GDUF Super Senior is ready:" -ForegroundColor Cyan
Write-Host "  Desktop: $desktopUrl"
Write-Host "  Mobile:  $mobileUrl"
Write-Host "  API: same-origin requests are proxied from $mobileUrl/api."
Write-Host ""
Write-Host "Keep the phone and computer on the same Wi-Fi. This script does not change Windows Firewall."

foreach ($port in 5173, 8000) {
    $listening = Test-ListeningPort $port
    $probe = Test-NetConnection -ComputerName $address -Port $port -WarningAction SilentlyContinue
    Write-Host ("Port {0}: listening={1}, LAN reachable={2}" -f $port, $listening, $probe.TcpTestSucceeded)
}

try {
    $health = Invoke-RestMethod "http://127.0.0.1:8000/health" -TimeoutSec 3
    $agent = Invoke-RestMethod "http://127.0.0.1:8000/api/agent/status" -TimeoutSec 3
    Write-Host ("Health: {0}; Agent: backend={1}, llm_configured={2}, database={3}" -f $health.status, $agent.backend, $agent.llm_configured, $agent.database)
} catch {
    Write-Warning "Health check failed: $($_.Exception.Message)"
}

if ((Test-ListeningPort 5173) -and -not (Test-NetConnection -ComputerName $address -Port 5173 -WarningAction SilentlyContinue).TcpTestSucceeded) {
    Write-Warning "The frontend is only reachable locally. Allow Node.js inbound access on private networks in Windows Firewall; the script will not change that rule."
}
