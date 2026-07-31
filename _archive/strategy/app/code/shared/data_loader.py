import pandas as pd
from functools import lru_cache
from shared.config import DATA_LONGI, POTDAT_PATH, STAMDATA_PATH, CAL_PATH


@lru_cache(maxsize=None)
def load_longi(filename: str) -> pd.DataFrame:
    """Load a Longi matrix CSV. Rows=tickers, cols=daynum strings, newest-left."""
    return pd.read_csv(DATA_LONGI / filename, sep=";", decimal=",", index_col=0)


@lru_cache(maxsize=None)
def load_potdat() -> pd.DataFrame:
    """Load PotDat.csv. Rows=tickers, cols=daynum strings, newest-left."""
    return pd.read_csv(POTDAT_PATH, sep=";", decimal=",", index_col=0)


@lru_cache(maxsize=None)
def load_stamdata() -> pd.DataFrame:
    """Load Stamdata.csv. Rows=tickers, cols=attributes (Name, Sector, GICS, Sector2, Zone, ...)."""
    return pd.read_csv(STAMDATA_PATH, sep=";", decimal=",", index_col=0)


@lru_cache(maxsize=None)
def _load_cal() -> pd.DataFrame:
    # Index is Daynum as float (European decimal in source: "2055,00" → 2055.0)
    return pd.read_csv(CAL_PATH, sep=";", decimal=",", index_col=0)


def daynum_to_date(daynum: int) -> str:
    """Convert a daynum integer to a date string via Cal.csv."""
    try:
        cal = _load_cal()
        key = float(daynum)
        if key in cal.index:
            return str(cal.loc[key].iloc[0])
    except Exception:
        pass
    return f"dn{daynum}"
