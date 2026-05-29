# Project Context — repositoryRTBI API

Last updated: 2026-05-28

## Goal
Make Potentials CSV files (mirrored from Google Drive) accessible to external agents and users via a REST API, without requiring Google Drive auth or DNS changes.

## Status: ✅ Complete and operational (2026-05-28)

All endpoints tested and working:
- [x] Caddy with valid SSL running
- [x] API smoke tests passing
- [x] Query endpoint working with ticker/daynum structure
- [x] Download endpoint working
- [x] Hourly cron job active
- [x] Semicolon separator and decimal comma parsing working

## Setup steps completed on Ubuntu (for reference)
1. Installed Caddy from official repo (`dl.cloudsmith.io/public/caddy/stable`)
2. Copied `Caddyfile` to `/etc/caddy/Caddyfile`, reloaded caddy
3. Ran `api/setup.sh` to install fastapi, uvicorn, python-dotenv, and pandas into potsystem_env
4. Created `api/.env` with `RTBI_API_KEY=<key>`
5. Copied `rtbi-api.service` to `/etc/systemd/system/`, enabled and started it
6. Opened ports 80+443 on router

## Access
- API base URL: `https://innovia.dk/rtbi-api/`
- Interactive docs: `https://innovia.dk/rtbi-api/docs`
- SSH: `ssh -p 2222 sm@innovia.dk`
