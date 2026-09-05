# PISS v0.1 Baseline Integration

PISS (Pressure-Informed Symbolic System) has been added to Deterministic Jungle Canopy as a sibling orchestration/evidence subsystem.

## Verified standalone baseline

Before repository integration, the Windows prototype demonstrated:

- 4/4 PISS unit tests passing
- `cards/piss_on_the_world.piss` parsing successfully
- WADRRB instruction order visible in the verifier
- the executable `.piss` prototype producing PASS/FAIL receipts

## Core grammar

```text
WANT -> ACT -> DO -> RECKON -> REPAIR -> BURY
```

## Repository integration decisions

- Canopy remains the deterministic render/state engine.
- PISS does not replace Canopy.
- PISS source lives in the `piss/` Python package.
- Example programs live in `cards/`.
- PISS runtime receipts are namespaced under `receipts/piss/`.
- PISS tests are isolated in `tests/test_piss.py`.
- Existing Canopy APIs, rendering, session semantics and receipt formats are not changed by this baseline commit.

## Important limitations to hand to the next builder

v0.1 is intentionally primitive:

- `ACT` has only a few built-in observations.
- unknown ACT targets currently return an informational string instead of failing closed.
- `DO` uses the host shell directly.
- `REPAIR` records intent but performs no mutation.
- no variables
- no conditional repair block
- no adapter interface
- no `piss show <run-id>` command

Those are v0.2 work, not hidden capabilities.
