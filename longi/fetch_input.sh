#!/bin/bash
# Fetch inputdata from Google Drive to ../input


echo "=== Fetch input data START: $(date) ==="

# Set source and destination
SOURCE=GoogleDrive:PotSystem/repositoryRTBI/
RECEIVER=/home/sm/potentials/longi/app/input/

# Clear destination folder
echo "Clearing destination folder: $RECEIVER"
rm -rf "$RECEIVER"*

# Echo the copy operations
echo "Copying to: $RECEIVER"
echo "Copying from: $SOURCE"
rclone copy "$SOURCE" "$RECEIVER" --include "{PotDat.csv,Stamdata.csv,Cal.csv}" --update --verbose --drive-skip-gdocs
RCLONE_EXIT_CODE=$?

# Check result
if [ $RCLONE_EXIT_CODE -eq 0 ]; then
    echo "SUCCESS: Files copied successfully"
else
    echo "ERROR: rclone failed with exit code: $RCLONE_EXIT_CODE"
fi

echo "=== fetch_input.sh END: $(date) ==="

exit $RCLONE_EXIT_CODE