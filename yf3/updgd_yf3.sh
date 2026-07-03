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
SOURCE=/home/sm/potentials/yf3/app/output_stacked
RECEIVER=GoogleDrive:PotSystem/repositoryRTBI/Yfinance/
# Verify source directory exists
if [ ! -d "$SOURCE" ]; then
    echo "ERROR: Source directory does not exist: $SOURCE"
    exit 1
fi

# Echo the copy operation
echo "Copying from: $SOURCE"
echo "Copying to: $RECEIVER"

# Run the rclone command
rclone copy "$SOURCE" "$RECEIVER" --update --verbose --drive-skip-gdocs --exclude ".stack_ledger.json" --exclude ".gitignore"

RCLONE_EXIT_CODE=$?
echo "rclone exit code: $RCLONE_EXIT_CODE"

if [ $RCLONE_EXIT_CODE -eq 0 ]; then
    echo "SUCCESS: Files copied successfully"
else
    echo "ERROR: rclone failed with exit code: $RCLONE_EXIT_CODE"
fi

echo "=== updgd_yf3.sh END: $(date) ==="

# Display log file when on TTY
if [ -t 3 ]; then
    exec >&3
    echo "** Content of log: $LOGFILE"
    cat "$LOGFILE"
fi

exit $RCLONE_EXIT_CODE
