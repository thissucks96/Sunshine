# SunnyNotSummer - Agent Operating Guide

Use this file as the default instruction set for coding agents working in this repo.

---

## 1) Default Working Style

* Keep changes minimal and local.
* Avoid architecture rewrites unless explicitly requested.
* No dependency changes unless explicitly requested.
* Preserve existing behavior unless fixing a clear bug.
* Prefer low-risk fixes first.
* Assume the app is actively used; avoid breaking user workflow.
* Avoid formatting-only edits unless explicitly requested.

---

## 2) Execution Rules

* Implement requested changes directly; do not stop at planning unless asked.
* Keep diffs tightly scoped to touched logic only.
* Run quick validation after edits:

  * `python -m py_compile main.py llm_pipeline.py config.py utils.py`
* If tests exist for touched code, run them.
* Report blockers immediately.
* If instructions conflict with this document, pause and ask for clarification.

---

## 3) Commit Policy

* Create a commit after each completed task unless user says not to.
* Commit format:

  * `<type>: <short summary>`
* Recommended types:

  * `fix`, `feat`, `refactor`, `docs`, `test`, `chore`
* Do not push unless explicitly requested.

---

## 4) Safety Rules

* Never run destructive git commands without explicit user approval.
* Never revert unrelated user changes.
* If unexpected file changes appear during work, stop and ask how to proceed.
* Treat this file as a stable operational contract, not a running log.

---

## 5) New Task Kickoff Template

When starting a new task, expect a kickoff block structured like:

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

## 6) Current Project Priorities

* Reliability over raw speed.
* Keep solve output deterministic and concise.
* Protect clipboard result integrity.
* Maintain strong graph/reference handling.
* Prevent model drift in output formatting.
* Minimize silent failure modes.

---

## 7) Documentation & Reviews

* Do not place time-specific code reviews inside `AGENTS.md`.
* Store comprehensive reviews in `/docs` using a date-based filename:

  * `docs/ARCHITECTURE_REVIEW_<YYYY_MM>.md`
* If durable design decisions emerge from a review, extract only those into:

  * `docs/ARCHITECTURE.md`
  * or `docs/ROADMAP.md`
* Keep this file limited to persistent operational rules.
* Treat review documents as audits, not contracts.

---

## 8) Documentation Awareness (Pre-Task Requirement)

Before beginning any new task, review the following files if they exist:

* `docs/ARCHITECTURE.md`
* `docs/ROADMAP.md`
* Most recent `docs/ARCHITECTURE_REVIEW_<YYYY_MM>.md`

Use these documents to:

* Align changes with existing architecture decisions.
* Avoid reintroducing previously identified risks.
* Follow established roadmap direction.

If documentation conflicts with user instructions, pause and ask for clarification.

Do not summarize documentation unless requested. Use it as internal guidance only.

---

This structure gives you:

* Stable behavioral guardrails
* Clean separation of audit vs policy
* Controlled commits
* Documentation continuity
* Reduced architectural drift
