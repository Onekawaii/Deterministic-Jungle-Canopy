param([switch]$SkipBrowserInstall)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $Root
[System.IO.Directory]::SetCurrentDirectory($Root)

if ((Get-Location).Path -match "\\Windows\\System32$") { throw "Verification safety failure: working directory resolved to System32." }

$VenvPython = Join-Path $Root ".venv\\Scripts\\python.exe"
if (-not (Test-Path $VenvPython)) {
    if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 -m venv .venv }
    elseif (Get-Command python -ErrorAction SilentlyContinue) { & python -m venv .venv }
    else { throw "Python 3 was not found." }
}

& $VenvPython -m pip install --disable-pip-version-check --upgrade pip
& $VenvPython -m pip install --disable-pip-version-check -r requirements-release.txt

if (-not $SkipBrowserInstall) { & $VenvPython -m playwright install chromium }

& $VenvPython scripts\sovereign_release_gate.py
exit $LASTEXITCODE
