#!/usr/bin/env bash
# =============================================================================
# orchestrator.sh  —  PotSystem daily pipeline
#
# Steps:
#   1. Sync fresh CSVs from Google Drive  → RTBI_import/
#   2. Build corrected import-ready copy  → RTBI_corr/
#   3. Import all tables into PostgreSQL
#
# Logging:
#   - Attended (tty):    all output to screen only
#   - Unattended (cron): all output to logs/pipeline_YYYY-MM-DD.log
#
# Crontab entry (runs daily at 03:00):
#   0 3 * * * /home/sm/potentials/DB/code/pipeline/orchestrator.sh
# =============================================================================
set -euo pipefail

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE="$HOME/potentials/DB"
PIPELINE="$BASE/code/pipeline"
IMPORT_CSV="$BASE/code/import_csv"
LOGDIR="$BASE/logs"
LOGFILE="$LOGDIR/pipeline_$(date '+%Y-%m-%d').log"

CONDA_BASE="/home/sm/miniconda3"
CONDA_ENV="potsystem_env"

# ── tty-aware logging ─────────────────────────────────────────────────────────
# When running unattended (cron): all output goes to the daily log file.
# When running from a terminal: all output flows to screen as normal.
if [ ! -t 1 ]; then
    mkdir -p "$LOGDIR"
    exec > >(tee -a "$LOGFILE") 2>&1
fi

# ── Helpers ───────────────────────────────────────────────────────────────────
STEP=0
T_START=$(date +%s)

log()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')]  $*"; }
hdr()  { echo; echo "════════════════════════════════════════════════"; \
          echo "  Step $((++STEP)): $*"; \
          echo "════════════════════════════════════════════════"; }
ok()   { echo "[$(date '+%Y-%m-%d %H:%M:%S')]  ✓  $*"; }
fail() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')]  ✗  ERROR in step $STEP: $*"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')]  Pipeline aborted."
    exit 1
}

elapsed() {
    local secs=$(( $(date +%s) - T_START ))
    printf "%dm %02ds" $(( secs / 60 )) $(( secs % 60 ))
}

# ── Pipeline start ────────────────────────────────────────────────────────────
echo
echo "╔══════════════════════════════════════════════════╗"
echo "║        PotSystem  —  daily pipeline              ║"
echo "║        $(date '+%Y-%m-%d %H:%M:%S')                       ║"
echo "╚══════════════════════════════════════════════════╝"

# ── Step 1: Sync from Google Drive ───────────────────────────────────────────
hdr "Sync CSVs from Google Drive"

SYNC_SCRIPT="$PIPELINE/sync_dbold_from_gdrive.sh"
[[ -f "$SYNC_SCRIPT" ]] || fail "Script not found: $SYNC_SCRIPT"

bash "$SYNC_SCRIPT" || fail "sync_dbold_from_gdrive.sh exited with error"
ok "Sync complete"

# ── Step 2: Build corrected copy ─────────────────────────────────────────────
hdr "Prepare corrected import-ready copy"

PREP_SCRIPT="$PIPELINE/prepare_dbold_corr.sh"
[[ -f "$PREP_SCRIPT" ]] || fail "Script not found: $PREP_SCRIPT"

bash "$PREP_SCRIPT" || fail "prepare_dbold_corr.sh exited with error"
ok "Correction complete"

# ── Step 3: Import into PostgreSQL ───────────────────────────────────────────
hdr "Import all tables into PostgreSQL"

RUN_IMPORT="$IMPORT_CSV/run_import.py"
[[ -f "$RUN_IMPORT" ]] || fail "Script not found: $RUN_IMPORT"

# Activate conda — requires sourcing the init script explicitly,
# because cron does not run an interactive shell and conda is not on PATH.
log "Activating conda environment: $CONDA_ENV"
source "$CONDA_BASE/etc/profile.d/conda.sh" \
    || fail "Could not source conda init script at $CONDA_BASE"

conda activate "$CONDA_ENV" \
    || fail "Could not activate conda environment: $CONDA_ENV"

log "Python: $(python --version 2>&1)"

cd "$IMPORT_CSV"
python run_import.py || fail "run_import.py exited with error"
ok "Import complete"

# ── Summary ───────────────────────────────────────────────────────────────────
echo
echo "╔══════════════════════════════════════════════════╗"
echo "║  Pipeline finished successfully                  ║"
printf  "║  Total time: %-35s  ║\n" "$(elapsed)"
echo "╚══════════════════════════════════════════════════╝"
echo
