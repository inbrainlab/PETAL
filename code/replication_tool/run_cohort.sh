#!/bin/bash
# run_cohort.sh -- run run_public_pipeline.sh for every subject found under
# MRI_DATA_DIR, one at a time, IN SERIES (finishes one before starting the
# next). Thin wrapper: no new processing logic -- it only calls
# run_public_pipeline.sh once per subject and keeps one log file per subject.
#
# Usage:
#   nohup bash run_cohort.sh [--tracer FTP|FDG] [--rewrite N|0b|all] > logs/cohort.out 2>&1 &
#   tail -f logs/cohort.out
#
# Any arguments given to this script (e.g. --tracer FDG) are forwarded as-is
# to run_public_pipeline.sh for every subject.
#
# Subjects are auto-discovered from every subdirectory under MRI_DATA_DIR
# (the same variable run_public_pipeline.sh itself uses -- see its own
# configuration block). run_public_pipeline.sh is already resumable per
# subject (should_run / checkpoint files), so relaunching this script after
# an interruption simply continues where it left off: a subject whose steps
# are already done just finishes quickly.

set -o pipefail   # no "set -e": one subject failing should not take down the whole cohort

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIPELINE_SCRIPT="$SCRIPT_DIR/run_public_pipeline.sh"        # per-subject pipeline, called once per subject below

FASTSURFER_BASE="${FASTSURFER_BASE:-$HOME/pet_pipeline}"    # same default as run_public_pipeline.sh
MRI_DATA_DIR="${MRI_DATA_DIR:-$FASTSURFER_BASE/mri_data}"   # one subdirectory per subject
LOGS_DIR="${LOGS_DIR:-$FASTSURFER_BASE/logs}"               # per-subject cohort logs (created automatically)

[ -f "$PIPELINE_SCRIPT" ] || { echo "ERROR: $PIPELINE_SCRIPT does not exist"; exit 1; }
mkdir -p "$LOGS_DIR"

SUBJECTS=()
for d in "$MRI_DATA_DIR"/*/; do
    [ -d "$d" ] || continue
    SUBJECTS+=("$(basename "$d")")
done
if [ "${#SUBJECTS[@]}" -eq 0 ]; then
    echo "ERROR: no subject subdirectories found under $MRI_DATA_DIR"
    exit 1
fi

GLOBAL_START=$(date +%s)
hms() { printf "%02d:%02d:%02d" $(( $1/3600 )) $(( ($1%3600)/60 )) $(( $1%60 )); }

TOTAL=${#SUBJECTS[@]}
DONE_COUNT=0; FAIL_COUNT=0

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "COHORT -- $(basename "$PIPELINE_SCRIPT"), in series -- $(date '+%Y-%m-%d %H:%M:%S')"
echo "Subjects: $TOTAL (auto-discovered under $MRI_DATA_DIR)   Args: $*"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

for i in "${!SUBJECTS[@]}"; do
    SUBJECT="${SUBJECTS[$i]}"
    NUM=$((i+1))
    LOG_FILE="$LOGS_DIR/${SUBJECT}.log"

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "[$NUM/$TOTAL] $SUBJECT   ($(date '+%H:%M:%S'))"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    SUBJ_START=$(date +%s)
    if bash "$PIPELINE_SCRIPT" "$SUBJECT" "$@" 2>&1 | tee "$LOG_FILE"; then
        SUBJ_EL=$(( $(date +%s) - SUBJ_START ))
        echo "  OK $SUBJECT COMPLETE in $(hms $SUBJ_EL)"
        DONE_COUNT=$((DONE_COUNT+1))
    else
        echo "  X  $SUBJECT failed -- check $LOG_FILE"
        FAIL_COUNT=$((FAIL_COUNT+1))
    fi

    echo "  progress: $DONE_COUNT ok - $FAIL_COUNT failed - $(hms $(( $(date +%s) - GLOBAL_START ))) elapsed"
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "COHORT COMPLETE"
echo "  OK:      $DONE_COUNT"
echo "  Failed:  $FAIL_COUNT"
echo "  Total:   $(hms $(( $(date +%s) - GLOBAL_START )))"
echo "  Per-subject logs: $LOGS_DIR/<SUBJECT>.log"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
