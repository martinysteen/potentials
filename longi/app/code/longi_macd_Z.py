#!/usr/bin/env python3
"""
MACD Histogram Zero-Crossing Detection Module

Detects transitions in MACD histogram values:
- Positive to negative transitions → 'ZNED' (zero crossing negative)
- Negative to positive transitions → 'ZOP' (zero crossing positive)
- All other values remain empty

Input: output/longi_macd_histogram.csv
Output: output/longi_macd_Z.csv
"""

import sys
import os
import pandas as pd
import numpy as np
from pathlib import Path


def main():
    try:
        # Get the app directory
        script_dir = Path(__file__).parent
        app_dir = script_dir.parent
        
        input_file = app_dir / "output" / "longi_macd_histogram.csv"
        output_file = app_dir / "output" / "longi_macd_Z.csv"
        
        # Read the input file
        print(f"Reading {input_file}")
        df = pd.read_csv(input_file, sep=";", decimal=",", index_col=0)
        
        print(f"Input shape: {df.shape}")
        print(f"Processing {len(df)} tickers")
        
        # Create output dataframe with same structure - use object dtype to avoid warnings
        result = df.astype(object)
        result[:] = ""  # Initialize with empty strings
        
        # Process each row (ticker)
        for idx, row in df.iterrows():
            # Convert to numeric, handling European format and empty values
            values = []
            for val in row:
                try:
                    if pd.isna(val) or val == "":
                        values.append(np.nan)
                    else:
                        # Handle European format (comma as decimal)
                        val_str = str(val).replace(",", ".")
                        values.append(float(val_str))
                except:
                    values.append(np.nan)
            
            # Detect zero crossings
            for i in range(len(values) - 1):
                current = values[i]
                next_val = values[i + 1]
                
                # Skip if either value is NaN
                if pd.isna(current) or pd.isna(next_val):
                    continue
                
                # Time goes right-to-left (oldest to newest)
                # next_val (i+1) is older, current (i) is newer
                # Check for negative to positive transition (ZOP)
                if next_val < 0 and current > 0:
                    result.iloc[df.index.get_loc(idx), i] = "ZOP"
                # Check for positive to negative transition (ZNED)
                elif next_val > 0 and current < 0:
                    result.iloc[df.index.get_loc(idx), i] = "ZNED"
        
        # Write output file with European format
        print(f"Writing {output_file}")
        result.to_csv(output_file, sep=";", decimal=",", quoting=False)
        
        print(f"Output shape: {result.shape}")
        print("MACD Zero-Crossing detection completed successfully")
        return 0
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
