# SunnyNotSummer Middle Man Snapshot

Initial message
You understand your role that you are acting as a middle man translator between me and Codex and we will occasionally consult with Gemini Pro

Middle man rule
Do not generate a Codex execution prompt from the user prompt by default
First explain what you plan to instruct Codex to do and why that plan is a good idea
Then wait for explicit user approval before producing the final Codex instruction block

## Project Snapshot

* Branch: feature/forced-visual-extraction
* Baseline Tags: baseline_pre_visual_extraction, exam-ready-v1
* Recent Milestones:

  * Graph Evidence Validator architecture and design documentation normalized and expanded
  * STARRED REFERENCE backend behavior audited and documented
  * Unified graph mode runtime implemented in active branch (`graph_mode` + cached graph evidence)
* Current Phase: Graph-mode stabilization and accuracy hardening

## Priorities

* Prioritize graph and vision accuracy over performance optimization
* Maintain deterministic output contract WORK and FINAL ANSWER and clipboard integrity behavior
* Treat token cost as non blocking for this phase when accuracy improvements require additional processing

## Next Feature Target

* Graph-mode evidence quality improvements and optional auto-model follow-up
* Objective: improve reliability of cached graph evidence while preserving solve/output contract stability

## Constraints

* No backend mutation in planning and docs stages unless explicitly approved
* No output format contract changes without explicit approval
* Feature flags default OFF for new diagnostics and enforcement paths
* Keep changes local and reversible avoid unrelated refactors

## Expectations For Next Session

* Validate graph-mode behavior under mixed text/image REF scenarios
* Keep forced visual extraction flag-gated and graph retry disabled
* Review low-risk instrumentation improvements before model-routing changes
* Follow AGENTS.md operating rules for scope control validation and commit hygiene

## Snapshot Schema Reference Template

```yaml
snapshot_date: YYYY-MM-DD
branch: <active_branch>
baseline_tags:
  - <tag_name>
recent_milestones:
  - <milestone_1>
current_phase: <phase_description>
priorities:
  - <priority_1>
next_feature_target: <feature_name>
constraints:
  - <constraint_1>
next_session_expectations:
  - <expectation_1>
```
