#!/bin/bash
# Fetch inputdata from Google Drive to ../input


echo "=== Fetch input data START: $(date) ==="

# Set source and destination
SOURCE_1=GoogleDrive:PotSystem/repositoryRTBI/
SOURCE_2=GoogleDrive:PotSystem/repositoryRTBI/Longi/
RECEIVER=/home/sm/potentials/correlation/input/

# Clear destination folder
echo "Clearing destination folder: $RECEIVER"
rm -rf "$RECEIVER"*

# Echo the copy operations
echo "Copying to: $RECEIVER"
echo "Copying from: $SOURCE_1"
rclone copy "$SOURCE_1" "$RECEIVER" --include "PotDat.csv" --update --verbose --drive-skip-gdocs
RCLONE_EXIT_CODE_1=$?

echo "Copying from: $SOURCE_2"
rclone copy "$SOURCE_2" "$RECEIVER" --include "*.csv" --max-depth 1 --update --verbose --drive-skip-gdocs
RCLONE_EXIT_CODE_2=$?

# Combine exit codes
if [ $RCLONE_EXIT_CODE_1 -eq 0 ] && [ $RCLONE_EXIT_CODE_2 -eq 0 ]; then
    echo "SUCCESS: Files copied successfully"
else
    echo "ERROR: rclone failed with exit code: $RCLONE_EXIT_CODE_1 or $RCLONE_EXIT_CODE_2"
fi

echo "=== fetch_input.sh END: $(date) ==="

RCLONE_EXIT_CODE=$((RCLONE_EXIT_CODE_1 + RCLONE_EXIT_CODE_2))
exit $RCLONE_EXIT_CODE