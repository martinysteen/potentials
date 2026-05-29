# -*- coding: utf-8 -*-
import yfinance as yf
import pandas as pd
import json
import time
import datetime
from zoneinfo import ZoneInfo   # Python 3.9+, for older use pytz library
import requests

verbose = False

def get_time_string (unix_timestamp, dateOnly=False):
    # Convert Unix timestamp to local datetime strong
    local_dt = datetime.datetime.fromtimestamp(unix_timestamp, tz=ZoneInfo("Europe/Berlin"))
    if dateOnly:
        return local_dt.strftime("%Y-%m-%d")
    else :
        return local_dt.strftime("%Y-%m-%d %H:%M")

# Time stamp for each record
current_timestamp = datetime.datetime.now().timestamp()     # Unix timestamp
print('Now is:', get_time_string(current_timestamp))

def format_number(value, precision=2):
    # European commas. All numbers made strings
    if isinstance(value, float):
        return f"{value:.{precision}f}".replace('.', ',')
    elif isinstance(value, int):
        return str(value)
    return value  # integers and other types are returned unchanged

# Create a session object to reuse connections
def create_yfinance_session():
    """Create a session with custom headers to appear more like a regular browser"""
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    })
    return session

# Global session (create once, reuse)
_yf_session = None

def get_session():
    """Get or create the global yfinance session"""
    global _yf_session
    if _yf_session is None:
        _yf_session = create_yfinance_session()
    return _yf_session

# Function to fetch today's stock data
def get_stock_info(ticker, popDescription=True, timeout=30):
    """
    Fetch stock information from Yahoo Finance
    
    Args:
        ticker: Stock symbol
        popDescription: Whether to remove description from result
        timeout: Request timeout in seconds (default 30)
    
    Returns:
        Dictionary with stock data
    
    Raises:
        ValueError: If no valid data is returned
        requests.exceptions.Timeout: If request times out
        Exception: For other errors
    """
    
    try:
        # Use session for connection reuse
        session = get_session()
        stock = yf.Ticker(ticker, session=session)
        
        # Fetch stock metadata with timeout
        info = stock.info
        
        # Check if we got valid data
        if not info or not isinstance(info, dict):
            raise ValueError(f"No valid data returned for ticker {ticker}")
        
        # Check if the response indicates an error (yfinance sometimes returns empty/error dicts)
        if len(info) < 5:  # Very minimal response likely means an error
            raise ValueError(f"Insufficient data returned for ticker {ticker} (possible invalid ticker or API issue)")
            
    except requests.exceptions.Timeout:
        raise Exception(f"Timeout while fetching data for {ticker}")
    except requests.exceptions.ConnectionError:
        raise Exception(f"Connection error while fetching data for {ticker}")
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429:
            raise Exception(f"Rate limited by Yahoo Finance for {ticker} - need to slow down")
        elif e.response.status_code == 404:
            raise Exception(f"Ticker {ticker} not found (404)")
        else:
            raise Exception(f"HTTP error {e.response.status_code} for {ticker}")
    except Exception as e:
        raise Exception(f"Error fetching data for {ticker}: {str(e)}")

    # Extract key metrics
    stock_data = {
        "FetchedDate": get_time_string(datetime.datetime.now().timestamp()),
        "Symbol": info.get("symbol", "N/A"),
        "Currency": info.get("financialCurrency", "N/A"),
        "PreviousClose": format_number(info.get("previousClose", "N/A")),
        "CurrentPrice": format_number(info.get("currentPrice", "N/A")),
        "DividendRate": format_number(info.get("dividendRate", "N/A")),
        "DividendYield_Pct": format_number(round(info.get("dividendYield", 0) * 100, 2))
            if info.get("dividendYield") else "N/A",
        "ExDivDate": (
            get_time_string(info.get("exDividendDate", 0), True)
            if info.get("exDividendDate") else "N/A"
        ),
        "PE_TTM": format_number(info.get("trailingPE", "N/A")),
        "PE_Fwd": format_number(info.get("forwardPE", "N/A")),
        "PS_TTM": format_number(info.get("priceToSalesTrailing12Months", "N/A")),
        "ProfitMargin": format_number(info.get("profitMargins", "N/A")),
        "FloatShares": format_number(info.get("floatShares", "N/A"), precision=0),
        "BookValue": format_number(info.get("bookValue", "N/A")),
        "PB": format_number(info.get("priceToBook", "N/A")),
        "EPS_TTM": format_number(info.get("trailingEps", "N/A")),
        "EPS_Fwd": format_number(info.get("forwardEps", "N/A")),
        "DividendLast": format_number(info.get("lastDividendValue", "N/A")),
        "Date_DividendLate": (
            get_time_string(info.get("lastDividendDate", 0), True)
            if info.get("lastDividendDate") else "N/A"
        ),
        "Target_HighPrice": format_number(info.get("targetHighPrice", "N/A")),
        "Target_LowPrice": format_number(info.get("targetLowPrice", "N/A")),
        "Target_MeanPrice": format_number(info.get("targetMeanPrice", "N/A")),
        "Target_MedianPrice": format_number(info.get("targetMedianPrice", "N/A")),
        "Recommendation_Mean": format_number(info.get("recommendationMean", "N/A")),
        "Recommendation_Key": info.get("recommendationKey", "N/A"),
        "NumberOfAnalysts": format_number(info.get("numberOfAnalystOpinions", "N/A"), precision=0),
        "Revenue_Total": format_number(info.get("totalRevenue", "N/A")),
        "RevenuePerShare": format_number(info.get("revenuePerShare", "N/A")),
        "FreeCashFlow": format_number(info.get("freeCashflow", "N/A")),
        "EarningsGrowth": format_number(info.get("earningsGrowth", "N/A")),
        "RevenueGrowth": format_number(info.get("revenueGrowth", "N/A")),
        "FullTimeEmpl": format_number(info.get("fullTimeEmployees", "N/A")),
        "Description": info.get("longBusinessSummary", "N/A"),
    }

    if stock_data["Description"] != "N/A" :
        stock_data["Description"] = stock_data["Symbol"] + ": " + stock_data["Description"]

    if popDescription :
        stock_data.pop("Description")

    return stock_data

def main():
    symbol = "0270.HK"

    # Print up-to date stock info
    dict_info = get_stock_info(symbol)
    print("Stock Info on", symbol)
    print(json.dumps(dict_info, indent=2))

if __name__ == "__main__":
    main()