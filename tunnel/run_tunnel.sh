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
#
# INTRADAY REFRESH: ./run_tunnel.sh --intraday (cron 20 1-22 * * *) does not refit. Every run
# saves its fitted tunnels to app/data/nightly/<folder>/ (--record-dir); with --intraday
# tunnel_diag.py takes those saved tunnels instead of fitting, carries their lines on to today
# and scores/draws them with the newer closes (purple). So: new tunnels once per day (the
# midnight run), today's price development shown inside last night's tunnel. Same recipes, same
# swap + publish. No saved tunnels yet (before the first nightly run) = the run fails safe and
# yesterday's output stays. The midnight run must NOT get --intraday.

LOGFILE=~/logs/run_tunnel.log
case " $* " in *" --intraday "*) LOGFILE=~/logs/run_tunnel_intraday.log ;; esac
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
REC_DIR=/home/sm/potentials/tunnel/app/data/nightly     # saved tunnels, outside the published namespace
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

# One selection = a folder holding a tunnel_runs.txt. Selections sit directly in output/ or one
# level down in a group folder (output/personal/SM/); a folder with neither is carried over.
build_selection() {
    local SRC=$1 NAME=$2 DST="$NEW_DIR/$2" LINE RC
    shift 2                                   # what is left is run_tunnel.sh's own extra arguments
    if [ ! -f "$SRC/$RECIPE" ]; then
        echo ""
        if [ "$NAME" = history ]; then      # rebuilt by run_tunnel_history.sh, only carried across the swap
            echo "history/ carried over unchanged (rebuilt by run_tunnel_history.sh)"
        else
            echo "WARNING: $NAME/ has no $RECIPE - carried over unchanged, not refreshed"
        fi
        mkdir -p "$(dirname "$DST")"
        cp -a "$SRC" "$DST" || fail "copying $NAME/ failed"
        return
    fi
    mkdir -p "$DST"
    cp -a "$SRC/$RECIPE" "$DST/"
    mapfile -t RUNS < <(grep -v '^[[:space:]]*\(#\|$\)' "$SRC/$RECIPE")
    [ ${#RUNS[@]} -gt 0 ] || fail "$NAME/$RECIPE lists no runs"
    for LINE in "${RUNS[@]}"; do
        read -ra ARGS <<< "$LINE"
        echo ""
        echo "--- $NAME: tunnel_diag.py ${ARGS[*]} ---"
        python3 tunnel_diag.py "${ARGS[@]}" --out "$DST" --record-dir "$REC_DIR/$NAME" "$@" < /dev/null
        RC=$?
        [ $RC -eq 0 ] || fail "$NAME: tunnel_diag.py ${ARGS[*]} exited $RC" $RC
    done
}

for TOP in "$OUT_DIR"/*/; do
    [ -d "$TOP" ] || continue
    TOPNAME=$(basename "$TOP")
    if [ ! -f "$TOP/$RECIPE" ] && compgen -G "$TOP*/$RECIPE" > /dev/null; then
        for SUB in "$TOP"*/; do                       # a group folder: its subfolders are the selections
            [ -d "$SUB" ] && build_selection "${SUB%/}" "$TOPNAME/$(basename "$SUB")" "$@"
        done
    else
        build_selection "${TOP%/}" "$TOPNAME" "$@"
    fi
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
