#!/bin/bash
# Fetch input data from the LOCAL MIRROR (repositoryRTBI/data) to ../input
#
# Not from Google Drive - see ~/potentials/shared/app/code/repository.py for the
# three-layer rule and for this family's declared input list. Scoped to exactly
# what the group-conformity grader needs, not the full Longi pull.
#
# Note the consequence of reading the mirror: this family consumes longi_per1d,
# which longi publishes to Drive, which the mirror pulls back on its own cron.
# So this run must be scheduled AFTER a mirror tick that followed longi's
# publish, or it grades an hour-old vintage. The freshness gate below catches a
# dead mirror; it cannot catch a badly ordered cron.

echo "=== Fetch input data START: $(date) ==="

python3 /home/sm/potentials/shared/app/code/repository.py fetch group_conformity "$@"
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "ERROR: fetch failed with exit code: $EXIT_CODE"
fi

echo "=== fetch_input.sh END: $(date) ==="

exit $EXIT_CODE
