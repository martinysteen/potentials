# repositoryRTBI — Claude Code Instructions

## Purpose
Mirrors `GoogleDrive:PotSystem/repositoryRTBI` to local `data/` on Ubuntu (`~/potentials/repositoryRTBI/data`), and exposes the CSV files via a REST API at `https://innovia.dk/rtbi-api/`.

## Environment
- Ubuntu server: `gandalf` (accessed via SSH on `innovia.dk:2222`)
- Python: conda environment `potsystem_env` — always use this, never pip/requirements.txt
- Reverse proxy: Caddy (config at `/etc/caddy/Caddyfile`)
- API service: systemd unit `rtbi-api.service`

## Directory structure
```
repositoryRTBI/
├── data/               # CSV files synced from Google Drive (do not edit manually)
├── api/
│   ├── main.py         # FastAPI + DuckDB application
│   ├── setup.sh        # conda install commands for dependencies
│   ├── .env            # RTBI_API_KEY (not committed)
│   └── .env.example    # key format reference
├── sync_rtbi.sh        # rclone sync script (run manually or via cron)
├── Caddyfile           # Caddy reverse proxy config (deployed to /etc/caddy/Caddyfile)
├── rtbi-api.service    # systemd service definition (deployed to /etc/systemd/system/)
└── nginx_rtbi.conf     # obsolete — replaced by Caddyfile
```

## Key commands (run on Ubuntu)
```bash
# Manual sync from Google Drive
bash ~/potentials/repositoryRTBI/sync_rtbi.sh

# API service
sudo systemctl status rtbi-api
sudo systemctl restart rtbi-api
sudo journalctl -u rtbi-api -f

# Caddy
sudo systemctl status caddy
sudo systemctl reload caddy
sudo journalctl -u caddy -f

# Test API
curl -H "X-API-Key: <key>" https://innovia.dk/rtbi-api/files
```

## Excluded folders (not synced from Drive)
- `Longi/exp/`
- `Longi/QA/`

## API endpoints
| Method | Path | Description |
|--------|------|-------------|
| GET | `/rtbi-api/files` | List all CSV files with metadata |
| GET | `/rtbi-api/files/{path}` | Download full CSV |
| GET | `/rtbi-api/data/{path}` | Query CSV via DuckDB (params: `limit`, `offset`, plus any column=value filters) |

All endpoints require header `X-API-Key: <key>`. Key is stored in `api/.env` on the server.

## Notes
- `rclone sync` mirrors source exactly — stale/deleted files are removed automatically, no pre-wipe needed
- Caddy handles SSL automatically via Let's Encrypt; certificate renews itself
- The systemd service uses the full conda env path: `/home/sm/miniconda3/envs/potsystem_env/bin/uvicorn`
