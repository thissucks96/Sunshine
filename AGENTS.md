# SunnyNotSummer - Agent Operating Guide

Use this file as the default instruction set for coding agents working in this repo.

---

## 1) Default Working Style

* Keep changes minimal and local unless broader change is explicitly requested.
* Avoid architecture rewrites unless explicitly approved.
* Do not add or remove dependencies unless explicitly approved.
* Preserve existing behavior unless fixing a clear bug.
* Prefer low-risk fixes before structural changes.
* Assume the app is actively used; avoid breaking workflow.
* Avoid formatting-only edits unless requested.

When the user explicitly asks for exploratory design or architectural thinking, broader creative proposals are allowed, but do not modify code unless instructed.

---

## 2) Execution Rules

* Implement requested changes directly unless the task is marked analysis-only.
* Keep diffs tightly scoped to relevant logic.
* Run quick validation after edits:

  * `python -m py_compile main.py llm_pipeline.py config.py utils.py`
* If tests exist for touched code, run them.
* Report blockers immediately.
* If instructions conflict with this document, pause and ask for clarification.
* Do not autonomously refactor unrelated systems.

---

## 3) Commit Policy

* Create a commit after each completed task unless told otherwise.
* Create a commit after every code change set (not just at session end) unless told otherwise.
* Commit format:

  * `<type>: <intent> [scope: <files_or_area>]`
* Commit message must include:

  * Intent: why the change was made
  * Scope: what code area/files were changed
* Recommended types:

  * `fix`, `feat`, `refactor`, `docs`, `test`, `chore`
* Do not push unless explicitly requested.

---

## 4) Safety Rules

* Never run destructive git commands without explicit approval.
* Never revert unrelated user changes.
* If unexpected file changes appear during work, stop and ask how to proceed.
* Do not introduce breaking output-format changes without approval.
* Treat this file as a stable operational contract, not a running log.

---

## 5) Autonomy Model

Default Mode: Controlled Engineering

* Minimal scope
* No architecture rewrites
* No dependency changes
* Deterministic output preserved

Exploration Mode (only when explicitly requested)

* Broader architectural suggestions allowed
* Structural redesign proposals allowed
* Performance or reliability improvements may be proposed
* Code modifications still require explicit approval

If unclear which mode applies, ask before proceeding.

---

## 6) New Task Kickoff Template

When starting a structured task, expect a kickoff block:

```
Goal:
Scope:
Files likely involved:
Constraints:
Acceptance criteria:
Out of scope:
Validation plan:
Commit policy:
```

Follow it strictly.

---

## 7) Current Project Priorities

* Reliability over raw speed.
* Keep solve output deterministic and concise.
* Protect clipboard result integrity.
* Maintain strong graph/reference handling.
* Prevent model drift in output formatting.
* Minimize silent failure modes.

---

## 8) Documentation & Reviews

* Do not place time-specific code reviews inside `AGENTS.md`.
* Store comprehensive reviews in `/docs` using a date-based filename:

  * `docs/ARCHITECTURE_REVIEW_<YYYY_MM>.md`
* Extract durable design decisions into:

  * `docs/ARCHITECTURE.md`
  * or `docs/ROADMAP.md`
* Treat review documents as audits, not contracts.
* Do not create a new `ARCHITECTURE_REVIEW_<YYYY_MM>.md` file unless the user explicitly requests updating both `docs/ARCHITECTURE.md` and `docs/ROADMAP.md`.

---

## 9) Documentation Awareness (Pre-Task Requirement)

At the start of each session and before beginning any new task, review the following files if they exist:

* `docs/ARCHITECTURE.md`
* `docs/ROADMAP.md`
* Most recent `docs/ARCHITECTURE_REVIEW_<YYYY_MM>.md`

Use these documents to:

* Align changes with architecture direction.
* Avoid reintroducing known risks.
* Follow established roadmap priorities.

If documentation conflicts with user instructions, pause and ask for clarification.

Do not summarize documentation unless requested. Use it as internal guidance only.

---

This version gives you:

* Safe default behavior
* Controlled exploration when desired
* No silent architecture drift
* Clean documentation separation
* Long-term scalability
