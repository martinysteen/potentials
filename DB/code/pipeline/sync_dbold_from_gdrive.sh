#!/bin/bash
# =============================================================================
# sync_dbold_from_gdrive.sh — Pull CSV files from Google Drive into DB_old
# =============================================================================
# Mirrors selected Google Drive folders into ~/potentials/DB_old/
# preserving subfolder structure.
#
# Output behaviour:
#   Interactive (TTY) : all output goes to screen only
#   Cron              : all output goes to log file only
#
# Usage:
#   bash sync_dbold_from_gdrive.sh
#
# To add more source folders later, add entries to the SOURCES array below.
# =============================================================================

LOGFILE=/home/sm/potentials/DB/logs/sync_gdrive.log
DB_OLD=/home/sm/potentials/DB/RTBI_import

# --- Route output: screen when interactive, log when cron -------------------
if [ -t 1 ]; then
    # Running interactively — output goes to screen
    echo "Running interactively — output to screen"
else
    # Running under cron — redirect all output to log
    exec > >(tee -a "$LOGFILE") 2>&1
fi

echo "=== sync_dbold_from_gdrive.sh START: $(date) ==="

# --- Source folders to sync --------------------------------------------------
# Format: "GDrive_path|local_subfolder_name"
# Add new entries here as more source folders are needed.
declare -a SOURCES=(
    "GoogleDrive:/PotSystem/repositoryRTBI|repositoryRTBI"
    "GoogleDrive:/PotSystem/repositoryRTBI/Yfinance|repositoryRTBI/Yfinance"
    "GoogleDrive:/PotSystem/repositoryRTBI/Longi|repositoryRTBI/Longi"
    "GoogleDrive:/PotSystem/repositoryRTBI/Longi/output_grp|repositoryRTBI/Longi/output_grp"
)

# --- Verify DB_old exists ----------------------------------------------------
if [ ! -d "$DB_OLD" ]; then
    echo "ERROR: DB_old directory does not exist: $DB_OLD"
    exit 1
fi

# --- Track overall result ----------------------------------------------------
OVERALL_EXIT=0

# --- Loop across all source folders ------------------------------------------
for ENTRY in "${SOURCES[@]}"; do
    GDRIVE_PATH="${ENTRY%%|*}"
    LOCAL_SUBDIR="${ENTRY##*|}"
    LOCAL_PATH="${DB_OLD}/${LOCAL_SUBDIR}"

    echo "---"
    echo "SOURCE : $GDRIVE_PATH"
    echo "DEST   : $LOCAL_PATH"

    mkdir -p "$LOCAL_PATH"

    rclone copy "$GDRIVE_PATH" "$LOCAL_PATH" \
    --update \
    --verbose \
    --drive-skip-gdocs \
    --include "*.csv" \
    --max-depth 1
    EXIT_CODE=$?
    echo "rclone exit code: $EXIT_CODE"

    if [ $EXIT_CODE -eq 0 ]; then
        echo "SUCCESS: $GDRIVE_PATH"
    else
        echo "ERROR: rclone failed for $GDRIVE_PATH (exit code $EXIT_CODE)"
        OVERALL_EXIT=$EXIT_CODE
    fi
done

echo "---"
echo "=== sync_dbold_from_gdrive.sh END: $(date) ==="

exit $OVERALL_EXIT