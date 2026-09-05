# PISS Language Spec v0.1

PISS is a small orchestration/testing DSL. It is not a Python replacement.

One instruction per line: `OP ARGUMENTS`. Comments start with `#`.

Valid v0.1 operations:

- `WANT`
- `ACT`
- `DO`
- `RECKON`
- `REPAIR`
- `BURY`

A program must start with `WANT`.

## WADRRB

```text
WANT -> ACT -> DO -> RECKON -> REPAIR -> BURY
```

## ACT targets

```text
ACT cwd
ACT python
ACT platform
ACT env NAME
```

## RECKON predicates

```text
RECKON last_do_passed
RECKON last_do_failed
RECKON file_exists PATH
RECKON contains TEXT
```

## REPAIR

In v0.1, REPAIR records the requested repair but does not mutate files automatically.

## Exit contract

- PASS: exit 0
- FAIL: exit 1
- parser/runtime error: exit 2

## Design law

**PISS describes intent and verification; host adapters perform reality.**

In Deterministic Jungle Canopy, PISS is a sibling subsystem. It does not replace or directly couple itself to the renderer.
