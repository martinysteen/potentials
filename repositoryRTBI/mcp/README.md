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
| `get_series` | Time series for tickers, as dates oldest-first; `freq` D/W/M, `transform` level/pct_change; `tickers=["*"]` = every row. Up to 6000 values inline; more → newest dates inline + `download_url` for the complete CSV. `download=true` = file only: the link, the totals and a 10-date × 10-ticker preview, not the data (scripts/agents) |
| `plot_series` | Same as `get_series`, returns a PNG chart plus the numbers |
| `get_table` | Rows from Stamdata, potrank2, Google, StrategicStocks, across, Yfinance, StockData2_stacked; up to `limit` (≤300) rows inline, the complete selection as `download_url` when there are more. `download=true` = file only, with a 10-row preview |
| `create_api_key` | Optional personal key for scripts (links open without it), shown once with copy-paste store commands; calling it again replaces the old one |
| `tunnel_report` | Price-tunnel report for 1-200 tickers and an end date: CSV + PDF + PNG in a folder, returns links (valid 7 days) and the table |
| `tunnel_history` | Search the full tunnel history (every trading day x every ticker, ~0.9M rows): filters across all tickers and dates, then up to 500 rows or a count+mean summary per date/month/ticker/status; always reports `rows_matched` |

Resource `potentials://conventions` explains daynums, seven-pack horizons and trailing vs forward
gains. Monthly/weekly results flag `last_period_partial` when the newest point is to-date.

### tunnel_report
Arguments: `tickers` (required), `end_date` (YYYY-MM-DD, default newest day), `name` (optional label
in the link). Example prompts:
> Make a tunnel report for MSFT, MU and NVDA.
> Tunnels for the tickers in semiconductors, as of 2026-09-30.

Reads from the answer: `close_pos` 0 = on the lower line, 1 = on the upper line, outside 0..1 = the
close has left the tunnel; `slope20_pct` = % gain per 20 trading days along the lines. Nightly
history of every ticker and day: the `tunnel_history` tool (file `Tunnel/history/tunnels_history_LB100.csv` on Drive).
Details: `tunnel/CLAUDE.md`.

## Access
Google sign-in, then an email allowlist (`RTBI_MCP_ALLOWED_EMAILS` in `.env`). To add a person:
1. Add their Google email to `RTBI_MCP_ALLOWED_EMAILS` in `~/potentials/repositoryRTBI/mcp/.env`.
2. Add the same email as a Test user: Google Cloud console → Google Auth Platform → Audience.
3. `sudo systemctl restart rtbi-mcp`.

Refused users and every tool call (with email) are logged: `sudo journalctl -u rtbi-mcp -f`.

### Downloads and API keys (2026-11-07)
`get_series`, `get_table` and `tunnel_history` hand over the COMPLETE result as a CSV
(`https://mcp.innovia.dk/dl/<token>/<name>.csv`, standard comma/point, deleted after 24 h).
Each link is **tied to the member whose tool call made it** (their email in the export folder's
`.owner` file, never in the URL), and the route (`server.py::download`) serves it two ways
(2026-11-07, links used to need a key):
- **Link alone** (a click in a browser): served while the link's owner is on the allowlist.
- **With a key** (`Authorization: Bearer <key>` or `X-API-Key`), for scripts and agents: served
  while the key's owner is on the allowlist. A wrong key is refused, never ignored. A link with no
  owner (made without a signed-in caller) needs a key.

The allowlist is read **as `.env` says right now** on every fetch (no restart needed); each fetch
is logged `download <email> via=link|key <file> <bytes> ip=…`. Trade-off: a leaked link works for
whoever holds it until it expires (24 h) or its owner is removed; the data is read-only.

- **Member gets a key** (only for scripts; chat users never need one): asks for `create_api_key`.
  The reply carries one-line `store_it` commands (Linux / macOS / Windows) that put it in
  `$POTENTIALS_KEY`. Only the sha256 is
  stored (`~/.config/potentials/mcp_keys.json`, outside the repo); a lost key is replaced, not recovered.
- **Member leaves:** delete their email from `RTBI_MCP_ALLOWED_EMAILS` in `.env` (every link they ever made
  and their key die at once), then `sudo systemctl restart rtbi-mcp` to end their MCP
  access, and `python exports.py revoke <email>` to drop the key. `python exports.py list` shows who has one.
- Not covered: data a member already downloaded; `tunnel_report` links (PDF/PNG folders under
  `innovia.dk/tunnel-reports`) are still public bearer links, 7 days.
- Exports live in `~/.cache/potentials/mcp-exports/` (not served by Caddy).

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
cd ~/potentials/repositoryRTBI/mcp && python smoke_test.py   # 24 checks, in-memory, no auth
```
Without `GOOGLE_CLIENT_ID` in `.env` the server refuses to start. It never serves unauthenticated
by accident. OAuth client registrations persist under `~/.fastmcp/`, so restarts don't log
clients out. Changing `RTBI_MCP_JWT_KEY` does.

## Files
- `server.py` — tools, auth, allowlist middleware, HTTP entry point
- `catalog.py` — dataset discovery, descriptions, cached loading through the PotDat
  gatekeeper (`shared/app/code/potdat_gatekeeper.py`: `admit()` for PotDat, `looks_intact()`
  for the rest), and `carried_newest()` behind get_series' `provisional_newest` field
- `exports.py` — CSV exports, the API-key store, `list` / `revoke` admin commands
- `smoke_test.py` — every tool + error paths + allowlist + keys + download route; monthly gain checked against a hand
  computation from PotDat.csv
- `rtbi-mcp.service` — systemd unit (deployed to `/etc/systemd/system/`)
- `.env.example` — what `.env` needs
