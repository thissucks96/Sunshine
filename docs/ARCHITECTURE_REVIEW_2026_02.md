# SunnyNotSummer Architecture Review - 2026_02

## Scope
Baseline audit of current runtime behavior, reliability hardening, and known remaining risks.

## What Is Working
- Tray-driven solve and REF workflows are stable.
- Config persistence and runtime cache behavior are consistent.
- Tray/cycle model switching includes probe validation before activation status.
- REF classifier EMPTY path now has fallback handling.
- Output normalization is more deterministic than earlier iterations.
- `AUTO` model menu item is present as a placeholder for future routing.

## Accuracy Notes
- Startup and "Refresh Model List" model announcements are currently not probe-gated.

## Key Risks Still Open
- Close-path consistency: ensure all exit paths enforce the same REF clear behavior if required by policy.
- Aggressive post-processing heuristics can still over-correct edge outputs.
- Graph accuracy variance remains model-dependent for difficult visual reads.

## Recommended Next Steps
1. Ship optional `AUTO` model routing behind a disabled-by-default flag.
2. Build a compact regression matrix for graph/domain/range and REF paths.
3. Keep reliability-focused changes small and reversible.

## Notes
- This file is an audit snapshot, not a policy document.
- Durable decisions should be promoted into `docs/ARCHITECTURE.md` and `docs/ROADMAP.md`.
