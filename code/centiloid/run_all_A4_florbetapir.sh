#!/bin/bash
# run_all_A4_florbetapir.sh -- run centiloid_pipeline_tracers.py --test on every subject of the
# A4 cohort (Florbetapir + T1), instead of --all.
#
# Why not --all: get_all_subject_ids() auto-discovers subjects by looking for DICOM folders shaped
# like florbetapir/Elder_subject_florbetapir/<6_digit_id>/, a layout A4 does not have (A4 is already
# NIfTI, with alphanumeric IDs like A4:56:571e). This wrapper replaces that auto-discovery with a
# plain listing of the subfolders already prepared under A4_DATA_DIR, without touching
# centiloid_pipeline_tracers.py (which keeps being used as-is for the GAAIN validation cohort, via
# its normal --all).
#
# Usage:
#   bash run_all_A4_florbetapir.sh
#   bash run_all_A4_florbetapir.sh A4:56:571e          # one subject only
#
# The results CSV (centiloid_results.csv) is accumulated incrementally in A4_DATA_DIR just like with
# --all -- each --test call writes to it internally (init_csv/update_csv_row). The one thing --all
# does that this wrapper does not reproduce is the global QC plot (generar_qc): it would not apply
# here anyway, because the GAAIN reference spreadsheet (Avid_Centiloid_standard_method.xlsx) has no
# data for voi_method=avid (ref_col_id=None), so --all would not generate a plot for this
# tracer+voi_method combination either.

set -uo pipefail

# PIPELINE_DIR is auto-detected (the folder this script lives in) so the package stays portable.
# A4_DATA_DIR DOES depend on where you copied the A4 data on this machine -- export A4_DATA_DIR
# before running if it is not the default below, e.g.:
#   A4_DATA_DIR=/data/A4_pipeline_input bash run_all_A4_florbetapir.sh
#
# VOI_METHOD (optional): 'avid' or 'klunk'. If not set, the flag is omitted and the Python script
# uses its own default (klunk). E.g.:
#   VOI_METHOD=avid bash run_all_A4_florbetapir.sh
PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
A4_DATA_DIR="${A4_DATA_DIR:-$HOME/Downloads/pet_pipeline/A4_pipeline_input}"
VOI_METHOD="${VOI_METHOD:-}"
PYTHON_SCRIPT="$PIPELINE_DIR/centiloid_pipeline_tracers.py"

cd "$PIPELINE_DIR" || { echo "ERROR: cannot find $PIPELINE_DIR"; exit 1; }

if [ ! -d "$A4_DATA_DIR" ]; then
    echo "ERROR: cannot find $A4_DATA_DIR"
    exit 1
fi

VOI_METHOD_FLAG=()
if [ -n "$VOI_METHOD" ]; then
    VOI_METHOD_FLAG=(--voi_method "$VOI_METHOD")
fi

# One subject only (debug), or every subject found under A4_DATA_DIR
if [ $# -ge 1 ]; then
    SUBJECT_IDS=("$1")
else
    SUBJECT_IDS=()
    for d in "$A4_DATA_DIR"/*/; do
        sid=$(basename "$d")
        [[ "$sid" == _* ]] && continue
        SUBJECT_IDS+=("$sid")
    done
fi

N_TOTAL=${#SUBJECT_IDS[@]}
N_OK=0
N_ERR=0
FAILED_IDS=()

echo "════════════════════════════════════════════════════════"
echo "  A4 Florbetapir — $N_TOTAL subject(s)"
echo "  out_dir: $A4_DATA_DIR"
echo "════════════════════════════════════════════════════════"

i=0
for sid in "${SUBJECT_IDS[@]}"; do
    i=$((i+1))
    echo ""
    echo "──[$i/$N_TOTAL] $sid ──────────────────────────────────"
    python "$PYTHON_SCRIPT" --test "$sid" --skip_dcm2niix --out "$A4_DATA_DIR" "${VOI_METHOD_FLAG[@]}"
    if [ $? -eq 0 ]; then
        N_OK=$((N_OK+1))
    else
        N_ERR=$((N_ERR+1))
        FAILED_IDS+=("$sid")
        echo "  X $sid finished with an error -- continuing with the next one"
    fi
done

echo ""
echo "════════════════════════════════════════════════════════"
echo "  SUMMARY"
echo "════════════════════════════════════════════════════════"
echo "  Total:  $N_TOTAL"
echo "  OK:     $N_OK"
echo "  Error:  $N_ERR"
if [ ${#FAILED_IDS[@]} -gt 0 ]; then
    echo ""
    echo "  Subjects with errors:"
    printf '    - %s\n' "${FAILED_IDS[@]}"
fi
echo ""
echo "  Results: $A4_DATA_DIR/centiloid_results.csv"
