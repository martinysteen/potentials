"""
Yahoo Finance Data Fetcher

Fetches stock information from Yahoo Finance with optimized session management
and European number formatting.
"""

import json
import datetime
from zoneinfo import ZoneInfo
import requests
import yfinance as yf


# Configuration
TIMEZONE = "Europe/Berlin"
VERBOSE = False


# Session Management
_yf_session = None


def get_session():
    """Get or create the global yfinance session with browser-like headers."""
    global _yf_session
    if _yf_session is None:
        _yf_session = requests.Session()
        _yf_session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
    return _yf_session


# Utility Functions
def get_time_string(unix_timestamp, date_only=False):
    """
    Convert Unix timestamp to local datetime string.
    
    Args:
        unix_timestamp: Unix timestamp to convert
        date_only: If True, return only date (YYYY-MM-DD), else include time
    
    Returns:
        Formatted datetime string
    """
    local_dt = datetime.datetime.fromtimestamp(unix_timestamp, tz=ZoneInfo(TIMEZONE))
    if date_only:
        return local_dt.strftime("%Y-%m-%d")
    else:
        return local_dt.strftime("%Y-%m-%d %H:%M")


def format_number(value, precision=2):
    """
    Format number with European convention (comma as decimal separator).
    
    Args:
        value: Number to format
        precision: Number of decimal places for floats
    
    Returns:
        Formatted string with comma as decimal separator
    """
    if isinstance(value, float):
        return f"{value:.{precision}f}".replace('.', ',')
    elif isinstance(value, int):
        return str(value)
    return value


# Main Data Fetching Function
def get_stock_info(ticker, pop_description=True, timeout=10):
    """
    Fetch stock information from Yahoo Finance.

    Args:
        ticker: Stock symbol (e.g., 'AAPL', '0270.HK')
        pop_description: Whether to remove description from result
        timeout: Request timeout in seconds

    Returns:
        Dictionary with stock data including metrics like price, PE ratio, dividends, etc.

    Raises:
        ValueError: If no valid data is returned
        Exception: For other errors
    """
    # Let yfinance handle the session (required for curl_cffi support)
    stock = yf.Ticker(ticker)
    
    # Fetch stock metadata
    info = stock.info
    
    # Validate response
    if not info or not isinstance(info, dict):
        raise ValueError(f"No valid data returned for ticker {ticker}")
    
    if len(info) < 5:
        raise ValueError(f"Insufficient data returned for ticker {ticker}")

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
        "Date_DividendLast": (
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
        "GrossMargin": format_number(info.get("grossMargins", "N/A")),
        "EbitdaMargin": format_number(info.get("ebitdaMargins", "N/A")),
        "OperatingMargin": format_number(info.get("operatingMargins", "N/A")),
        "TrailingPEG": format_number(info.get("trailingPegRatio", "N/A")),
        "FullTimeEmpl": format_number(info.get("fullTimeEmployees", "N/A")),
        "Description": info.get("longBusinessSummary", "N/A"),
    }

    # Add symbol prefix to description
    if stock_data["Description"] != "N/A":
        stock_data["Description"] = f"{stock_data['Symbol']}: {stock_data['Description']}"

    # Remove description if requested
    if pop_description:
        stock_data.pop("Description")

    return stock_data


def main():
    """Example usage of the stock info fetcher."""
    symbol = "0270.HK"
    
    current_timestamp = datetime.datetime.now().timestamp()
    print(f'Now is: {get_time_string(current_timestamp)}')
    
    print(f"\nStock Info on {symbol}")
    dict_info = get_stock_info(symbol)
    print(json.dumps(dict_info, indent=2))


if __name__ == "__main__":
    main()
