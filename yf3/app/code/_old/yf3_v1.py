#!/usr/bin/env python
# coding: utf-8

# In[1]:


# Import necessary libraries
import pandas as pd
from datetime import datetime
import time
from pathlib import Path
import gd_download  # your module that fetches the CSV from Google Drive
from getYfinanceData import get_stock_info

# Making fetch more appetizing to Yfinance
import random
# Pause between requests - increased from 10 to 15-20 seconds
SLEEPTIME_MIN = 15
SLEEPTIME_MAX = 25
# Retry settings
MAX_RETRIES = 3
RETRY_DELAY = 30  # seconds to wait before retry
# Batch processing - take a longer break after every N stocks
BATCH_SIZE = 5
BATCH_BREAK = 60  # seconds

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

if verbose:
    print('First stocks:')
    print(selected_codes[0:10])
    print('Last stocks:')
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
    if (N_stocks == -1) :
        filename_core = 'StockData-'+formatted_date
    else :
        filename_core = 'StockData-test'
print('Signal:', N_stocks, '  Core filename:', filename_core)


# In[6]:


# Get stock-info for all stocks in list selected_codes

# Timer start
start_time = time.perf_counter()

# Fetch data for each selected stock code
stock_data_list = []
for idx, code in enumerate(selected_codes, 1):
    print(f"Processing {idx}/{len(selected_codes)}: {code}")
    
    # Retry logic
    success = False
    for attempt in range(MAX_RETRIES):
        try:
            stock_data = get_stock_info(code, popDescription)
            stock_data_list.append(stock_data)
            success = True
            break  # Success, exit retry loop
        except Exception as e:
            print(f"  Attempt {attempt + 1} failed for {code}: {e}")
            if attempt < MAX_RETRIES - 1:
                print(f"  Waiting {RETRY_DELAY} seconds before retry...")
                time.sleep(RETRY_DELAY)
            else:
                print(f"  Giving up on {code} after {MAX_RETRIES} attempts")
    
    if success:
        # Random sleep time between requests (more human-like)
        sleep_time = random.uniform(SLEEPTIME_MIN, SLEEPTIME_MAX)
        print(f"  Waiting {sleep_time:.1f} seconds...")
        time.sleep(sleep_time)
        
        # Longer break after each batch
        if idx % BATCH_SIZE == 0 and idx < len(selected_codes):
            print(f"\n--- Batch break: waiting {BATCH_BREAK} seconds ---\n")
            time.sleep(BATCH_BREAK)

# Create a new DataFrame from the fetched data
new_df = pd.DataFrame(stock_data_list)

# Optional: Reorder columns so that the stock code (e.g., 'Symbol') is the first column
if 'Symbol' in new_df.columns:
    cols = new_df.columns.tolist()
    cols.remove('Symbol')
    new_df = new_df[['Symbol'] + cols]

end_time = time.perf_counter()
print(f"\nGet_Stock_info's execution time: {(end_time - start_time)/60:.2f} min ----------")
print(f"Fetched data for {len(stock_data_list)} out of {len(selected_codes)} stocks")

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
