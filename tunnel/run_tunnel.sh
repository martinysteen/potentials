#!/bin/bash
# Nightly tunnel run: rebuild app/output/all/ (all tickers, LB100 + LB250) and publish it to
# repositoryRTBI/Tunnel/all (Drive + local mirror, repository.py's default target="both").
# The ONE entry point for both cron (00:00) and a manual refresh - same script, so the two
# can never drift apart. Model: ~/potentials/potrank/run_potrank.sh
#
# The build goes into a fresh all.new/ and replaces all/ only when every run succeeded, so a
# failed night leaves yesterday's files in place (and published) instead of a half set. The
# swap is also what retires the previous day's dated files: all/ only ever holds the newest
# run, and the scoped `rclone sync` in repository.py then deletes the old ones on Drive too.
# Older days are regenerable with tunnel_diag.py --asof <daynum>.
#
# Extra arguments are passed to every tunnel_diag.py call, e.g. ./run_tunnel.sh --stale-ok

LOGFILE=~/logs/run_tunnel.log

# Ignore SIGHUP so SSH disconnect does not kill the run
trap '' HUP

# Log to file; also mirror to terminal while it is connected
exec > >(tee "$LOGFILE" 2>/dev/null) 2>&1

echo "=== run_tunnel.sh START: $(date) ==="
echo "Log file: $LOGFILE"

# A manual run landing on top of the cron run (or vice versa) is a no-op, not a race into
# the same all.new/.
LOCKFILE=/tmp/tunnel.lock
exec 200>"$LOCKFILE"
if ! flock -n 200; then
    echo "tunnel already running - nothing to do: $(date)"
    echo "=== run_tunnel.sh END: $(date) ==="
    exit 0
fi

CODE_DIR=/home/sm/potentials/tunnel/app/code
OUT_DIR=/home/sm/potentials/tunnel/app/output/all
NEW_DIR="$OUT_DIR.new"
OLD_DIR="$OUT_DIR.old"

cd "$CODE_DIR" || {
    echo "ERROR: Failed to change to $CODE_DIR"
    exit 1
}

CONDA_BASE="$HOME/miniconda3"
if [ -f "$CONDA_BASE/etc/profile.d/conda.sh" ]; then
    source "$CONDA_BASE/etc/profile.d/conda.sh"
else
    echo "ERROR: Cannot find conda.sh at $CONDA_BASE/etc/profile.d/conda.sh"
    exit 1
fi

conda activate potsystem_env || {
    echo "ERROR: Failed to activate conda environment 'potsystem_env'"
    exit 1
}
echo "Using Python: $(which python3)"

rm -rf "$NEW_DIR"
mkdir -p "$NEW_DIR"

for LB in 100 250; do
    echo ""
    echo "--- tunnel_diag.py --universe all, lookback=$LB ---"
    python3 tunnel_diag.py --universe all --param lookback=$LB --out "$NEW_DIR" "$@"
    RC=$?
    if [ $RC -ne 0 ]; then
        echo "ERROR: tunnel_diag.py (lookback=$LB) exited $RC - keeping the previous $OUT_DIR, no publish"
        rm -rf "$NEW_DIR"
        echo "=== run_tunnel.sh END: $(date) ==="
        exit $RC
    fi
done

# Swap the new set in
rm -rf "$OLD_DIR"
[ -d "$OUT_DIR" ] && mv "$OUT_DIR" "$OLD_DIR"
mv "$NEW_DIR" "$OUT_DIR" && rm -rf "$OLD_DIR"
echo ""
echo "New contents of $OUT_DIR:"
ls -l "$OUT_DIR"

echo ""
echo "--- Publishing to repositoryRTBI/Tunnel/all ---"
python3 /home/sm/potentials/shared/app/code/repository.py publish tunnel
PUB_RC=$?
[ $PUB_RC -ne 0 ] && echo "ERROR: publish failed with exit code $PUB_RC"

echo ""
echo "=== run_tunnel.sh END: $(date) ==="
exit $PUB_RC
