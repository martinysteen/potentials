# repositoryRTBI — Claude Code Instructions

## Purpose
Mirrors `GoogleDrive:PotSystem/repositoryRTBI` to local `data/` on Ubuntu (`~/potentials/repositoryRTBI/data`), and exposes the CSV files via a REST API at `https://innovia.dk/rtbi-api/`.

## The three-layer contract (read this before changing any sync)
`data/` is the authoritative copy on this machine. Three layers, and nothing crosses:

| Layer | Who | Does |
|-------|-----|------|
| Producers | `longi`, `group_conformity`, … | compute, then publish **their own namespace** to Drive. Never pull, never trigger anything downstream. |
| Mirror | this project (`sync_rtbi.sh`) | pulls Drive → `data/` **on its own cron**, for its own reasons |
| Consumers | `strategy_grp`, and every family's `fetch_input.sh` | read `data/`. **Never Google Drive directly.** |

A producer must not call `sync_rtbi.sh` — both `start_longi.sh` and `run_conf.sh` used to,
which made every family's timing depend on every other family's. If consumers need fresher
data, this project changes **its own** cron; that is not a producer's business.

### Where the ownership list is

**`~/potentials/shared/app/code/repository.py` — the `OWNERS` dict, `owns=(...)` on each family.**
That tuple of filename patterns *is* the contract; there is no copy of it in any `.md` file, on
purpose (a second copy is a copy that goes stale). To read it without opening the file:

```bash
python3 ~/potentials/shared/app/code/repository.py check   # every owner, both guards
```

**A new output file must be added there or it is never published** — see the full producer-side
checklist in [../longi/CLAUDE.md](../longi/CLAUDE.md) ("Adding New Modules to Pipeline", step 4),
and the root [../CLAUDE.md](../CLAUDE.md) for the second list every *consumer* keeps.

Ownership, publishing and fetching all live in that one module. Each family declares what it
**owns** — never excludes of other families' files — and its `rclone sync` is scoped to that
namespace, so it cleans up its own retired outputs and is blind to everything else in the folder. The old
exclude-based arrangement failed silently: longi's uploader excluded `longi_conf_*.csv` but
nobody added `longi_sectorbeta_*.csv`, so those two files were deleted at :20 and restored
at :31, every hour, for weeks.

### mirror_status.json
`sync_rtbi.sh` writes `~/potentials/repositoryRTBI/mirror_status.json` after every run —
`{"finished": ISO8601, "exit_code": N, "files": N}` — including on failure. Consumers gate on
it (`repository.py fetch` refuses a mirror that failed, or is over 90 min stale, unless
`--stale-ok`). It lives **outside** `data/` on purpose: anything inside `data/` that Drive
does not have is deleted by the next sync.

### Cron
`:07`, `:37`, `:55` — three ticks. `:55` exists so `group_conformity`'s `:45` output reaches
the mirror in the hour it was computed. Full chain:
`longi :15 → publish ~:17 → mirror :37 → group_conformity :45 → publish ~:47 → mirror :55`.

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
│   ├── main.py         # FastAPI + pandas ticker/daynum query application
│   ├── setup.sh        # conda install commands for dependencies
│   ├── .env            # RTBI_API_KEY (not committed)
│   └── .env.example    # key format reference
├── sync_rtbi.sh        # rclone sync script (run manually or via cron)
├── Caddyfile           # Caddy reverse proxy config (deployed to /etc/caddy/Caddyfile)
├── rtbi-api.service    # systemd service definition (deployed to /etc/systemd/system/)
```

## Key commands (run on Ubuntu)
```bash
# Manual sync from Google Drive
bash ~/potentials/repositoryRTBI/sync_rtbi.sh

# Ad-hoc publish / fetch for one family (see shared/app/code/repository.py)
python3 ~/potentials/shared/app/code/repository.py check              # both guards, all owners
python3 ~/potentials/shared/app/code/repository.py publish longi --dry-run
python3 ~/potentials/shared/app/code/repository.py publish group_conformity
python3 ~/potentials/shared/app/code/repository.py fetch longi        # --stale-ok to override
# equivalent, from the family's own wrapper (activates conda first):
bash ~/potentials/longi/upload_output.sh

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

# Run smoke tests
bash ~/potentials/repositoryRTBI/api/test_api.sh <key>
```

## Excluded folders (not synced from Drive)
- `Longi/exp/`
- `Longi/QA/`

## API endpoints
| Method | Path | Description |
|--------|------|-------------|
| GET | `/rtbi-api/files` | List all CSV files with metadata |
| GET | `/rtbi-api/files/{path}` | Download full CSV |
| GET | `/rtbi-api/data/{path}` | Query ticker/daynum matrix CSVs as JSON (params: `tickers`, `daynums`) |

All endpoints require header `X-API-Key: <key>`. Key is stored in `api/.env` on the server.

## Notes
- `rclone sync` mirrors source exactly — stale/deleted files are removed automatically, no pre-wipe needed
- Caddy handles SSL automatically via Let's Encrypt; certificate renews itself
- The systemd service uses the full conda env path: `/home/sm/miniconda3/envs/potsystem_env/bin/uvicorn`
