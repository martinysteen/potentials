# -*- coding: utf-8 -*-
import yfinance as yf
import pandas as pd
#import streamlit as st
import json
import time
import datetime
from zoneinfo import ZoneInfo   # Python 3.9+, for older use pytz library
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

# Function to fetch today's stock data
def get_stock_info(ticker, popDescription=True):

    stock = yf.Ticker(ticker)
    info = stock.info  # Fetch stock metadata
    if not info or not isinstance(info, dict):
        raise ValueError(f"No valid data returned for ticker {ticker}")
    #else:
        #print(json.dumps(info, indent=2))

    # Extract key metrics
    stock_data1 = {
        "FetchedDate": get_time_string(datetime.datetime.now().timestamp()),
        "Symbol": info.get("symbol", "N/A"),
        "Currency": info.get("financialCurrency", "N/A"),
        "PreviousClose": format_number(info.get("previousClose", "N/A")),
        "CurrentPrice": format_number(info.get("currentPrice", "N/A")),
    }

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
