#!/bin/bash
# Testing from ~/potentials/longi? Use: bash updgd_longi.sh

LOGFILE=/home/sm/updgd_longi.log

# Delete log file if it exists
#if [ -f "$LOGFILE" ]; then
#    rm "$LOGFILE"
#fi

exec 3>&1
exec >> $LOGFILE 2>&1

echo "=== updgd_longi.sh START: $(date) ==="

# Set source and destination
SOURCE=/home/sm/potentials/longi/app/output
RECEIVER=GoogleDrive:PotSystem/PotApps/Longi/output

# Verify source directory exists
if [ ! -d "$SOURCE" ]; then
    echo "ERROR: Source directory does not exist: $SOURCE"
    exit 1
fi

# Echo the copy operation
echo "Copying from: $SOURCE"
echo "Copying to: $RECEIVER"

# Run the rclone command
rclone copy "$SOURCE" "$RECEIVER" --update --verbose --drive-skip-gdocs

RCLONE_EXIT_CODE=$?
echo "rclone exit code: $RCLONE_EXIT_CODE"

if [ $RCLONE_EXIT_CODE -eq 0 ]; then
    echo "SUCCESS: Files copied successfully"
else
    echo "ERROR: rclone failed with exit code: $RCLONE_EXIT_CODE"
fi

echo "=== updgd_longi.sh END: $(date) ==="

# Display log file when on TTY
if [ -t 3 ]; then
    exec >&3
    echo "** Content of log: $LOGFILE"
    cat "$LOGFILE"
fi

exit $RCLONE_EXIT_CODE
