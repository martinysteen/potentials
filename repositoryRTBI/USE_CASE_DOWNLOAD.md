# Use Case: Download longi_sh3m.csv

## Scenario
User: "I need the `longi_sh3m.csv` file. How do I get it?"

## Solution

### Step 1: Get your API key
Contact sm@innovia.dk for an API key (one per user/app).

### Step 2: List available files
Check if the file exists:
```bash
curl -H "X-API-Key: YOUR_KEY" \
  https://innovia.dk/rtbi-api/files | grep longi_sh3m
```

Response:
```json
{
  "path": "Longi/longi_sh3m.csv",
  "size_bytes": 2457600,
  "modified": 1748433600.0
}
```

### Step 3: Download the file
```bash
curl -H "X-API-Key: YOUR_KEY" \
  https://innovia.dk/rtbi-api/files/Longi/longi_sh3m.csv \
  -o longi_sh3m.csv
```

The file is now in your current directory.

---

## If querying (not just downloading)

If you want data from the file without downloading the whole thing, you can query it:

```bash
# Get first 5 columns (daynums) for specific tickers
curl -H "X-API-Key: YOUR_KEY" \
  "https://innovia.dk/rtbi-api/data/Longi/longi_sh3m.csv?tickers=ABC;XYZ&daynums=first:5"
```

Response (JSON):
```json
[
  { "ticker": "ABC", "2156": 1039.95, "2155": 1042.18, "2154": 1053.27, "2153": 1045.05, "2152": 1034.98 },
  { "ticker": "XYZ", "2156": 75101.42, "2155": 75989.75, "2154": 77218.06, "2153": 75898.03, "2152": 77634.42 }
]
```

Then import to pandas, Excel, or your app directly.

---

## Excel example

**Download and open directly** (works with all Excel versions)
```bash
curl -H "X-API-Key: YOUR_KEY" \
  https://innovia.dk/rtbi-api/files/Longi/longi_sh3m.csv \
  -o longi_sh3m.csv
```
Then open `longi_sh3m.csv` in Excel (File → Open).

**Note:** The file uses semicolon separators and European decimal notation (1.234,56). Excel may prompt on import — select "Semicolon" as delimiter if prompted.

---

## Google Sheets example

**Option A: Manual copy-paste** (simplest, no setup)
1. In browser, query the API:
   ```
   https://innovia.dk/rtbi-api/data/Longi/longi_sh3m.csv?tickers=ABC;XYZ&daynums=first:10
   ```
2. Copy the JSON response
3. In Google Sheets, paste into a cell or use `Data` → `Import external data` (if available in your version)

**Option B: Google Apps Script** (auto-refresh daily)
In Google Sheets, go to `Extensions` → `Apps Script` and create a new project. Paste this:

```javascript
function fetchRTBIData() {
  const apiKey = "YOUR_API_KEY";
  const url = "https://innovia.dk/rtbi-api/data/Longi/longi_sh3m.csv?tickers=ABC;XYZ&daynums=first:10";
  
  const response = UrlFetchApp.fetch(url, {
    headers: { "X-API-Key": apiKey },
    muteHttpExceptions: true
  });
  
  if (response.getResponseCode() !== 200) {
    Logger.log("Error: " + response.getContentText());
    return;
  }
  
  const data = JSON.parse(response.getContentText());
  const sheet = SpreadsheetApp.getActiveSheet();
  
  // Clear existing data
  sheet.clearContents();
  
  // Write headers
  const headers = Object.keys(data[0]);
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  
  // Write rows
  const values = data.map(row => headers.map(h => row[h]));
  sheet.getRange(2, 1, values.length, headers.length).setValues(values);
  
  Logger.log("✓ Data loaded: " + data.length + " rows");
}
```

Then:
1. Click **Run** (authorizes the script on first run)
2. Check `Extensions` → `Triggers` (clock icon)
3. Click **Add Trigger** → set to run daily (or hourly)
4. Data auto-refreshes on schedule



```python
import requests
import pandas as pd

KEY = "YOUR_KEY"
BASE = "https://innovia.dk/rtbi-api"

# List files
files = requests.get(f"{BASE}/files", headers={"X-API-Key": KEY}).json()
print([f["path"] for f in files if "longi_sh3m" in f["path"]])

# Download
csv_bytes = requests.get(
    f"{BASE}/files/Longi/longi_sh3m.csv",
    headers={"X-API-Key": KEY}
).content
with open("longi_sh3m.csv", "wb") as f:
    f.write(csv_bytes)

# Or query directly to pandas
rows = requests.get(
    f"{BASE}/data/Longi/longi_sh3m.csv",
    headers={"X-API-Key": KEY},
    params={"tickers": "ABC;XYZ", "daynums": "first:10"}
).json()
df = pd.DataFrame(rows)
```
