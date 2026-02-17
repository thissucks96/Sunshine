# SunnyNotSummer Known Limitations

## Graph Extraction

- Dark/Low-Contrast images are supported as "Best Effort" only.
- Coordinate drift of ±0.2 is expected in these cases.
- This is a known limitation of the stress test configuration.

## Scope Notes

- Hard-tier dark-mode datasets are treated as resilience/stress validation, not primary production acceptance gates.
- Primary production quality targets are anchored to standard Easy/Medium graph inputs and parser-contract stability.
