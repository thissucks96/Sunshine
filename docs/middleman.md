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
  * Baseline snapshot tag created before forced visual extraction work
* Current Phase: Graph accuracy improvement and forced visual extraction planning pre implementation

## Priorities

* Prioritize graph and vision accuracy over performance optimization
* Maintain deterministic output contract WORK and FINAL ANSWER and clipboard integrity behavior
* Treat token cost as non blocking for this phase when accuracy improvements require additional processing

## Next Feature Target

* Forced visual extraction for graph solves
* Objective: increase reliability of graph perception evidence before final interval domain range claims

## Constraints

* No backend mutation in planning and docs stages unless explicitly approved
* No output format contract changes without explicit approval
* Feature flags default OFF for new diagnostics and enforcement paths
* Keep changes local and reversible avoid unrelated refactors

## Expectations For Next Session

* Prepare a precise Codex execution prompt for forced visual extraction implementation
* Keep implementation behind flags and preserve warning only safety where applicable
* Review proposed diffs for behavioral regression risk before merge
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
