param(
    [switch]$Baseline,
    [switch]$RequireClean,
    [switch]$SkipBrowserInstall
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $Root
[System.IO.Directory]::SetCurrentDirectory($Root)

if ((Get-Location).Path -match "\\Windows\\System32$") {
    throw "Autonomous build safety failure: working directory resolved to System32."
}

$VenvPython = Join-Path $Root ".venv\\Scripts\\python.exe"
if (-not (Test-Path $VenvPython)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv .venv
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv .venv
    } else {
        throw "Python 3 was not found."
    }
}

& $VenvPython -m pip install --disable-pip-version-check --upgrade pip
& $VenvPython -m pip install --disable-pip-version-check -r requirements-release.txt

if (-not $SkipBrowserInstall) {
    & $VenvPython -m playwright install chromium
}

$BuildArgs = @("scripts\\hardened_autonomous_build.py")
if ($Baseline) { $BuildArgs += "--baseline" }
if ($RequireClean) { $BuildArgs += "--require-clean" }

& $VenvPython @BuildArgs
exit $LASTEXITCODE
