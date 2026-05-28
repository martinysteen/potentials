#!/usr/bin/env bash
# =============================================================================
# prepare_dbold_corr.sh  —  Build import-ready corrected copy of RTBI_import
#
# Rebuilds RTBI_corr from scratch on every run:
#   1. Wipes and recreates ~/potentials/DB/RTBI_corr/
#   2. Copies everything from ~/potentials/DB/RTBI_import/
#   3. Removes files not imported into PostgreSQL
#   4. Renames files to match uniform naming conventions
#
# Logging: screen only when run from a terminal (tty), log file when unattended.
# =============================================================================
set -euo pipefail

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE="$HOME/potentials/DB"
SRC="$BASE/RTBI_import"
DST="$BASE/RTBI_corr"
LOGFILE="$BASE/logs/prepare_dbold_corr.log"

# ── tty-aware logging ─────────────────────────────────────────────────────────
if [ ! -t 1 ]; then
    mkdir -p "$(dirname "$LOGFILE")"
    exec > >(tee -a "$LOGFILE") 2>&1
fi

# ── Helpers ───────────────────────────────────────────────────────────────────
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')]  $*"; }

# ── Main ──────────────────────────────────────────────────────────────────────
log "Starting prepare_dbold_corr.sh"
log "Source : $SRC"
log "Target : $DST"

# Verify source exists
if [[ ! -d "$SRC" ]]; then
    log "ERROR: Source directory not found: $SRC"
    exit 1
fi

# Rebuild RTBI_corr from scratch
log "Wiping and recreating $DST"
rm -rf "$DST"
cp -r "$SRC" "$DST"
log "Copy complete"

# ── Removals ──────────────────────────────────────────────────────────────────
# Files not imported into PostgreSQL or not yet numerically coded

REMOVE=(
    "PotNdx.csv"             # not imported into PostgreSQL
    "PotRank.csv"            # not imported into PostgreSQL
    "Longi/longi_macd_Z.csv" # qualitative data — not yet coded numerically
    "Longi/longi_uptrend.csv" # qualitative data, no longer in use
)

log "Applying removals..."
for f in "${REMOVE[@]}"; do
    target="$DST/$f"
    if [[ -f "$target" ]]; then
        rm "$target"
        log "  Removed : $f"
    else
        log "  Skip (not found) : $f"
    fi
done

# ── Renames ───────────────────────────────────────────────────────────────────
# Enforce uniform longi_ prefix so glob patterns work reliably

declare -A RENAMES=(
    ["Longi/future_gain20d.csv"]="Longi/longi_futgain20d.csv"
    ["Longi/future_gain50d.csv"]="Longi/longi_futgain50d.csv"
)

log "Applying renames..."
for old in "${!RENAMES[@]}"; do
    new="${RENAMES[$old]}"
    src_file="$DST/$old"
    dst_file="$DST/$new"
    if [[ -f "$src_file" ]]; then
        mv "$src_file" "$dst_file"
        log "  Renamed : $old  →  $new"
    else
        log "  Skip (not found) : $old"
    fi
done

# ── Summary ───────────────────────────────────────────────────────────────────
CSV_COUNT=$(find "$DST" -name "*.csv" | wc -l)
log "Done. $CSV_COUNT CSV files ready in $DST"
