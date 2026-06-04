#!/bin/bash
# Mirror GoogleDrive:PotSystem/repositoryRTBI/ to local data/
# Run hourly via cron, or manually: bash sync_rtbi.sh

SOURCE="GoogleDrive:PotSystem/repositoryRTBI"
DEST="/home/sm/potentials/repositoryRTBI/data"

echo "*************************************************"
echo "* sync_rtbi START: $(date)"

rclone sync "$SOURCE" "$DEST" \
    --update \
    --drive-skip-gdocs \
    --exclude "Longi/exp/**" \
    --exclude "Longi/QA/**" \
    --verbose \
    2>&1 | tee -a "/home/sm/logs/sync_repositoryRTBI.log"

EXIT=${PIPESTATUS[0]}

if [ $EXIT -ne 0 ]; then
    echo "ERROR: rclone exited with code $EXIT"
fi

echo "* sync_rtbi END: $(date)"
exit $EXIT
