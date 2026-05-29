import os
from pathlib import Path
from typing import Optional

import pandas as pd
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

load_dotenv(Path(__file__).parent / ".env")

API_KEY = os.environ["RTBI_API_KEY"]
DATA_DIR = Path("/home/sm/potentials/repositoryRTBI/data").resolve()

app = FastAPI(title="RTBI Data API", root_path="/rtbi-api")


def _require_key(request: Request):
    key = request.headers.get("X-API-Key", "")
    if key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")


def _safe_path(rel: str) -> Path:
    """Resolve path and guard against traversal outside DATA_DIR."""
    resolved = (DATA_DIR / rel).resolve()
    if not str(resolved).startswith(str(DATA_DIR)):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not resolved.exists():
        raise HTTPException(status_code=404, detail="File not found")
    if resolved.suffix.lower() != ".csv":
        raise HTTPException(status_code=400, detail="Only CSV files are served")
    return resolved


def _select_daynums(daynum_cols: list[str], daynum_ints: list[int], daynums: str) -> list[str]:
    if daynums == "all":
        return daynum_cols
    if daynums == "first":
        return daynum_cols[:1]
    if daynums.startswith("first:"):
        try:
            n = int(daynums.split(":", 1)[1])
        except ValueError:
            raise HTTPException(400, detail=f"Invalid daynums: '{daynums}'. Expected 'first:N'.")
        return daynum_cols[:n]
    if ":" in daynums:
        try:
            lo, hi = map(int, daynums.split(":", 1))
        except ValueError:
            raise HTTPException(400, detail=f"Invalid daynums: '{daynums}'. Expected 'N1:N2'.")
        selected = [c for c, d in zip(daynum_cols, daynum_ints) if lo <= d <= hi]
        if not selected:
            raise HTTPException(400, detail=f"No daynum columns in range {lo}:{hi}.")
        return selected
    raise HTTPException(400, detail=f"Invalid daynums: '{daynums}'. Use 'first', 'first:N', 'N1:N2', or 'all'.")


@app.get("/files")
def list_files(_=Depends(_require_key)):
    """List all available CSV files with size and modification time."""
    result = []
    for f in sorted(DATA_DIR.rglob("*.csv")):
        stat = f.stat()
        result.append({
            "path": str(f.relative_to(DATA_DIR)).replace("\\", "/"),
            "size_bytes": stat.st_size,
            "modified": stat.st_mtime,
        })
    return result


@app.get("/files/{path:path}")
def download_file(path: str, _=Depends(_require_key)):
    """Download a full CSV file."""
    resolved = _safe_path(path)
    return FileResponse(resolved, media_type="text/csv", filename=resolved.name)


@app.get("/data/{path:path}")
def query_data(
    path: str,
    tickers: Optional[str] = None,
    daynums: Optional[str] = None,
    _=Depends(_require_key),
):
    """
    Query a ticker/daynum matrix CSV.
    - tickers: semicolon-separated row labels, e.g. tickers=ABC;DEF
    - daynums: 'first', 'first:N', 'N1:N2' (inclusive range), or 'all'
    Returns 400 if the file does not follow the ticker/daynum structure
    (detected by checking whether the second column header is an integer).
    """
    resolved = _safe_path(path)
    df = pd.read_csv(resolved, sep=";", decimal=",")

    # Rename first column to 'ticker' regardless of its original header
    df = df.rename(columns={df.columns[0]: "ticker"})

    if len(df.columns) < 2:
        raise HTTPException(400, detail="File has fewer than 2 columns; use /files/ to download.")

    try:
        int(df.columns[1])
    except (ValueError, TypeError):
        raise HTTPException(
            400,
            detail=(
                f"Query not supported: second column header '{df.columns[1]}' is not a daynum integer. "
                f"Use /files/{path} to download the full file."
            ),
        )

    daynum_cols = list(df.columns[1:])
    daynum_ints = [int(c) for c in daynum_cols]

    if tickers:
        ticker_list = [t.strip() for t in tickers.split(";")]
        df = df[df["ticker"].isin(ticker_list)]

    if daynums:
        selected = _select_daynums(daynum_cols, daynum_ints, daynums)
        df = df[["ticker"] + selected]

    return df.to_dict(orient="records")
