# SunnyNotSummer Known Limitations

## Graph Extraction

- Dark/Low-Contrast images are supported as "Best Effort" only.
- Coordinate drift of ±0.2 is expected in these cases.
- This is a known limitation of the stress test configuration.
- System is optimized for standard light-mode graphs.
- Dark mode support is currently experimental.
- Latest system-acceptance stress result for dark mode:
  - `tests/GRAPH_CHECKER/system_acceptance_dark_20260216.txt`
  - pass rate: `2/5` (`40.00%`) under strict key-point criteria.
- Operational guidance:
  - Dark-mode extraction should not be used as a production acceptance gate.
  - Primary release quality remains anchored to light-mode validation.

## Scope Notes

- Hard-tier dark-mode datasets are treated as resilience/stress validation, not primary production acceptance gates.
- Primary production quality targets are anchored to standard Easy/Medium graph inputs and parser-contract stability.
