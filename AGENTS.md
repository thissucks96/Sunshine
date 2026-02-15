# SunnyNotSummer - Agent Operating Guide

Use this file as the default instruction set for coding agents working in this repo.

## 1) Default Working Style
- Keep changes minimal and local.
- Avoid architecture rewrites unless explicitly requested.
- No dependency changes unless explicitly requested.
- Preserve existing behavior unless fixing a clear bug.
- Prefer low-risk fixes first.

## 2) Execution Rules
- Implement requested changes directly; do not stop at planning unless asked.
- Run quick validation after edits:
  - `python -m py_compile main.py llm_pipeline.py config.py utils.py`
- If tests exist for touched code, run them.
- Report any blockers immediately.

## 3) Commit Policy
- Create a commit after each completed task unless user says not to.
- Commit format:
  - `<type>: <short summary>`
- Recommended types:
  - `fix`, `feat`, `refactor`, `docs`, `test`, `chore`
- Do not push unless explicitly requested.

## 4) Safety Rules
- Never run destructive git commands without explicit user approval.
- Never revert unrelated user changes.
- If unexpected file changes appear during work, stop and ask user how to proceed.

## 5) New Chat Kickoff Template
Use this at the top of a new task:

```text
Goal:
Scope:
Files likely involved:
Constraints:
Acceptance criteria:
Out of scope:
Validation plan:
Commit policy:
```

## 6) Current Project Priorities
- Reliability over raw speed.
- Keep solve output deterministic and concise.
- Protect clipboard result integrity.
- Maintain strong graph/reference handling.
