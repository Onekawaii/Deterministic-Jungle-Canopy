# Hardened Autonomous Build — Jungle + PISS

This is the authoritative continuation order for an autonomous builder.

Target:
- preserve and harden Deterministic Jungle Canopy
- harden PISS from v0.1 into a safe v0.2 execution language
- keep the existing Sovereign release gate green
- finish with one composite green receipt

The builder may inspect, edit, test, repair, commit, and iterate without asking for routine approval. It must not weaken tests, hide failures, widen network exposure, rewrite git history, force-push, delete unrelated data, or expand scope after the gate is green.

No receipt, no banana.

## Architecture law

Canopy = deterministic state/render/session system.

PISS = declarative orchestration, verification, repair, and receipts.

PISS may invoke Canopy only through an explicit adapter/capability boundary.

Do not merge the two systems.

## Autonomous working law

Before editing:
1. read the repository
2. record the starting commit
3. run the current Sovereign gate
4. run the current PISS tests and cards
5. run RUN_HARDENED_AUTONOMOUS_BUILD.ps1 -Baseline

During work:
- use main unless the platform forces a temporary branch
- make coherent commits
- run targeted tests after each repair
- run the full composite gate before declaring completion
- never convert a real failure into a skip
- never hardcode expected hashes or outputs only to satisfy a test
- stop with an honest blocker receipt if credentials, destructive external action, or an irreducible product decision is required

## Part A — harden Canopy

The current Sovereign distribution gate is an invariant. Keep it green.

### Network and browser boundary

All default launch surfaces must bind to loopback:
- 127.0.0.1
- localhost
- ::1

Remote binding must require explicit opt-in.

CORS must not use wildcard origins with credentials. The local Control Room should use an explicit loopback-origin policy. Add regression tests for this.

### Imports and archives

All imported payloads and archives must validate before mutation.

Reject:
- unsafe paths
- path traversal
- malformed session state
- unsupported schemas
- invalid events
- oversized payloads
- excessive nesting
- excessive collection/event counts

A failed import must not mutate active state.

### Filesystem and release

Generated paths must remain under intended output roots.

Reject ../, ..\, and absolute-path escapes where relative paths are required.

Release artifacts must exclude:
- .venv
- caches
- local databases
- local sessions
- .env files
- secrets and credentials

### API semantics

4xx/5xx are failures.

Unknown events fail before mutation.

Do not return a successful HTTP status for a failed operation unless an existing compatibility contract proves it is required.

### Determinism

Prove:
- same canonical manifest + seed + frame = identical pixels
- same input across fresh processes = identical output
- export/import/replay = identical output
- interrupted render = no partial mutation
- invalid event = no mutation
- corrupted session = fail closed
- two release builds from the same commit and SOURCE_DATE_EPOCH produce byte-identical archive SHA-256

Do not silently weaken exact comparisons.

### Persistence and recovery

Test:
- SessionStore opens/closes cleanly on Windows
- DB can be removed after close
- malformed persistent state gives a useful diagnostic
- concurrency preserves event order
- export/import loses no events
- frame/hash metadata stays internally consistent
- temporary writes are atomic where practical

### Resource bounds

Review and bound:
- width and height
- frame count
- sequence export count
- import size
- nesting depth
- event count
- request body size where practical
- verification subprocess timeouts

## Part B — harden PISS

PISS remains WADRRB:

WANT -> ACT -> DO -> RECKON -> REPAIR -> BURY

ACT remains the primary observation verb.

Do not turn PISS into Python. Do not add classes, inheritance, arbitrary loops, eval, embedded Python, package management, or a general expression engine.

### Remove arbitrary shell execution

Current v0.1 host-shell execution is not acceptable for the hardened build.

Hard law:

A card names a registered capability. It does not provide an arbitrary shell program.

Forbidden:
- shell=True
- arbitrary executable names from a card
- eval
- exec
- arbitrary Python expressions
- shell metacharacter interpretation
- unbounded command substitution

Adapters must invoke fixed argv lists or rigorously validated structured arguments.

### Adapter registry

Create an explicit registry.

Initial capabilities:

system:
- cwd
- platform
- safe runtime metadata

filesystem, sandboxed to repo root:
- exists
- sha256
- stat
- bounded text read if needed

git, read-only:
- repo root
- branch
- HEAD
- clean/dirty
- status summary

python:
- version
- approved repository test entrypoint via fixed argv

core:
- safe echo/message action for piss_on_the_world

canopy:
- optional approved Sovereign verification action through a fixed adapter

Each adapter declares:
- name
- capabilities
- read-only vs mutating
- structured inputs
- structured outputs
- timeout
- output cap
- failure mode
- permissions

Unknown adapter/capability fails closed before execution.

### Validation pipeline

Separate:

parse -> validate -> plan -> execute -> verify -> repair -> receipt

piss check must never mutate state.

Reject:
- unknown verbs
- unknown adapters
- unknown capabilities
- invalid ordering
- missing WANT
- undefined references
- malformed RECKON
- oversized cards
- path escapes
- repair loops beyond the configured maximum

Suggested stable exits:
- 0 PASS
- 1 executed but WANT/RECKON failed
- 2 INVALID
- 3 runtime/adapter ERROR

### Variables

Add only minimal named references for ACT observations and DO results.

No expression evaluator.

Undefined references fail closed.

Variable substitution must not create a shell/code-injection path.

### Repair

REPAIR becomes real but bounded:
- entered only after failed RECKON
- capability must be registered and permitted
- default max attempts = 2
- no recursive/unbounded loop
- before/after evidence recorded
- repair followed by RECKON
- exhausted attempts = FAIL

Repair cannot silently convert failure into PASS.

### Receipt v0.2

Every executed run writes a versioned receipt containing:
- schema_version
- run_id
- card path + SHA-256
- piss_version
- grammar
- WANT
- PASS/FAIL/INVALID/ERROR
- start/end timestamps
- environment
- ordered steps
- repairs
- evidence
- reproducibility hash excluding volatile fields
- receipt SHA-256

Each step preserves:
- sequence
- verb
- adapter
- capability
- normalized arguments
- status
- duration
- bounded stdout/stderr where applicable
- return code
- evidence hashes
- error class/message

Redact likely credentials and secret-like values.

Never store raw tokens, passwords, API keys, Authorization headers, or credentials.

### CLI v0.2

Required:
- piss check CARD
- piss run CARD
- piss history
- piss show RUN_ID

### Hostile-input tests

Prove rejection of:
- shell metacharacter injection
- arbitrary executable request
- ../ filesystem escape
- absolute path escape
- unknown adapter
- unknown capability
- undefined variable
- malformed RECKON
- unbounded repair
- timeout
- oversized output
- secret leakage into receipts
- invalid ordering
- no WANT

Retain positive coverage for:
- piss_on_the_world
- project_check
- intentional failure with a real failure receipt
- history
- show

## Part C — combined acceptance

Final command:

~~~powershell
cd "<repo>\Deterministic-Jungle-Canopy"
.\RUN_HARDENED_AUTONOMOUS_BUILD.ps1 -RequireClean
~~~

The hardened profile is intentionally red on the PISS v0.1 baseline. Baseline mode is evidence only, not acceptance.

Completion requires:
1. composite command returns 0
2. Sovereign Canopy release gate is green
3. PISS is 0.2.x or later
4. no card-driven arbitrary shell execution remains
5. no wildcard-with-credentials CORS remains
6. all tests pass
7. determinism passes across process and export/import boundaries
8. recovery/failure-injection passes
9. real Chromium Control Room smoke passes
10. PISS hostile-input and receipt tests pass
11. release archive is clean and reproducible
12. composite receipt exists
13. final working tree is clean
14. final commit SHA is reported

## Final report

Report:
1. starting SHA
2. final SHA
3. files changed
4. Canopy security changes
5. Canopy determinism/recovery changes
6. final PISS grammar
7. adapter registry
8. PISS receipt contract
9. exact test totals
10. determinism totals
11. recovery totals
12. browser totals
13. PISS hardening totals
14. release archive + SHA-256
15. composite receipt path
16. known limitations
17. exact Windows run commands

If any item is unproven, leave the build FAILED.

Once the composite gate is green: STOP. Do not start another feature phase.
