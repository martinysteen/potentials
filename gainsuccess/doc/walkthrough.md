# Trial 10: Comprehensive Indicator Decile Analysis

This trial extends the decile-based "gain success" analysis to all 20 stock indicators. We measured the probability of achieving a >10% max forward gain within 21 days, focusing on the most recent 132 data points for each ticker/indicator pair.

## Methodology

- **Gain Calculation**: `(max(prices in next 21 days) - current price) / current price`.
- **Lookback Window**: 132 days (recent cases).
- **Decile Analysis**: For each indicator, data points were ranked and split into 10 deciles (D1 = Top, D10 = Bottom).
- **Success Criteria**: Gain > 10%.
- **Special Handling**: `uptrend` indicator mapped categorical values (`VeryGood`=5, `Good`=4, `Maybe`=2, others=0).

## Comparison of Indicators (D1 vs D10)

The following table summarizes the success rates for the top (D1) and bottom (D10) deciles across all indicators. D1 represents the top 10% highest indicator values.

| Indicator | D1 Success Rate | D10 Success Rate |
| :--- | :--- | :--- |
| **per6m** | **46.71%** | 28.99% |
| **per3m** | **46.52%** | 25.87% |
| **per1y** | **44.92%** | 33.38% |
| **median_50d** | **43.39%** | 24.77% |
| **median_100d** | **42.85%** | 27.17% |
| **median_40d** | **42.62%** | 24.26% |
| **median_30d** | **41.71%** | 24.03% |
| **median_20d** | **41.23%** | 24.48% |
| **median_10d** | **40.31%** | 24.55% |
| **rank** | **38.45%** | 24.96% |
| **per1w** | 37.65% | 36.24% |
| **per1d** | 36.90% | 34.71% |
| **per1m** | 33.79% | 40.38% |
| **macd_histogram** | 25.46% | 22.05% |
| **rsi** | 23.77% | 24.20% |
| **macd_line** | 23.20% | 22.98% |
| **uptrend** | 24.01% | 23.52% |
| **stepup40** | 23.85% | 22.54% |
| **macd_signal** | 21.56% | 23.03% |
| **stepup100** | 21.13% | 24.33% |

> [!NOTE]
> For almost all indicators, the **Top Decile (D1)** shows higher success rates, which is intuitive.

## Top 3 Indicators (Peak Success Rates)

The three indicators with the highest success rates in their top decile were:

1.  **per6m**: Peak Success Rate of **46.71%** (D1)
2.  **per3m**: Peak Success Rate of **46.52%** (D1)
3.  **per1y**: Peak Success Rate of **44.92%** (D1)

## Detailed Analysis: per6m

The `per6m` indicator (6-month percent change) showed the highest peak success rate in its top decile.

### Success Rate Table (per6m)

| Decile | Count | Avg Indicator Value | Success Count | Success Rate |
| :--- | :--- | :--- | :--- | :--- |
| **D1 (Top)** | 14,332 | 111.76 | 6,694 | **46.71%** |
| **D2** | 14,332 | 42.01 | 4,426 | 30.88% |
| **D3** | 14,332 | 27.27 | 3,089 | 21.55% |
| **D4** | 14,332 | 18.58 | 2,650 | 18.49% |
| **D5** | 14,332 | 12.10 | 2,314 | 16.15% |
| **D6** | 14,331 | 6.60 | 2,211 | 15.43% |
| **D7** | 14,332 | 1.59 | 1,958 | 13.66% |
| **D8** | 14,332 | -3.68 | 2,257 | 15.75% |
| **D9** | 14,332 | -10.73 | 2,648 | 18.48% |
| **D10 (Bottom)** | 14,332 | -26.87 | 4,155 | 28.99% |

### Histogram

![per6m Success Rate by Decile](C:\Users\sm\.gemini\antigravity\brain\68c32ce8-903f-48ae-bfaf-8558b9254390\per6m_histogram.png)

# Trial 11: Cross-Indicator Decile overlap

This trial analyzed how often different indicators simultaneously rank the same stock-day in their top decile (D1). We also extracted the specific hurdle values required to reach D1 for each indicator.

## Methodology

- **Simultaneous Belonging**: Counted (Ticker, Day) pairs that were in D1 for both Row-Indicator and Column-Indicator.
- **Hurdles**:
  - `lowerLimit`: The threshold (90th percentile) to enter D1.
  - `upperLimit`: The maximum value observed within D1.

## Hurdle Values (Top Indicators)

| Indicator | Lower Limit (Hurdle) | Upper Limit (Max) |
| :--- | :--- | :--- |
| **per6m** | 54.59 | 1,556.44 |
| **per3m** | 34.30 | 1,587.50 |
| **per1y** | 75.57 | 2,383.19 |
| **median_50d** | 905.50 | 1,083.00 |
| **uptrend** | 4.00 | 5.00 |

## Cross-Occurrence Matrix (Full 20x20)

The following table shows the count of unique (Ticker, Day) pairs that simultaneously belong to the top decile (D1) for both the row indicator and the column indicator. `upperLimit` and `lowerLimit` represent the D1 value range for the row indicator.

| Indicator | upperLimit | lowerLimit | macd_histogram | macd_line | macd_signal | median_100d | median_10d | median_20d | median_30d | median_40d | median_50d | per1d | per1m | per1w | per1y | per3m | per6m | rank | rsi | stepup100 | stepup40 | uptrend |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| macd_histogram | 100.0 | 29.01 | 14434 | 5813 | 2700 | 1129 | 1168 | 1619 | 1546 | 1401 | 1317 | 3586 | 2899 | 7438 | 2370 | 2108 | 2392 | 279 | 4475 | 1400 | 1554 | 2642 |
| macd_line | 100.0 | 39.73 | 5813 | 14440 | 9984 | 510 | 39 | 131 | 225 | 282 | 385 | 2572 | 6689 | 5774 | 3492 | 4198 | 3869 | 9 | 9145 | 4077 | 4193 | 5997 |
| macd_signal | 100.0 | 47.83 | 2700 | 9984 | 14434 | 398 | 1 | 28 | 75 | 144 | 240 | 1744 | 7027 | 3289 | 3444 | 4508 | 3966 | 3 | 7667 | 4713 | 4677 | 5271 |
| median_100d | 1083.0 | 878.5 | 1129 | 510 | 398 | 14276 | 5775 | 6646 | 7463 | 8430 | 9397 | 1738 | 1300 | 1755 | 8 | 441 | 26 | 4795 | 632 | 1752 | 1930 | 945 |
| median_10d | 1083.0 | 943.5 | 1168 | 39 | 1 | 5775 | 14276 | 10720 | 9279 | 8270 | 7702 | 1473 | 50 | 864 | 80 | 15 | 14 | 8297 | 29 | 20 | 101 | 16 |
| median_20d | 1083.0 | 931.0 | 1619 | 131 | 28 | 6646 | 10720 | 14276 | 11541 | 10045 | 9106 | 1495 | 121 | 1197 | 40 | 29 | 23 | 7383 | 95 | 107 | 385 | 203 |
| median_30d | 1083.0 | 922.5 | 1546 | 225 | 75 | 7463 | 9279 | 11541 | 14276 | 11948 | 10653 | 1527 | 382 | 1362 | 25 | 37 | 24 | 6636 | 203 | 228 | 872 | 449 |
| median_40d | 1083.0 | 912.0 | 1401 | 282 | 144 | 8430 | 8270 | 10045 | 11948 | 14276 | 12307 | 1566 | 617 | 1448 | 1 | 39 | 15 | 6233 | 287 | 339 | 1505 | 597 |
| median_50d | 1083.0 | 905.5 | 1317 | 385 | 240 | 9397 | 7702 | 9106 | 10653 | 12307 | 14276 | 1627 | 831 | 1548 | 0 | 53 | 24 | 5916 | 375 | 536 | 1713 | 714 |
| per1d | 146.26 | 2.39 | 3586 | 2572 | 1744 | 1738 | 1473 | 1495 | 1527 | 1566 | 1627 | 14448 | 3784 | 5266 | 3248 | 3518 | 3649 | 231 | 3239 | 1656 | 1674 | 1392 |
| per1m | 1376.82 | 14.25 | 2899 | 6689 | 7027 | 1300 | 50 | 121 | 382 | 617 | 831 | 3784 | 14434 | 5862 | 4642 | 6954 | 5629 | 22 | 7073 | 4284 | 4295 | 4020 |
| per1w | 2954.3 | 5.89 | 7438 | 5774 | 3289 | 1755 | 864 | 1197 | 1362 | 1448 | 1548 | 5266 | 5862 | 14445 | 3724 | 4428 | 4184 | 84 | 5679 | 2359 | 2316 | 2833 |
| per1y | 2383.19 | 75.57 | 2370 | 3492 | 3444 | 8 | 80 | 40 | 25 | 1 | 0 | 3248 | 4642 | 3724 | 14254 | 5833 | 7834 | 109 | 2800 | 1301 | 1404 | 2095 |
| per3m | 1587.5 | 34.3 | 2108 | 4198 | 4508 | 441 | 15 | 29 | 37 | 39 | 53 | 3518 | 6954 | 4428 | 5833 | 14397 | 7354 | 24 | 4719 | 3398 | 2106 | 2721 |
| per6m | 1556.44 | 54.59 | 2392 | 3869 | 3966 | 26 | 14 | 23 | 24 | 15 | 24 | 3649 | 5629 | 4184 | 7834 | 7354 | 14332 | 17 | 3238 | 1932 | 1712 | 2244 |
| rank | 1086.0 | 974.0 | 279 | 9 | 3 | 4795 | 8297 | 7383 | 6636 | 6233 | 5916 | 231 | 22 | 84 | 109 | 24 | 17 | 14276 | 6 | 182 | 332 | 154 |
| rsi | 96.24 | 68.69 | 4475 | 9145 | 7667 | 632 | 29 | 95 | 203 | 287 | 375 | 3239 | 7073 | 5679 | 2800 | 4719 | 3238 | 6 | 14440 | 4589 | 4350 | 5734 |
| stepup100 | 3.0 | 3.0 | 1400 | 4077 | 4713 | 1752 | 20 | 107 | 228 | 339 | 536 | 1656 | 4284 | 2359 | 1301 | 3398 | 1932 | 182 | 4589 | 14276 | 7250 | 4490 |
| stepup40 | 3.0 | 3.0 | 1554 | 4193 | 4677 | 1930 | 101 | 385 | 872 | 1505 | 1713 | 1674 | 4295 | 2316 | 1404 | 2106 | 1712 | 332 | 4350 | 7250 | 14276 | 4874 |
| uptrend | 5.0 | 4.0 | 2642 | 5997 | 5271 | 945 | 16 | 203 | 449 | 597 | 714 | 1392 | 4020 | 2833 | 2095 | 2721 | 2244 | 154 | 5734 | 4490 | 4874 | 14506 |

# Trial 12: Combined Indicator Success Rate Lift

This trial explored whether filtering the already successful `per6m-D1` population by a secondary indicator (Top 10% or Bottom 10%) can yield an even higher success rate. 

## Methodology

- **Anchor Population**: All (Ticker, Day) pairs where `per6m` is in its top decile (D1).
- **Baseline Success Rate**: **46.69%** (Gain > 10% within 21 days).
- **Goal**: Find secondary filters (Indicator $X$ in D1 or D10) that provide the maximum "lift" to this baseline.

## Top Combined Indicators (Ranked by Success Rate)

| Combined Indicator | Condition | Cutoff Value | Count | Success Rate | Lift |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **median_40d** | Top 10% | **over 912.00** | 15 | **100.00%** | +53.31% |
| **median_50d** | Top 10% | **over 905.50** | 24 | **95.83%** | +49.14% |
| **median_100d** | Top 10% | **over 878.50** | 26 | **92.31%** | +45.62% |
| **rsi** | Bottom 10% | **under 36.75** | 378 | **54.50%** | +7.81% |
| **per1d** | Bottom 10% | **under -2.18** | 2,737 | **52.06%** | +5.37% |
| **per3m** | Top 10% | **over 34.30** | 7,314 | **51.75%** | +5.06% |

> [!TIP]
> While `median_40d` shows a theoretical 100% success rate, the sample size (N=15) is extremely low. 
> The combination of **`per6m` (over 54.59)** and **`per3m` (over 34.30)** is the most robust finding, maintaining a high count (**7,314**) while increasing the success rate to **51.75%**.

## Generated Files

- **Indicator Comparison**: [trial10_comparison.csv](file:///\\gandalf\sm-home\potentials\gainsuccess\output\trial10_comparison.csv)
- **Top 1 Full Decile (per6m)**: [trial10_full_decile_per6m.csv](file:///\\gandalf\sm-home\potentials\gainsuccess\output\trial10_full_decile_per6m.csv)
- **Cross-Decile Matrix**: [trial11_cross_deciles.csv](file:///\\gandalf\sm-home\potentials\gainsuccess\output\trial11_cross_deciles.csv)
- **Combined Lift Analysis**: [trial12_combined_lift.csv](file:///\\gandalf\sm-home\potentials\gainsuccess\output\trial12_combined_lift.csv)
- **Mod 1: Top 20%**: [trial13_mod1_top20.csv](file:///\\gandalf\sm-home\potentials\gainsuccess\output\trial13_mod1_top20.csv)
- **Mod 2: 40-Day Window**: [trial13_mod2_40days.csv](file:///\\gandalf\sm-home\potentials\gainsuccess\output\trial13_mod2_40days.csv)

- **Mod 3: Mixed Mixed**: [trial13_mod3_mixed.csv](file:///\\gandalf\sm-home\potentials\gainsuccess\output\trial13_mod3_mixed.csv)

# Trial 13: Top Combination Refinements

This trial re-evaluates the top 3 combinations from Trial 12 (`per6m` + `median_40d/50d/100d`) with modifications to the threshold and testing window.

## Modification 1: Use Top 20% instead of Top 10% (21-Day Window)

Increasing the candidate pool to the Top 20% significantly increases the sample size but leads to a drop in Success Rate compared to the 100% perfection seen in Trial 12.

| Combined Indicator | Condition | Count | Success Rate | Lift |
| :--- | :--- | :--- | :--- | :--- |
| **per6m (Base)** | Top 20% | 28,444 | 38.81% | |
| **median_40d** | Top 20% | 121 | **66.12%** | +27.30% |
| **median_50d** | Top 20% | 138 | **65.94%** | +27.13% |
| **median_100d** | Top 20% | 204 | **58.82%** | +20.01% |

## Modification 2: 40-Day Window (Top 10% Hurdle Kept)

Increasing the duration to 40 trading days (+10% gain reached sometime during 40 days) shows that the base `per6m` indicator significantly improves with time, and the top combinations remain nearly perfect.

| Combined Indicator | Condition | Count | Success Rate | Lift |
| :--- | :--- | :--- | :--- | :--- |
| **per6m (Base)** | Top 10% | 14,226 | 58.64% | |
| **median_40d** | Top 10% | 15 | **100.00%** | +41.36% |
| **median_50d** | Top 10% | 24 | **95.83%** | +37.19% |
| **median_100d** | Top 10% | 26 | **92.31%** | +33.67% |

## Modification 3: Mixed Thresholds (per6m Top 10% / Medians Top 20%)

This modification keeps the strict `per6m` anchor but loosens the secondary filters to the Top 20%. This provides a strong balance between a healthy sample size and a high success rate.

| Combined Indicator | Condition | Count | Success Rate | Lift |
| :--- | :--- | :--- | :--- | :--- |
| **per6m (Base)** | Top 10% | 14,226 | 46.69% | |
| **median_40d** | **Top 20%** | 43 | **81.40%** | +34.71% |
| **median_50d** | **Top 20%** | 53 | **77.36%** | +30.67% |
| **median_100d** | **Top 20%** | 111 | **69.37%** | +22.68% |

> [!CONCLUSION]
> Modification 3 identifies cases that are nearly twice as likely to succeed as the base `per6m` top decile while providing roughly 3-4x more trading opportunities than the original "Rare-Top3" criteria.

# Trial 14: Super-Sample Member Listing

Detailed listing of the 47 members identified in the "super-sample" (where `per6m` is in the Top 10% and `median_40d` is in the Top 20%).

| Ticker | Start Daynum | Max Gain (21-Day Window) |
| :--- | :--- | :--- |
| ETL.PA | 1929 | 9.01% |
| 1833.HK | 1931 | 27.12% |
| ETL.PA | 1931 | 6.84% |
| 1833.HK | 1932 | 29.31% |
| ETL.PA | 1932 | 6.53% |
| ETL.PA | 1933 | -4.27% |
| TLS | 1956 | 25.38% |
| TLS | 1957 | 24.78% |
| ETL.PA | 1962 | 4.82% |
| ETL.PA | 1963 | 4.82% |
| ETL.PA | 1964 | -1.23% |
| ETL.PA | 1965 | 1.90% |
| ETL.PA | 1966 | 5.92% |
| ETL.PA | 1967 | 3.21% |
| ETL.PA | 1968 | 8.77% |
| ETL.PA | 1969 | 11.25% |
| ETL.PA | 1970 | 13.07% |
| ETL.PA | 1971 | 17.69% |
| ETL.PA | 1972 | 21.68% |
| ETL.PA | 1973 | 32.50% |
| FLUX | 1981 | 102.22% |
| FLUX | 1982 | 129.14% |
| CLSK | 1983 | 72.36% |
| CLSK | 1984 | 70.34% |
| CLSK | 1985 | 68.85% |
| FCEL | 1985 | 19.06% |
| FLUX | 1985 | 110.93% |
| CLSK | 1986 | 66.79% |
| FCEL | 1986 | 25.88% |
| FLUX | 1986 | 134.51% |
| CLSK | 1987 | 60.55% |
| FCEL | 1987 | 31.83% |
| FLUX | 1987 | 101.21% |
| CLSK | 1988 | 69.59% |
| FCEL | 1988 | 45.05% |
| FLUX | 1988 | 101.82% |
| FCEL | 1989 | 44.68% |
| FLUX | 1989 | 75.26% |
| FCEL | 1990 | 46.92% |
| FLUX | 1990 | 48.99% |
| FCEL | 1991 | 46.54% |
| FCEL | 1992 | 30.93% |
| FCEL | 1993 | 31.68% |
| FCEL | 1994 | 11.95% |
| VKTX | 1998 | 9.12% |
| VKTX | 1999 | 13.74% |
| VKTX | 2002 | 16.12% |

> [!TIP]
> This list is available in CSV format at: [trial14_supersample_members.csv](file:///\\gandalf\sm-home\potentials\gainsuccess\output\trial14_supersample_members.csv)
