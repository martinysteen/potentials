#!/bin/bash
# Fetch input data from the LOCAL MIRROR (repositoryRTBI/data) to ../input
#
# Not from Google Drive. The mirror is the authoritative copy on this machine:
# one place pulls from Drive (repositoryRTBI/sync_rtbi.sh), everybody else reads
# what it produced. A family reaching past it to Drive would be computing on a
# different vintage than its neighbours, for no gain.
#
# The declared input list lives in the registry at
# ~/potentials/shared/app/code/repository.py, together with the freshness gate:
# a mirror that failed its last sync, or has not synced recently, stops the run
# here rather than feeding it stale data.

echo "* Fetch input data START: $(date)"

python3 /home/sm/potentials/shared/app/code/repository.py fetch longi "$@"
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "ERROR: fetch failed with exit code: $EXIT_CODE"
fi

echo "* fetch_input.sh END: $(date)"

exit $EXIT_CODE
