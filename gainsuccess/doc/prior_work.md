# Stock Indicator Gain Analysis - Walkthrough

## Phase 1: Single Indicator Investigation

**Objective**: Systematically identify indicators that reliably predict a >10% gain over 20 trading days (`Gain20d`).

### Subphase 1.1: Finding Top Indicators (Corrected Analysis)

**Critical Correction**: Previous runs inadvertently tested "Backward Gain" (Past Performance). We have corrected the logic to strictly test "Forward Gain" (Predictive Performance). The results consistently identify realistic "edges" over the market baseline.

We tested all 35 indicators using a **Global Threshold** approach (pooling all dates and stocks).

#### Key Findings (Corrected)

1.  **Volatility is King**:
    - **`longi_vola100d` (Top Decile)**: **34.6% Success Rate** (Mean Gain 5.8%).
    - **`longi_vola20d` (Top Decile)**: **31.8% Success Rate**.
    - *Insight*: To achieve >10% gains in short windows (20 days), you strictly need high volatility. Quiet stocks rarely make the move.

2.  **Spread & Long-Term Momentum**:
    - **`longi_spr250d` (Top Decile)**: **31.8% Success Rate**.
    - **`longi_per1y` (Top Decile)**: **30.2% Success Rate**.
    - *Insight*: Stocks with high spread (often correlated with volatility) and strong long-term trends perform well.

3.  **Reversion over Momentum**:
    - **`longi_PdivMA50` & `PdivMA20`**: The **Bottom Decile** (Price below MA) outperforms the Top Decile.
    - **Success Rate**: ~26.4%.
    - *Insight*: "Buying the Dip" (Reversion) offers a better edge than "Buying the Breakout" for 20-day horizons. Note that short-term momentum (`per1m`) faded in predictive power compared to volatility.

#### Top 10 Leaderboard (Predictive Power)

| Rank | Indicator | Range (Decile) | Success Rate | Mean Gain | Samples |
|------|-----------|----------------|--------------|-----------|---------|
| 1 | **longi_vola100d** | **Top Decile** | **34.59%** | **5.8%** | 45,187 |
| 2 | **longi_vola20d** | **Top Decile** | **31.82%** | 4.9% | 53,884 |
| 3 | **longi_spr250d** | **Top Decile** | **31.75%** | 5.6% | 28,520 |
| 4 | **longi_per1y** | **Top Decile** | **30.22%** | 3.9% | 26,881 |
| 5 | longi_spr100d | Top Decile | 29.54% | 4.4% | 45,005 |
| 6 | longi_PdivMA200 | Top Decile | 28.64% | 3.6% | 34,004 |
| 7 | longi_per6m | Top Decile | 27.56% | 2.9% | 41,362 |
| 8 | longi_per1y | Bottom Decile | 27.12% | 1.8% | 26,892 |
| 9 | **longi_PdivMA50** | **Bottom Decile** | **26.43%** | 3.8% | 50,573 |
| 10 | longi_PdivMA20 | Bottom Decile | 26.25% | 3.8% | 53,956 |
| 11 | **longi_macd_Z** | Top Value (ZOP) | 15.60% | 1.7% | 36,025 |

---

### Subphase 1.2: Across-Days Stability of 20d Hits

**Objective**: Verify if the "Global Threshold" strategy for our new champion (**`longi_vola100d`**, Threshold > 3.98) provides consistent opportunities.

**Methodology**:
- Analyzed hits per day for `longi_vola100d` > 3.98 across the 531-day dataset.

#### Key Findings (Subphase 1.2 - Corrected)

1.  **Warm-Up Period / Dead Zone**:
    - **18.8% of days (100 days)** had zero hits.
    - **Cause**: These were exclusively at the start of the dataset (Day 1288–1632). This is likely due to the indicator requiring 100 days of history to stabilize, or a period of extremely low volatility.

2.  **Robust Active Phase**:
    - Once the signal activates (Day 1633+), it is **highly consistent**.
    - **Avg Hits/Day**: ~88 stocks.
    - **Max Hits/Day**: 334 stocks (capturing volatility spikes).
    - It does *not* disappear during recent history.

**Conclusion**: The "Dead Zone" is an artifact of the indicator's long window (100d). For an active trading strategy, this is acceptable: it simply stays out of the market until volatility regimes define themselves.

**Coverage Plot (Simplified)**:
```text
Day 1288-1632:   0.0 hits | (Warm-up / Low Vol)
Day 1633-1648:  52.2 hits |#########
Day 1649-1664:  87.2 hits |###############
...
Day 1884-1899: 168.6 hits |##############################
Day 2057-2072:  95.7 hits |#################
```

---

### Subphase 1.3: Gain Distribution Analysis
**Objective**: Analyze the full risk/reward profile of key indicators to verify "quality" of gains.

**Methodology**:
Comparison of the former top pick (`per1m`) vs the new top pick (`vola100d`) vs user interest (`PdivMA50`). All stats for **Top Decile**.

| Metric | `longi_per1m` | `longi_PdivMA50` | `longi_vola100d` (New King) |
|:-------|:--------------|:-----------------|:---------------------------|
| **Mean Gain** | 3.13% | 2.65% | **5.81%** |
| **Median Gain** | 1.13% | 0.73% | **2.44%** |
| **Success Rate (>10%)** | 23.9% | 23.5% | **34.6%** |
| **Upside (95th Pctl)** | 33.0% | 32.5% | **48.2%** |
| **Tail Risk (5th Pctl)** | -21.6% | -21.8% | -27.3% |

**Conclusion**:
Volatility (`vola100d`) is vastly superior. It offers nearly double the mean gain and massive upside potential (48% vs 33%), at the cost of slightly higher tail risk (-27% vs -21%). This confirms that **hunting volatility** is the most effective single-factor strategy for 20-day gains.

## Phase 2: Factor Interaction Explorations

### Subphase 2.1: Interaction Matrix (Broad Exploration)

**Objective**: SYSTEMATICALLY explore interactions between key "Pivot" indicators (Volatility, Spread, Reversion) and the entire universe to identify "Super-Synergies".

**Methodology**:
- **Pivots**: `vola100d`, `spr250d`, `per1y`, `PdivMA50`, `macd_Z`.
- **Tested**: All pairs (Pivot + Candidate).
- **Metric**: Success Rate (>10% Gain) and Failure Rate (>10% Loss).

#### Key Key Findings (Phase 2.1)

1.  **The "Golden Pair" (Spread + Volatility)**:
    - **Combination**: `longi_spr250d` (Top) + `longi_vola20d` (Top).
    - **Success Rate**: **46.3%** (vs Baseline 31.7%).
    - **Synergy**: **+14.6%** boost.
    - **Risk**: 22.5% Failure Rate.
    - **Ratio**: You are **2.05x** more likely to win big (>10%) than lose big (>10%).

2.  **Runner Up**: `longi_spr250d` (Top) + `longi_vola100d` (Top) @ **44.6%** Success.

3.  **Spread + Reversion**:
    - `longi_spr250d` (Top) + `longi_median_30d` (Bottom) @ **42.0%** Success.
    - Insight: Buying high-spread stocks that are currently at a "low point" (low median) is a powerful strategy.

**Conclusion**: The strongest "Island of Success" found so far is **High Spread + High Volatility**. This confirms a "High Energy" thesis: stocks that are moving fast and have wide trading ranges are the ones that deliver 20-day windfalls.

### Subphase 2.2: Pairwise Availability Analysis (Matrix Density)
**Objective**: Determine how many potential trades ("cases") exist for every pair of Top 10 indicators. This filters out "thin" combinations that are statistical flukes.

**Methodology**:
- Calculated intersection counts for all pairwise combinations of the Top 11 signals.

**Key Findings**:
1.  **Robust "Islands" (High Density)**:
    - **Volatility + Spread**: `vola100d_Top` + `spr100d_Top` (20,289 cases). This sector is massive and liquid.
    - **Spread + Reversion**: `spr100d_Top` + `PdivMA50_Bot` (28,046 cases). A very common setup ("Volatile stock dipping below MA").
    - **Mean Reversion**: `per1y_Bot` (Losers) + `spr250d_Top` (High Spread) (18,708 cases).

2.  **Thin/Dangerous Zones (Avoid)**:
    - **Contradictory Trends**: `PdivMA200_Top` (Long Term Uptrend) + `per1y_Bot` (Long Term Loser). Only **103 cases**. Physically nearly impossible.
    - **Trend + Spread Mismatch**: `spr250d_Top` + `PdivMA200_Top` (526 cases). High spread stocks rarely have the smooth uptrend required for high PdivMA200.

**Recommendation**: Focus Phase 2.3 testing on the **High Density** pairs found in the "Volatility/Spread" and "Reversion" clusters. Avoid the thin Trend/Counter-Trend mixes.

### Subphase 2.3: Viability Check (Case Counts)
**Objective**: precise verification of sample volumes for both "High Performance" (Synergy) and "High Volume" (Dense) clusters.

**Category A: High Performance (Synergy Leaders from 2.1)**
*Refined subsets (Conditional Top 10%) with highest success rates (~46%).*
1.  **`spr250d_Top` + `vola20d_Top`**: **2,855 Cases**.
2.  **`spr250d_Top` + `vola100d_Top`**: **2,859 Cases**.
3.  **`spr250d_Top` + `median_30d_Bot`**: **2,845 Cases**.
*Verdict: Actionable (>2,800 cases).*

**Category B: High Volume (Dense Islands from 2.2)**
*Massive overlaps of global top deciles. Lower validated success (untouched in 2.1) but huge liquidity.*
1.  **`spr100d_Top` + `PdivMA50_Bot`**: **28,046 Cases** (Massive Reversion Setup).
2.  **`spr100d_Top` + `vola100d_Top`**: **20,289 Cases**.
3.  **`spr250d_Top` + `per1y_Bot`**: **18,708 Cases** (Strategic Reversion).

**Conclusion**: We have two distinct trading distinct opportunities:
1.  **Sniper Strategy** (Category A): ~46% Success, ~2,800 trades.
2.  **Volume Strategy** (Category B): Unknown Success (likely ~30-35%), ~20,000+ trades.

Phase 3 will focus on verifying the performance of Category B to see if they can rival Category A.

## Phase 3: Island Performance Analysis (Deep Dive)

**Objective**: Determine the definitive "Quality vs Quantity" trade-off for the 6 Islands using standardized Global Thresholds.

### Performance Leaderboard (Global Deciles)

| Island (Pair) | Category | Samples | Success (>10%) | Fail (<-10%) | Ratio | Mean Gain |
|:---|:---|:---|:---|:---|:---|:---|
| **A1: Spr250d + Vola20d** | Sniper | **11,481** | **40.8%** | 20.1% | **2.03** | **9.79%** |
| **A2: Spr250d + Vola100d** | Sniper | 12,605 | 38.3% | 21.3% | 1.80 | 8.83% |
| **B2: Spr100d + Vola100d** | Volume | **19,388** | 35.5% | 23.0% | 1.54 | 6.70% |
| **B1: Spr100d + PdivMA50** | Volume | **26,790** | 31.0% | **18.8%** | 1.65 | 5.12% |
| **B3: Spr250d + Per1y** | Volume | 17,400 | 30.4% | 18.4% | 1.65 | 5.37% |
| *A3: Spr250d + Med30d* | Sniper | 310 | 33.2% | 35.5% | 0.94 | 1.68% |

### Key Conclusions

1.  **The Supreme Winner: A1 (`spr250d_Top` + `vola20d_Top`)**
    *   **Performance**: Dominates all other islands with **40.8% Success Rate** and a massive **9.8% Mean Gain** per trade.
    *   **Risk/Reward**: Highest Ratio (2.03). You win 2x more often than you lose big.
    *   **Volume**: 11,481 cases is highly liquid (approx 20 trades/day).
    *   *Strategy*: This is the "Go-To" strategy for maximizing returns.

2.  **The Volume King: B1 (`spr100d_Top` + `PdivMA50_Top` Bot)**
    *   **Performance**: Lower success (31%) and gain (5%), but **lowest risk** (18.8% failure).
    *   **Volume**: Massive 26,790 cases.
    *   *Strategy*: A safer, high-frequency "grinder" strategy.

3.  **The Collapse of A3**:
    *   `spr250d` + `median_30d` failed under Global Thresholds (only 310 cases, neg ratio). It relies entirely on finding absolute local minima *within* a spread, which global thresholds don't capture well.

**Final Recommendation**:
Prioritize **A1 (Spread+Vola)** for the final production strategy. It offers the best blend of high probability, high payout, and sufficient liquidity.
