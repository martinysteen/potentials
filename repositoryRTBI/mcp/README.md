# rtbi-mcp — Potentials data for LLM chats and agents

An MCP server at **`https://mcp.innovia.dk/mcp`** that lets Claude, ChatGPT, Cowork, Hermes or
any other MCP client query the Potentials repository: prices, longi factors, Stamdata, potrank,
today's StrategicStocks, yFinance. Read-only; reads the local mirror `repositoryRTBI/data/`.

Example prompt in any connected chat:
> Use Potentials data from longi_price for MSFT and MU and plot monthly gain since October 2025.

## Tools
| Tool | What it does |
|---|---|
| `list_datasets` | Every dataset with a one-line meaning; `matrix` = time series, `table` = rows |
| `search_tickers` | Company name / sector / GICS / country → ticker (from Stamdata) |
| `get_series` | Time series for tickers, as dates oldest-first; `freq` D/W/M, `transform` level/pct_change |
| `plot_series` | Same as `get_series`, returns a PNG chart plus the numbers |
| `get_table` | Rows from Stamdata, potrank2, Google, StrategicStocks, across, Yfinance, StockData2_stacked |

Resource `potentials://conventions` explains daynums, seven-pack horizons and trailing vs forward
gains. Monthly/weekly results flag `last_period_partial` when the newest point is to-date.

## Access
Google sign-in, then an email allowlist (`RTBI_MCP_ALLOWED_EMAILS` in `.env`). To add a person:
1. Add their Google email to `RTBI_MCP_ALLOWED_EMAILS` in `~/potentials/repositoryRTBI/mcp/.env`.
2. Add the same email as a Test user: Google Cloud console → Google Auth Platform → Audience.
3. `sudo systemctl restart rtbi-mcp`.

Refused users and every tool call (with email) are logged: `sudo journalctl -u rtbi-mcp -f`.

## Connecting a client
- **claude.ai / Claude Desktop / Cowork:** Settings → Connectors → Add custom connector →
  URL `https://mcp.innovia.dk/mcp` → sign in with Google.
- **ChatGPT:** Settings → Apps & Connectors → Advanced → Developer mode on → Create →
  URL `https://mcp.innovia.dk/mcp`, authentication OAuth → sign in with Google.
- **Claude Code:** `claude mcp add --transport http potentials https://mcp.innovia.dk/mcp`, then
  `/mcp` to sign in.
- **Hermes / other agents:** add a remote (streamable HTTP) MCP server with the URL above; it
  uses the same OAuth sign-in.

## Operations (on the server)
```bash
sudo systemctl status rtbi-mcp          # service, port 127.0.0.1:8766
sudo systemctl restart rtbi-mcp         # after editing .env or code
cd ~/potentials/repositoryRTBI/mcp && python smoke_test.py   # 23 checks, in-memory, no auth
```
Without `GOOGLE_CLIENT_ID` in `.env` the server refuses to start. It never serves unauthenticated
by accident. OAuth client registrations persist under `~/.fastmcp/`, so restarts don't log
clients out. Changing `RTBI_MCP_JWT_KEY` does.

## Files
- `server.py` — tools, auth, allowlist middleware, HTTP entry point
- `catalog.py` — dataset discovery, descriptions, cached loading with the mid-write guard
  from `shared/app/code/repository.py`
- `smoke_test.py` — every tool + error paths + allowlist; monthly gain checked against a hand
  computation from PotDat.csv
- `rtbi-mcp.service` — systemd unit (deployed to `/etc/systemd/system/`)
- `.env.example` — what `.env` needs
