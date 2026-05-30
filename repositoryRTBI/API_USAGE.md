# RTBI Data API — Usage Guide

Base URL: `https://innovia.dk/rtbi-api`

All requests require the header:
```
X-API-Key: <key>
```

Contact sm@innovia.dk for a key.

---

## Endpoints

### List available files
```
GET /files
```
Returns all CSV files with path, size, and last-modified timestamp.

```bash
curl -H "X-API-Key: <key>" https://innovia.dk/rtbi-api/files
```
```json
[
  { "path": "PotDat.csv", "size_bytes": 4823040, "modified": 1748433600.0 },
  { "path": "Longi/across/PotDat_across.csv", "size_bytes": 921600, "modified": 1748433600.0 }
]
```

---

### Download a full CSV
```
GET /files/{path}
```
Returns the raw CSV file. Use the `path` value from `/files`.

```bash
curl -H "X-API-Key: <key>" https://innovia.dk/rtbi-api/files/PotDat.csv -o PotDat.csv
```

---

### Query a CSV (ticker/daynum matrix)
```
GET /data/{path}?tickers=T1;T2;T3&daynums=...
```
Returns JSON rows. The CSV must have tickers in the first column (renamed to `ticker`) and integer daynum columns. If the second column is not an integer, returns 400.

**Parameters:**

| Parameter | Example | Meaning |
|-----------|---------|---------|
| `tickers` | `tickers=^AEX;^BTC` | Return these tickers (rows); semicolon-separated |
| `daynums` | `daynums=first` | Return only the first daynum column |
| | `daynums=first:10` | Return first 10 daynum columns |
| | `daynums=1000:2000` | Return daynums in that integer range (inclusive) |
| | `daynums=all` | Return all daynum columns |

Both can combine: `?tickers=^AEX&daynums=first:20`

```bash
# Get first daynum for all tickers
curl -H "X-API-Key: <key>" "https://innovia.dk/rtbi-api/data/PotDat.csv?daynums=first"

# Get multiple tickers, daynum range
curl -H "X-API-Key: <key>" "https://innovia.dk/rtbi-api/data/PotDat.csv?tickers=^AEX;^BTC;^FCHI&daynums=2000:2020"

# Get specific tickers, first 5 daynums
curl -H "X-API-Key: <key>" "https://innovia.dk/rtbi-api/data/PotDat.csv?tickers=^AEX&daynums=first:5"
```

Returns:
```json
[
  { "ticker": "^AEX", "2156": 1039.95, "2155": 1042.18, "2154": 1053.27 },
  { "ticker": "^BTC", "2156": 75101.42, "2155": 75989.75, "2154": 77218.06 }
]
```

**Note:** CSVs use semicolon (`;`) as field separator and comma (`,`) as decimal separator (European format). Numeric values are automatically parsed.

---

## Interactive docs (Swagger UI)
`https://innovia.dk/rtbi-api/docs`

Try all endpoints directly in the browser. Click **Authorize** and enter your API key.

---

## Using from Python

```python
import requests

BASE = "https://innovia.dk/rtbi-api"
HEADERS = {"X-API-Key": "<key>"}

# List files
files = requests.get(f"{BASE}/files", headers=HEADERS).json()

# Download CSV
csv_bytes = requests.get(f"{BASE}/files/PotDat.csv", headers=HEADERS).content

# Query with pandas
import pandas as pd
rows = requests.get(
    f"{BASE}/data/PotDat.csv",
    headers=HEADERS,
    params={"daynums": "first:10"},
).json()
df = pd.DataFrame(rows)
```

## Using from Claude / AI agents

Point the agent at the OpenAPI spec:
```
https://innovia.dk/rtbi-api/openapi.json
```
The spec describes all endpoints, parameters, and response schemas, allowing the agent to discover and call the API autonomously.
