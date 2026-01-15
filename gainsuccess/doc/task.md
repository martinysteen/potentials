# Trial 10: Comprehensive Indicator Decile Analysis

- [x] Analyze Trial 9 script and requirements for Trial 10
- [x] Update `PROMPTS.md` with special coding rules for `uptrend` indicator
- [x] Implement Trial 10 script: `analyze_gain_success_trial10.py`
    - [x] Load price data from `PotDat.csv`
    - [x] Calculate forward max gains (21-day window)
    - [x] Implement loop to iterate through all 20 `longi_*.csv` indicators
    - [x] Implement categorical-to-numeric mapping for `uptrend`
    - [x] Perform decile analysis for each indicator (last 132 days)
    - [x] Collect D1 and D10 success rates
    - [x] Identify top 3 indicators by peak success rate
- [x] Execute analysis on `gandalf`
- [x] Verify output files in `output/`
- [x] Create walkthrough report summarizing the findings

# Trial 11: Cross-Indicator Decile Analysis

- [x] Create implementation plan for cross-decile analysis
- [x] Implement Trial 11 script: `analyze_cross_deciles_trial11.py`
    - [x] Gather (Ticker, Day) pairs for D1 across all indicators
    - [x] Calculate hurdle values (upperLimit, lowerLimit)
    - [x] Compute cross-occurrence counts (simultaneous D1 membership)
- [x] Execute analysis and verify output `trial11_cross_deciles.csv`
- [x] Update walkthrough with Trial 11 results

# Trial 12: Combined Indicator Success Rate Lift

- [x] Create implementation plan for indicator combination lift
- [x] Implement Trial 12 script: `analyze_combined_lift_trial12.py`
    - [x] Establish `per6m-D1` as the anchor population
    - [x] Calculate success rates for overlaps with all other indicators (D1 and D10)
    - [x] Measure "lift" compared to base `per6m-D1` rate
- [x] Execute analysis and identify optimal combinations
- [x] Finalize walkthrough with Trial 12 findings

# Trial 13: Top Combination Refinements (Top 20% & 40-Day Window)

- [x] Create implementation plan for Trial 13 modifications
- [x] Implement `analyze_trial13.py`
    - [x] Calculate Top 20% (D1+D2) success rates (Mod 1)
    - [x] Calculate 41-day window success rates (Mod 2)
    - [x] Calculate mixed threshold success rates (per6m 10%, medians 20%) (Mod 3)
- [x] Generate result tables and compare with Trial 12
- [x] Update documentation/walkthrough

# Trial 14: Super-Sample Member Listing

- [x] Identify super-sample logic (per6m Top 10%, median_40d Top 20%)
- [x] Construct detailed member table (ticker, start_daynum, gain)
- [x] Incorporate member listing into walkthrough
