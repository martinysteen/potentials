#!/usr/bin/env python
# coding: utf-8

# In[1]:


# Import necessary libraries
import pandas as pd
from datetime import datetime
import time
from pathlib import Path
import random
import gd_download  # your module that fetches the CSV from Google Drive
from getYfinanceData import get_stock_info

# NO DELAYS - FAST MODE
# Abort after X consecutive failures
MAX_CONSECUTIVE_FAILURES = 10
# Number of stocks: N=1... is literal number, N=0 pre-selected sample, N=-1 is all
N_stocks = -1

PATHFOLDER_INPUT = '../data/d0_repo/'
PATHFOLDER_DOWNLOAD = '../data/d1_ydata/'

#FILE_INPUT = 'Defence.csv'
#popDescription = False
FILE_INPUT = 'PotDat.csv'
popDescription = True

verbose = False


# In[2]:


# Load csv-files in local folder (./input) from Cloud-based repository
gd_download.main(PATHFOLDER_INPUT)


# In[3]:


# Define the file path (assuming the CSV is placed in ./app/input/)
file_path = PATHFOLDER_INPUT+FILE_INPUT

# Read the CSV (semicolon-separated; decimal as dot)
df = pd.read_csv(file_path, sep=';')

# The first column header contains the creation datetime.
creation_datetime = df.columns[0]
print(f"PotDat creation datetime: {creation_datetime}")

# Rename that first column header to 'Yahoo'
df.rename(columns={creation_datetime: 'Yahoo'}, inplace=True)

# Display the first few rows
df.head()


# In[4]:


# Filter the "Yahoo" column to remove indices (those starting with '^')
filtered_codes = df['Yahoo'][~df['Yahoo'].str.startswith('^')]

# For testing, pick the first 5 stock codes or a predefined bunch
if (N_stocks==0 ) :
    selected_codes =['ALC.SW', 'CWIGAKLA.CO', 'CTC-A.TO', 'NOVN.SW', 'CFR.SW', 'ROG.SW']
elif (N_stocks>0 ) : 
    selected_codes = filtered_codes.tail(N_stocks).tolist()
else :
    selected_codes = filtered_codes.tolist()        # All stocks in Potentials

print(f'\nSignal {N_stocks}: Data on {len(selected_codes)} stocks called from yfinance')

# RANDOMIZE THE ORDER OF STOCK TICKERS
random.shuffle(selected_codes)
print('Stock order randomized for this run')

if verbose:
    print('First stocks (randomized):')
    print(selected_codes[0:10])
    print('Last stocks (randomized):')
    print(selected_codes[-10:])


# In[5]:


#Prepare date-marking for output filenames
now_datetime = datetime.fromtimestamp(time.time())
formatted_date = now_datetime.strftime("%Y%m%d-%H%M")
#print('Date-marking for output files:', formatted_date)

#Core filename
if FILE_INPUT == 'Defence.csv' :
    filename_core = 'Defence-'+formatted_date
else :
    # Listen over parametre udvidet med EBITDA-margin i filer benævnt StockData2-
    if (N_stocks == -1) :
        filename_core = 'StockData2-'+formatted_date
    else :
        filename_core = 'StockData2-test'
print('Signal:', N_stocks, '  Core filename:', filename_core)


# In[6]:


# Get stock-info for all stocks in list selected_codes - FAST MODE (NO DELAYS, NO RETRIES)

# Timer start
start_time = time.perf_counter()

# Fetch data for each selected stock code
stock_data_list = []
failed_stocks = []
consecutive_failures = 0

for idx, code in enumerate(selected_codes, 1):
    # Print progress every 100 stocks (or first/last stock)
    if idx == 1 or idx == len(selected_codes) or idx % 100 == 0:
        print(f"Processing {idx}/{len(selected_codes)}: {code}")
    
    try:
        stock_data = get_stock_info(code, popDescription)
        stock_data_list.append(stock_data)
        consecutive_failures = 0  # Reset counter on success
    except Exception as e:
        print(f"  Failed: {code} - {e}")
        failed_stocks.append((code, str(e)))
        consecutive_failures += 1
        
        # Check if we should abort
        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            print(f"\n*** ABORTING: {MAX_CONSECUTIVE_FAILURES} consecutive failures detected ***")
            print(f"*** Successfully processed {len(stock_data_list)} stocks before abort ***")
            print(f"*** Failed on stocks: {[fs[0] for fs in failed_stocks[-MAX_CONSECUTIVE_FAILURES:]]} ***")
            break

# Create a new DataFrame from the fetched data
new_df = pd.DataFrame(stock_data_list)

# Optional: Reorder columns so that the stock code (e.g., 'Symbol') is the first column
if 'Symbol' in new_df.columns:
    cols = new_df.columns.tolist()
    cols.remove('Symbol')
    new_df = new_df[['Symbol'] + cols]

end_time = time.perf_counter()
print(f"\nGet_Stock_info's execution time: {(end_time - start_time)/60:.2f} min ----------")
print(f"Successfully fetched: {len(stock_data_list)} out of {len(selected_codes)} stocks")
print(f"Failed: {len(failed_stocks)} stocks")

if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
    print(f"*** Run was ABORTED due to {MAX_CONSECUTIVE_FAILURES} consecutive failures ***")

if failed_stocks and verbose:
    print("\nFailed stocks:")
    for code, error in failed_stocks[:10]:  # Show first 10 failures
        print(f"  {code}: {error}")

if verbose:
    print(new_df.head())


# In[7]:


from pathlib import Path
def saveCsvFile(path, filename_with_no_extension, df_input, myDelimiter=';', myDecimal=',') :
    ''' 
    Save file to csv-file (index are dropped all along)
       shared.saveCsvFile('./csvAll','Outliers_stockprices_zscores', df_input)
    '''
    dir_path = Path(path)
    filename = f'{filename_with_no_extension}.csv'
    csv_file_path = dir_path / filename  # Path object for the file
    
    # Create the directory if it does not exist
    dir_path.mkdir(parents=True, exist_ok=True)
               
    try:
        # index droppes (if to be saved it must be done before calling saveCsvFile)
        if 'index' in df_input.columns:
            df_to_save = df_input.reset_index(drop=True)
        else:
            # Use the DataFrame as is
            df_to_save = df_input


        # Save the DataFrame to CSV with index=False to avoid duplicating the index
        df_to_save.to_csv(csv_file_path, sep=myDelimiter, decimal=myDecimal, encoding='utf-8', index=False)
        print(f"\n{filename} shaped {df_to_save.shape} saved in {dir_path}")
    except PermissionError:
        print(f"Permission denied. Unable to save {filename}")
    except Exception as e:
        print(f"When saving {filename} an error occurred:", e)

if new_df.shape[0]!=0 :
    saveCsvFile(PATHFOLDER_DOWNLOAD, filename_core, new_df)

    import pyarrow
    dir_path = PATHFOLDER_DOWNLOAD
    filename = filename_core+'.parquet'
    new_df.to_parquet(dir_path+filename)
    print(f"\n{filename} shaped {new_df.shape} saved in {dir_path}")
else :
    print('No stock-data fetched from Yfinance')

    # Create a text file to log the failed attempt
    dir_path = Path(PATHFOLDER_DOWNLOAD)
    dir_path.mkdir(parents=True, exist_ok=True)
    filename = f'No_stock_data_{formatted_date}.txt'

    no_data_file = dir_path / filename
    with open(no_data_file, 'w', encoding='utf-8') as f:
        f.write(f"{formatted_date}: No stockdata fetched\n")
    
    print(f"Log file created: {no_data_file}")

# Save failed stocks log if any
if failed_stocks:
    dir_path = Path(PATHFOLDER_DOWNLOAD)
    dir_path.mkdir(parents=True, exist_ok=True)
    failed_log_file = dir_path / f'Failed_stocks_{formatted_date}.txt'
    with open(failed_log_file, 'w', encoding='utf-8') as f:
        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            f.write(f"*** RUN ABORTED after {MAX_CONSECUTIVE_FAILURES} consecutive failures ***\n")
            f.write(f"Successfully processed {len(stock_data_list)} stocks before abort\n\n")
        f.write(f"Failed to fetch data for {len(failed_stocks)} stocks:\n\n")
        for code, error in failed_stocks:
            f.write(f"{code}: {error}\n")
    print(f"Failed stocks log created: {failed_log_file}")