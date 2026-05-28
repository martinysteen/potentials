#!/bin/bash
# Testing from ~/potentials/yf3? Use: bash updgd_yf3.sh

LOGFILE=/home/sm/updgd_yf3.log

# Delete log file if it exists
#if [ -f "$LOGFILE" ]; then
#    rm "$LOGFILE"
#fi

exec 3>&1
exec >> $LOGFILE 2>&1

echo "=== updgd_yf3.sh START: $(date) ==="

# Set source and destination
SOURCE=/home/sm/potentials/yf3/app/output
RECEIVER=GoogleDrive:PotSystem/PotApps/Yfinance/output

SOURCE_STACKED=/home/sm/potentials/yf3/app/output_stacked
RECEIVER_STACKED=GoogleDrive:/PotSystem/repositoryRTBI/Yfinance

# Verify source directories exist
if [ ! -d "$SOURCE" ]; then
    echo "ERROR: Source directory does not exist: $SOURCE"
    exit 1
fi

if [ ! -d "$SOURCE_STACKED" ]; then
    echo "ERROR: Source directory does not exist: $SOURCE_STACKED"
    exit 1
fi

# --- Copy output ---
echo "Copying from: $SOURCE"
echo "Copying to: $RECEIVER"

rclone copy "$SOURCE" "$RECEIVER" --update --verbose --drive-skip-gdocs

RCLONE_EXIT_CODE=$?
echo "rclone exit code: $RCLONE_EXIT_CODE"

if [ $RCLONE_EXIT_CODE -eq 0 ]; then
    echo "SUCCESS: Files copied successfully"
else
    echo "ERROR: rclone failed with exit code: $RCLONE_EXIT_CODE"
fi

# --- Copy output_stacked ---
echo "Copying from: $SOURCE_STACKED"
echo "Copying to: $RECEIVER_STACKED"

rclone copy "$SOURCE_STACKED" "$RECEIVER_STACKED" --update --verbose --drive-skip-gdocs

RCLONE_EXIT_CODE_STACKED=$?
echo "rclone exit code (stacked): $RCLONE_EXIT_CODE_STACKED"

if [ $RCLONE_EXIT_CODE_STACKED -eq 0 ]; then
    echo "SUCCESS: Stacked files copied successfully"
else
    echo "ERROR: rclone (stacked) failed with exit code: $RCLONE_EXIT_CODE_STACKED"
fi

echo "=== updgd_yf3.sh END: $(date) ==="

# Display log file when on TTY
if [ -t 3 ]; then
    exec >&3
    echo "** Content of log: $LOGFILE"
    cat "$LOGFILE"
fi

# Exit non-zero if either transfer failed
if [ $RCLONE_EXIT_CODE -ne 0 ]; then
    exit $RCLONE_EXIT_CODE
fi
exit $RCLONE_EXIT_CODE_STACKED