param(
    [int]$Port = 8000,
    [string]$BindAddress = "127.0.0.1",
    [switch]$AllowRemote,
    [switch]$NoInstall,
    [switch]$NoBrowser,
    [switch]$SmokeTest
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $Root
[System.IO.Directory]::SetCurrentDirectory($Root)

if (-not $AllowRemote -and $BindAddress -notin @("127.0.0.1", "localhost", "::1")) {
    throw "Remote bind '$BindAddress' refused. Use -AllowRemote explicitly."
}

if ((Get-Location).Path -match "\\Windows\\System32$") {
    throw "Launcher safety failure: working directory resolved to System32."
}

$VenvPython = Join-Path $Root ".venv\\Scripts\\python.exe"
if (-not (Test-Path $VenvPython)) {
    $Py = Get-Command py -ErrorAction SilentlyContinue
    $Python = Get-Command python -ErrorAction SilentlyContinue
    if ($Py) {
        & py -3 -m venv .venv
    } elseif ($Python) {
        & python -m venv .venv
    } else {
        throw "Python 3 was not found. Install Python 3.11+ and run again."
    }
}

if (-not $NoInstall) {
    & $VenvPython -m pip install --disable-pip-version-check --upgrade pip
    & $VenvPython -m pip install --disable-pip-version-check -r requirements.txt
}

$Url = "http://${BindAddress}:$Port"
Write-Host ""
Write-Host "============================================================"
Write-Host " DETERMINISTIC JUNGLE CANOPY // SOVEREIGN LAUNCHER"
Write-Host "============================================================"
Write-Host "WORKING_DIRECTORY=$Root"
Write-Host "LOCAL_ONLY=$(-not $AllowRemote)"
Write-Host "CANOPY_LISTENING=$Url"
Write-Host ""

if ($SmokeTest) {
    $proc = Start-Process -FilePath $VenvPython -ArgumentList @("-m","uvicorn","server:app","--host",$BindAddress,"--port","$Port") -WorkingDirectory $Root -PassThru -WindowStyle Hidden
    try {
        $healthy = $false
        for ($i = 0; $i -lt 60; $i++) {
            Start-Sleep -Milliseconds 500
            try {
                $health = Invoke-RestMethod -Uri "$Url/api/health/detail" -TimeoutSec 2
                if ($health.status -eq "healthy") { $healthy = $true; break }
            } catch {}
            if ($proc.HasExited) { break }
        }
        if (-not $healthy) { throw "Canopy smoke launch did not become healthy at $Url" }
        Write-Host "LAUNCHER_SMOKE=PASS"
        exit 0
    } finally {
        if ($proc -and -not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
    }
}

if (-not $NoBrowser) { Start-Process "$Url/control-room" }
& $VenvPython -m uvicorn server:app --host $BindAddress --port $Port
exit $LASTEXITCODE
