"""
Shared Functions for Longi Pipeline Modules

Contains utility functions used across multiple longi_*.py modules.
"""

import csv
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime


# File paths
INPUT_DIR = Path(__file__).parent.parent / "input"
CAL_FILE = INPUT_DIR / "Cal.csv"


def parse_european_decimal(value: str) -> Optional[float]:
    """
    Parse European decimal format (comma as decimal separator).

    Args:
        value: String value to parse (e.g., "123,45")

    Returns:
        Float value or None if empty/invalid
    """
    value = value.strip()
    if not value:
        return None
    try:
        # Replace comma with dot for Python float parsing
        return float(value.replace(',', '.'))
    except ValueError:
        return None


def format_european_decimal(value: Optional[float], decimals: int = 2) -> str:
    """
    Format float to European decimal format (comma as decimal separator).

    Args:
        value: Float value to format
        decimals: Number of decimal places

    Returns:
        Formatted string or empty string if value is None
    """
    if value is None:
        return ""
    # Format with specified decimals and replace dot with comma
    return f"{value:.{decimals}f}".replace('.', ',')


def parse_a1_datetime(datetime_str: str) -> datetime:
    """
    Parse the datetime string from A1 cell of downloaded files.

    Expected format: "Thu Nov 06 2025 00:43:29 GMT+0100 (Central European Standard Time)"

    Args:
        datetime_str: Datetime string from A1 cell

    Returns:
        datetime object

    Raises:
        ValueError: If datetime string cannot be parsed
    """
    # Extract just the date portion: "Thu Nov 06 2025"
    # Format: Day Month DD YYYY
    parts = datetime_str.split()

    if len(parts) < 4:
        raise ValueError(f"Invalid datetime format: {datetime_str}")

    # parts[0] = weekday (not needed)
    # parts[1] = month name
    # parts[2] = day
    # parts[3] = year

    date_str = f"{parts[1]} {parts[2]} {parts[3]}"

    # Parse using strptime
    dt = datetime.strptime(date_str, "%b %d %Y")

    return dt


def load_calendar() -> Dict[str, int]:
    """
    Load the calendar mapping from Cal.csv.

    Returns:
        Dictionary mapping date strings (YYYY-MM-DD) to daynum integers
    """
    calendar = {}

    with open(CAL_FILE, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter=';')
        next(reader)  # Skip header

        for row in reader:
            daynum_str = row[0]
            date_str = row[1]

            # Parse daynum (format: "2022,00" → 2022)
            daynum = int(float(daynum_str.replace(',', '.')))

            # Store mapping
            calendar[date_str] = daynum

    return calendar


def get_daynum_for_date(target_date: datetime, calendar: Optional[Dict[str, int]] = None) -> int:
    """
    Get the daynum for a specific date from the calendar.
    If the date is not in the calendar (weekend/holiday), returns the most recent prior daynum.

    Args:
        target_date: The date to look up
        calendar: Optional pre-loaded calendar dict (will load if None)

    Returns:
        Daynum (integer)

    Raises:
        ValueError: If no suitable daynum can be found
    """
    if calendar is None:
        calendar = load_calendar()

    # Try exact match first
    date_str = target_date.strftime("%Y-%m-%d")
    if date_str in calendar:
        return calendar[date_str]

    # No exact match - search backwards for up to 7 days (handle long weekends)
    from datetime import timedelta

    for days_back in range(1, 8):
        prev_date = target_date - timedelta(days=days_back)
        prev_date_str = prev_date.strftime("%Y-%m-%d")

        if prev_date_str in calendar:
            return calendar[prev_date_str]

    # Still no match - this shouldn't happen for recent dates
    raise ValueError(f"No daynum found for {date_str} or 7 days prior")


def get_daynum_from_a1_cell(a1_datetime_str: str) -> int:
    """
    Convert A1 cell datetime string to daynum.

    This is the main function to use for converting the timestamp in downloaded files
    to the corresponding daynum from Cal.csv.

    Args:
        a1_datetime_str: Datetime string from A1 cell
                        (e.g., "Thu Nov 06 2025 00:43:29 GMT+0100 (Central European Standard Time)")

    Returns:
        Daynum (integer)

    Raises:
        ValueError: If datetime cannot be parsed or daynum not found

    Example:
        >>> get_daynum_from_a1_cell("Thu Nov 06 2025 00:43:29 GMT+0100 ...")
        2018
    """
    # Parse the datetime string
    dt = parse_a1_datetime(a1_datetime_str)

    # Load calendar and lookup daynum
    calendar = load_calendar()
    daynum = get_daynum_for_date(dt, calendar)

    return daynum
