#!/bin/bash
# Fetch inputdata from Google Drive to ../input
# Scoped to exactly what the group-conformity grader needs — not the full
# Longi/PotDat pull correlation/fetch_input.sh does.

echo "=== Fetch input data START: $(date) ==="

# Set source and destination
SOURCE_1=GoogleDrive:PotSystem/repositoryRTBI/
SOURCE_2=GoogleDrive:PotSystem/repositoryRTBI/Longi/
RECEIVER=/home/sm/potentials/group_conformity/app/input/

# Clear destination folder
echo "Clearing destination folder: $RECEIVER"
rm -rf "$RECEIVER"*

# Echo the copy operations
echo "Copying to: $RECEIVER"
echo "Copying from: $SOURCE_1"
rclone copy "$SOURCE_1" "$RECEIVER" --include "Stamdata.csv" --update --verbose --drive-skip-gdocs
RCLONE_EXIT_CODE_1=$?

echo "Copying from: $SOURCE_2"
rclone copy "$SOURCE_2" "$RECEIVER" \
    --include "{longi_per1d.csv,longi_grp_GICS_per1d.csv,longi_grp_Sector2_per1d.csv,longi_vola100d.csv,longi_future_per20d.csv,longi_future_per50d.csv}" \
    --max-depth 1 --update --verbose --drive-skip-gdocs
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
