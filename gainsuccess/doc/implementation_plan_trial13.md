# Implementation Plan - Trial 13: Top Combination Refinements

This trial re-evaluates the most attractive indicator combinations identified in Trial 12 (`per6m` + `median_40d/50d/100d`) with two specific modifications to observe the impact on count and success rate.

## Modification 1: Top 20% Thresholds
- **Hurdle**: Switch from Top 10% (D1) to Top 20% (D1 + D2).
- **Window**: 21-day max gain window (same as Trial 12).
- **Goal**: Increase the sample size (Count) while monitoring the decay in Success Rate.

## Modification 2: 40-Day Success Window
- **Hurdle**: Maintain Top 10% (D1).
- **Window**: Increase to 41-day max gain window (detecting >10% gain within 40 trading days).
- **Goal**: Observe how many more "slow burners" reach the 10% target with more time.

## Proposed Changes

### Script Development: `analyze_trial13.py`
- Inherit core logic from `analyze_combined_lift_trial12.py`.
- Implement a parameter to toggle between D1 (Top 10%) and D1+D2 (Top 20%).
- Implement a parameter to toggle between 21-day and 41-day gain windows.
- Perform the analysis specifically for the top 3 secondary indicators: `median_40d`, `median_50d`, and `median_100d`.

### Execution & Reporting
- Run analysis for both modifications.
- Generate comparison tables matching the format of Trial 12.
- Update `walkthrough.md` with findings.
