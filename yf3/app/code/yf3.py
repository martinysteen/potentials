"""
Yahoo Finance Bulk Stock Data Fetcher

Fetches stock data from Yahoo Finance for multiple tickers from a CSV file
and saves the results to CSV format.
"""

import random
import time
from datetime import datetime
from pathlib import Path
import pandas as pd

import gd_download
from getYfinanceData import get_stock_info


# Configuration
MAX_CONSECUTIVE_FAILURES = 10  # Abort after X consecutive failures
N_STOCKS = -1  # N=1... literal number, N=0 pre-selected sample, N=-1 is all

PATHFOLDER_INPUT = '../input/'
PATHFOLDER_DOWNLOAD = '../output/'

FILE_INPUT = 'PotDat.csv'
#FILE_INPUT = 'Defense.csv'
POP_DESCRIPTION = True

VERBOSE = False


# Utility Functions
def save_csv_file(path, filename_no_extension, df_input, delimiter=';', decimal=','):
    """
    Save DataFrame to CSV file with European formatting.
    
    Args:
        path: Directory path for saving
        filename_no_extension: Base filename without extension
        df_input: DataFrame to save
        delimiter: CSV delimiter
        decimal: Decimal separator
    """
    dir_path = Path(path)
    filename = f'{filename_no_extension}.csv'
    csv_file_path = dir_path / filename
    
    # Create directory if it doesn't exist
    dir_path.mkdir(parents=True, exist_ok=True)
    
    try:
        # Remove index if present
        if 'index' in df_input.columns:
            df_to_save = df_input.reset_index(drop=True)
        else:
            df_to_save = df_input
        
        # Save DataFrame to CSV
        df_to_save.to_csv(
            csv_file_path,
            sep=delimiter,
            decimal=decimal,
            encoding='utf-8',
            index=False
        )
        print(f"\n{filename} shaped {df_to_save.shape} saved in {dir_path}")
    except PermissionError:
        print(f"Permission denied. Unable to save {filename}")
    except Exception as e:
        print(f"Error saving {filename}: {e}")


def load_stock_codes(file_path, n_stocks=None):
    """
    Load stock codes from CSV file.
    
    Args:
        file_path: Path to CSV file
        n_stocks: Number of stocks to select (None/-1 for all, 0 for sample)
    
    Returns:
        Tuple of (list of stock codes, creation datetime)
    """
    df = pd.read_csv(file_path, sep=';')
    
    # First column header contains creation datetime
    creation_datetime = df.columns[0]
    df.rename(columns={creation_datetime: 'Yahoo'}, inplace=True)
    
    # Filter out indices (starting with '^')
    filtered_codes = df['Yahoo'][~df['Yahoo'].str.startswith('^')]
    
    # Select stocks based on N_STOCKS parameter
    if n_stocks == 0:
        # Pre-selected sample for testing
        selected_codes = ['ALC.SW', 'CWIGAKLA.CO', 'CTC-A.TO', 'NOVN.SW', 'CFR.SW', 'ROG.SW']
    elif n_stocks and n_stocks > 0:
        selected_codes = filtered_codes.tail(n_stocks).tolist()
    else:
        selected_codes = filtered_codes.tolist()
    
    # Randomize order
    random.shuffle(selected_codes)
    
    return selected_codes, creation_datetime


def fetch_stock_data(stock_codes, pop_description=True):
    """
    Fetch stock data for multiple tickers.
    
    Args:
        stock_codes: List of stock ticker symbols
        pop_description: Whether to exclude description from results
    
    Returns:
        Tuple of (DataFrame with stock data, list of failed stocks)
    """
    start_time = time.perf_counter()
    
    stock_data_list = []
    failed_stocks = []
    consecutive_failures = 0
    
    for idx, code in enumerate(stock_codes, 1):
        # Progress indicator
        if idx == 1 or idx == len(stock_codes) or idx % 100 == 0:
            print(f"Processing {idx}/{len(stock_codes)}: {code}")
        
        try:
            stock_data = get_stock_info(code, pop_description)
            stock_data_list.append(stock_data)
            consecutive_failures = 0
        except Exception as e:
            print(f"  Failed: {code} - {e}")
            failed_stocks.append((code, str(e)))
            consecutive_failures += 1
            
            # Check if we should abort
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                print(f"\n*** ABORTING: {MAX_CONSECUTIVE_FAILURES} consecutive failures ***")
                break
    
    # Create DataFrame from fetched data
    df = pd.DataFrame(stock_data_list)
    
    # Reorder columns to put Symbol first
    if 'Symbol' in df.columns:
        cols = df.columns.tolist()
        cols.remove('Symbol')
        df = df[['Symbol'] + cols]
    
    # Print summary
    end_time = time.perf_counter()
    execution_time = (end_time - start_time) / 60
    print(f"\nExecution time: {execution_time:.2f} min")
    print(f"Fetched: {len(stock_data_list)} out of {len(stock_codes)} stocks")
    print(f"Failed: {len(failed_stocks)} stocks")
    
    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
        print(f"*** Run was ABORTED due to {MAX_CONSECUTIVE_FAILURES} consecutive failures ***")
    
    if failed_stocks and VERBOSE:
        print("\nFailed stocks:")
        for code, error in failed_stocks[:10]:
            print(f"  {code}: {error}")
    
    return df, failed_stocks


def save_results(df, failed_stocks, filename_core, output_path):
    """
    Save fetched data and failure log.
    
    Args:
        df: DataFrame with stock data
        failed_stocks: List of failed stock tuples 
        filename_core: Base filename for output files
        output_path: Directory for output files
    """
    now = datetime.fromtimestamp(time.time())
    formatted_date = now.strftime("%Y%m%d-%H%M")
    
    if df.shape[0] != 0:
        # Sort by Symbol for organized output
        if 'Symbol' in df.columns:
            df = df.sort_values('Symbol').reset_index(drop=True)

        # Save CSV
        save_csv_file(output_path, filename_core, df)
    '''
    else:
        # Log no data fetched
        print('No stock data fetched from Yahoo Finance')
        dir_path = Path(output_path)
        dir_path.mkdir(parents=True, exist_ok=True)
        
        no_data_file = dir_path / f'No_stock_data_{formatted_date}.txt'
        with open(no_data_file, 'w', encoding='utf-8') as f:
            f.write(f"{formatted_date}: No stock data fetched\n")
        print(f"Log file created: {no_data_file}")
    '''
    
    # Save failed stocks log
    if failed_stocks:
        if VERBOSE :
            dir_path = Path(output_path)
            dir_path.mkdir(parents=True, exist_ok=True)
            
            failed_log_file = dir_path / f'Failed_stocks_{formatted_date}.txt'
            with open(failed_log_file, 'w', encoding='utf-8') as f:
                if len([fs for fs in failed_stocks]) >= MAX_CONSECUTIVE_FAILURES:
                    f.write(f"*** RUN ABORTED after {MAX_CONSECUTIVE_FAILURES} consecutive failures ***\n")
                    f.write(f"Successfully processed {df.shape[0]} stocks before abort\n\n")
                f.write(f"Failed to fetch data for {len(failed_stocks)} stocks:\n\n")
                for code, error in failed_stocks:
                    f.write(f"{code}: {error}\n")
            print(f"Failed stocks log created: {failed_log_file}")
        else :
            print(f"FAILURE: Some stocks were not processed. Turn VERBOSE on to log more info.")

def main():
    """Main execution flow."""
    print(f'Signal {N_STOCKS}: Data on stocks will be fetched from Yahoo Finance')
    
    # Download CSV files from Google Drive to local folder
    gd_download.main(PATHFOLDER_INPUT)
    
    # Load stock codes from CSV
    file_path = Path(PATHFOLDER_INPUT) / FILE_INPUT
    selected_codes, creation_datetime = load_stock_codes(file_path, N_STOCKS)
    
    print(f"PotDat creation datetime: {creation_datetime}")
    print(f"Fetching data for {len(selected_codes)} stocks (randomized order for fetching)")
    print("Note: Final output will be sorted alphabetically by ticker")
    
    if VERBOSE:
        print('First stocks (randomized):', selected_codes[:10])
        print('Last stocks (randomized):', selected_codes[-10:])
    
    # Generate output filename
    now = datetime.fromtimestamp(time.time())
    formatted_date = now.strftime("%Y%m%d-%H%M")
    
    if FILE_INPUT == 'Defense.csv':
        filename_core = f'Defense-{formatted_date}'
    else:
        filename_core = f'StockData2-{formatted_date}' if N_STOCKS == -1 else 'StockData2-test'
    
    print(f'Signal: {N_STOCKS}  Core filename: {filename_core}')
    
    # Fetch stock data
    stock_df, failed_stocks = fetch_stock_data(selected_codes, POP_DESCRIPTION)
    
    # Save results
    save_results(stock_df, failed_stocks, filename_core, PATHFOLDER_DOWNLOAD)


if __name__ == "__main__":
    main()
