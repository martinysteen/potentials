#!/bin/bash
# Mirror GoogleDrive:PotSystem/repositoryRTBI/ to local data/
# Run hourly via cron, or manually: bash sync_rtbi.sh
#
# This script serves the MIRROR's needs and nothing else. Producers do not call
# it (they publish to Drive and stop there), and it does not call producers. If
# consumers need fresher data, the answer is this script's own cron entry.

SOURCE="GoogleDrive:PotSystem/repositoryRTBI"
DEST="/home/sm/potentials/repositoryRTBI/data"
# Outside DEST on purpose: anything inside data/ that Drive does not have is
# deleted by the next sync, and a status file that deletes itself is no status.
STATUS="/home/sm/potentials/repositoryRTBI/mirror_status.json"

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

# The mirror is authoritative for every family on this machine, so it has to say
# so itself: consumers gate on this stamp rather than assuming the cron ran.
# Written on failure too - an exit code recorded is what lets a consumer refuse.
FILES=$(find "$DEST" -type f | wc -l)
printf '{"finished": "%s", "exit_code": %d, "files": %d}\n' \
    "$(date -Is)" "$EXIT" "$FILES" > "$STATUS"

if [ $EXIT -ne 0 ]; then
    echo "ERROR: rclone exited with code $EXIT"
fi

echo "* sync_rtbi END: $(date) ($FILES files mirrored)"
exit $EXIT
