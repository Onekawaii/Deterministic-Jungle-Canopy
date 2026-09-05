# OpenHands Continuation Order — PISS v0.2

You are continuing an existing working repository: **Deterministic-Jungle-Canopy**.

PISS is a sibling subsystem. Do not rewrite or replace Canopy.

## First actions

1. Read the repository.
2. Run the existing Canopy test suite.
3. Run `VERIFY_PISS.bat` or the equivalent Python PISS tests.
4. Establish the baseline before editing.

## Architectural law

Canopy = deterministic state/render engine.

PISS = orchestration + verification language.

Integration happens through explicit adapters/contracts, not hardcoded renderer dependencies.

PISS describes:

```text
INTENT -> OBSERVATION -> ACTION -> VERIFICATION -> REPAIR -> RECEIPT
```

Adapters perform reality.

## v0.2 milestone

Build the smallest correct next version.

Required additions:

- first-class read-only `WITNESS`
- small variable/reference support
- bounded `IF FAIL` repair flow
- explicit adapter contract
- initial adapters: shell, filesystem, python, git
- fail-closed unknown capability behavior
- CLI:
  - `piss check <card>`
  - `piss run <card>`
  - `piss history`
  - `piss show <run-id>`
- richer versioned receipts with run IDs and evidence
- a real `cards/project_check.piss`

## Do not add

- classes/objects to the language
- inheritance
- arbitrary embedded Python
- package management
- general-purpose loops
- network services
- direct renderer coupling
- fake PASS states

## Receipt discipline

A receipt must preserve enough evidence to reconstruct what happened.

No receipt, no banana.

## Acceptance gate

From a clean checkout:

```text
piss check cards/piss_on_the_world.piss
PASS

piss run cards/piss_on_the_world.piss
PASS + receipt

piss show <run-id>
shows real execution evidence

piss run cards/project_check.piss
performs real local project inspection + receipt
```

Existing Canopy tests and all PISS tests must pass.

Report files changed, grammar, adapters, receipt contract, test results, acceptance results, known limits, Windows commands, and final commit SHA.

Do not expand scope after the gate passes.
