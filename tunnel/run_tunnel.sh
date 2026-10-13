#!/bin/bash
# Nightly tunnel run: rebuild ALL of app/output/ - every selection folder - and publish it to
# repositoryRTBI/Tunnel/<folder>/ (Drive + local mirror, repository.py's default target="both").
# The ONE entry point for both cron (00:00) and a manual refresh - same script, so the two
# can never drift apart. Model: ~/potentials/potrank/run_potrank.sh
#
# Each folder says how it is built: app/output/<folder>/tunnel_runs.txt holds one line of
# tunnel_diag.py arguments per run ('#' comments and blank lines ignored), e.g.
#     --universe all --param lookback=100
#     --universe all --param lookback=250
# A new selection = a new folder with a tunnel_runs.txt; no edit here. A folder WITHOUT one is
# carried over unchanged (with a WARNING), so a hand-made folder is never lost - but it is not
# refreshed either.
#
# The whole set is built into a fresh app/output.new/ and replaces app/output/ only when every
# run of every folder succeeded, so a failed night leaves yesterday's set in place (and
# published) instead of a half set. The swap is also what retires the previous day's dated
# files: output/ only ever holds the newest runs, and the scoped `rclone sync` in repository.py
# then deletes the old ones on Drive too. Older days are regenerable with --asof <daynum>.
#
# Extra arguments are passed to every tunnel_diag.py call, e.g. ./run_tunnel.sh --stale-ok

LOGFILE=~/logs/run_tunnel.log
RECIPE=tunnel_runs.txt

# Ignore SIGHUP so SSH disconnect does not kill the run
trap '' HUP

# Log to file; also mirror to terminal while it is connected
exec > >(tee "$LOGFILE" 2>/dev/null) 2>&1

echo "=== run_tunnel.sh START: $(date) ==="
echo "Log file: $LOGFILE"

# A manual run landing on top of the cron run (or vice versa) is a no-op, not a race into
# the same output.new/.
LOCKFILE=/tmp/tunnel.lock
exec 200>"$LOCKFILE"
if ! flock -n 200; then
    echo "tunnel already running - nothing to do: $(date)"
    echo "=== run_tunnel.sh END: $(date) ==="
    exit 0
fi

CODE_DIR=/home/sm/potentials/tunnel/app/code
OUT_DIR=/home/sm/potentials/tunnel/app/output
NEW_DIR="$OUT_DIR.new"      # siblings of output/, so never inside the published namespace
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

fail() {
    echo "ERROR: $1 - keeping the previous $OUT_DIR, no publish"
    rm -rf "$NEW_DIR"
    echo "=== run_tunnel.sh END: $(date) ==="
    exit "${2:-1}"
}

rm -rf "$NEW_DIR"
mkdir -p "$NEW_DIR"

for SRC in "$OUT_DIR"/*/; do
    [ -d "$SRC" ] || continue
    NAME=$(basename "$SRC")
    DST="$NEW_DIR/$NAME"
    if [ ! -f "$SRC/$RECIPE" ]; then
        echo ""
        echo "WARNING: $NAME/ has no $RECIPE - carried over unchanged, not refreshed"
        cp -a "$SRC" "$DST" || fail "copying $NAME/ failed"
        continue
    fi
    mkdir -p "$DST"
    cp -a "$SRC/$RECIPE" "$DST/"
    mapfile -t RUNS < <(grep -v '^[[:space:]]*\(#\|$\)' "$SRC/$RECIPE")
    [ ${#RUNS[@]} -gt 0 ] || fail "$NAME/$RECIPE lists no runs"
    for LINE in "${RUNS[@]}"; do
        read -ra ARGS <<< "$LINE"
        echo ""
        echo "--- $NAME: tunnel_diag.py ${ARGS[*]} ---"
        python3 tunnel_diag.py "${ARGS[@]}" --out "$DST" "$@" < /dev/null
        RC=$?
        [ $RC -eq 0 ] || fail "$NAME: tunnel_diag.py ${ARGS[*]} exited $RC" $RC
    done
done

# Swap the new set in
rm -rf "$OLD_DIR"
[ -d "$OUT_DIR" ] && mv "$OUT_DIR" "$OLD_DIR"
mv "$NEW_DIR" "$OUT_DIR" && rm -rf "$OLD_DIR"
echo ""
echo "New contents of $OUT_DIR:"
ls -lR "$OUT_DIR"

echo ""
echo "--- Publishing app/output/ to repositoryRTBI/Tunnel/ ---"
python3 /home/sm/potentials/shared/app/code/repository.py publish tunnel
PUB_RC=$?
[ $PUB_RC -ne 0 ] && echo "ERROR: publish failed with exit code $PUB_RC"

echo ""
echo "=== run_tunnel.sh END: $(date) ==="
exit $PUB_RC
