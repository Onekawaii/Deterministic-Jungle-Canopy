# Windows Runbook — PISS v0.1 inside Deterministic Jungle Canopy

## Verify

```powershell
cd "<path-to>\Deterministic-Jungle-Canopy"
.\VERIFY_PISS.bat
```

## Ceremonial execution test

Double-click:

```text
PISS_ON_THE_WORLD.bat
```

Expected core output:

```text
PISS ON THE WORLD
STATUS: PASS
RECEIPT: receipts\piss\...json
```

## Manual CLI

```powershell
cd "<path-to>\Deterministic-Jungle-Canopy"
py -3 -m piss check cards\piss_on_the_world.piss
py -3 -m piss run cards\piss_on_the_world.piss
py -3 -m piss history
```

## Project check

```powershell
.\RUN_PROJECT_CHECK.bat
```

## Intentional failure

```powershell
py -3 -m piss run cards\intentional_failure.piss
```

It should report FAIL and still create a receipt.

## v0.1 boundaries

No automatic file mutation, no LLM, no general-purpose loops, no privilege escalation, and no direct Canopy renderer coupling.
