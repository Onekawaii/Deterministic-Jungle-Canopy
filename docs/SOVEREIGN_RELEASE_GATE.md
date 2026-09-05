# Sovereign Canopy Verified Distribution Gate

This document is the executable release contract for GitHub issue #1.

## Windows launch

From a fresh checkout:

```powershell
cd "<path>\Deterministic-Jungle-Canopy"
.\RUN_CANOPY_WINDOWS.ps1
```

Or double-click `RUN_CANOPY_WINDOWS.cmd`.

The launcher always changes into its own directory before creating `.venv` or starting the server. The default bind is `127.0.0.1`. Remote binding is refused unless `-AllowRemote` is explicit.

## One-command release verification

```powershell
cd "<path>\Deterministic-Jungle-Canopy"
.\VERIFY_SOVEREIGN_RELEASE.ps1
```

The gate runs:

- full pytest unit/API/session suite
- deterministic rendering trial
- real load plus failure-injection recovery/integrity trial
- reproducible release build and SHA-256 manifest
- extracted-release API smoke
- Chromium smoke through the real Control Room canvas

Evidence is written to `receipts/release_gate/`. Release artifacts are written to `dist/`.

## Hard rules

- HTTP 4xx/5xx are failures, not successful endpoint checks.
- Invalid events must not mutate manifest or event count.
- Injected render failure must leave session state unchanged.
- Corrupt import must fail closed.
- Browser smoke must prove actual rendered image bytes reach the real canvas.
- Same canonical inputs must reproduce the same pixels.
- Release packaging is allowlist-based and audits out `.venv`, caches, secrets, local databases, and local sessions.

## CI

`.github/workflows/sovereign-release-gate.yml` runs the same gate on Windows and uploads the receipts plus distribution archive as workflow artifacts.
