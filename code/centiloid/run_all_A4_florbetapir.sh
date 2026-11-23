#!/bin/bash
# run_all_A4_florbetapir.sh -- run centiloid_pipeline_tracers.py --test on every subject of the
# A4 cohort (Florbetapir + T1), instead of --all.
#
# Why not --all: get_all_subject_ids() auto-discovers subjects by looking for DICOM folders shaped
# like florbetapir/Elder_subject_florbetapir/<6_digit_id>/, a layout A4 does not have (A4 is already
# NIfTI, with alphanumeric IDs like B99999999). This wrapper replaces that auto-discovery with a
# plain listing of the subfolders already prepared under A4_DATA_DIR, without touching
# centiloid_pipeline_tracers.py (which keeps being used as-is for the GAAIN validation cohort, via
# its normal --all).
#
# A4_DATA_DIR (input, read-only) and A4_OUT_DIR (output) are two separate folders: this pipeline
# only ever writes into A4_OUT_DIR, never into A4_DATA_DIR, so the cohort's original data stays
# exactly as you dropped it in. (--input_dir below is what makes that split possible.)
#
# Usage:
#   bash run_all_A4_florbetapir.sh
#   bash run_all_A4_florbetapir.sh B99999999          # one subject only
#
# The results CSV (centiloid_results.csv) is accumulated incrementally in A4_OUT_DIR just like with
# --all -- each --test call writes to it internally (init_csv/update_csv_row). The one thing --all
# does that this wrapper does not reproduce is the global QC plot (generar_qc): it would not apply
# here anyway, because the GAAIN reference spreadsheet (Avid_Centiloid_standard_method.xlsx) has no
# data for voi_method=avid (ref_col_id=None), so --all would not generate a plot for this
# tracer+voi_method combination either.

set -uo pipefail

# PIPELINE_DIR is auto-detected (the folder this script lives in) so the package stays portable.
# A4_DATA_DIR/A4_OUT_DIR DO depend on where you copied the A4 data on this machine -- export them
# before running if they are not the defaults below, e.g.:
#   A4_DATA_DIR=/data/A4_raw A4_OUT_DIR=/data/A4_results bash run_all_A4_florbetapir.sh
#
# VOI_METHOD (optional): 'avid' or 'klunk'. If not set, the flag is omitted and the Python script
# uses its own default (klunk). E.g.:
#   VOI_METHOD=avid bash run_all_A4_florbetapir.sh
PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PETPIPELINE_BASE="${PETPIPELINE_BASE:-$(cd "$PIPELINE_DIR/../.." && pwd)/pet_pipeline}"  # same convention as run_public_pipeline.sh (this repo's own pet_pipeline/ folder)
A4_DATA_DIR="${A4_DATA_DIR:-$PETPIPELINE_BASE/A4_pipeline_input}"   # input: your original T1/PET NIfTI files, never written to
A4_OUT_DIR="${A4_OUT_DIR:-$PETPIPELINE_BASE/A4_pipeline_output}"    # output: everything this pipeline generates (per-subject work files, results CSV)
VOI_METHOD="${VOI_METHOD:-}"
PYTHON_SCRIPT="$PIPELINE_DIR/centiloid_pipeline_tracers.py"

cd "$PIPELINE_DIR" || { echo "ERROR: cannot find $PIPELINE_DIR"; exit 1; }

if [ ! -d "$A4_DATA_DIR" ]; then
    echo "ERROR: cannot find $A4_DATA_DIR"
    exit 1
fi
mkdir -p "$A4_OUT_DIR"

VOI_METHOD_FLAG=()
if [ -n "$VOI_METHOD" ]; then
    VOI_METHOD_FLAG=(--voi_method "$VOI_METHOD")
fi

# One subject only (debug), or every subject found under A4_DATA_DIR
if [ $# -ge 1 ]; then
    SUBJECT_IDS=("$1")
else
    SUBJECT_IDS=()
    # nullglob matters here: without it, an A4_DATA_DIR with no subfolders leaves
    # the pattern unexpanded, basename returns a literal "*", and the whole run
    # proceeds with "*" as the subject ID -- producing paths like
    # A4_pipeline_output/*/batch_*.m that are handed to SPM verbatim.
    shopt -s nullglob
    for d in "$A4_DATA_DIR"/*/; do
        sid=$(basename "$d")
        [[ "$sid" == _* ]] && continue
        SUBJECT_IDS+=("$sid")
    done
    shopt -u nullglob
fi

if [ ${#SUBJECT_IDS[@]} -eq 0 ]; then
    echo "ERROR: no subject folders found in $A4_DATA_DIR"
    echo "Each subject needs its own folder there, holding that subject's T1 and PET, e.g.:"
    echo "  $A4_DATA_DIR/B10693248/B10693248_t1.nii"
    echo "  $A4_DATA_DIR/B10693248/B10693248_pet.nii"
    echo "Note this is the INPUT folder: results are written separately to $A4_OUT_DIR."
    exit 1
fi

# One subject requested: say clearly if ITS folder is the problem (and what is available)
if [ $# -ge 1 ] && [ ! -d "$A4_DATA_DIR/$1" ]; then
    echo "ERROR: subject folder not found: $A4_DATA_DIR/$1"
    echo "  Subject folders available in $A4_DATA_DIR:"
    ls -1 "$A4_DATA_DIR" 2>/dev/null | head -10 | sed 's/^/    /'
    echo "  Each subject needs: $A4_DATA_DIR/<ID>/<ID>_t1.nii and <ID>_pet.nii"
    exit 1
fi

# VOI files: check once here (they are the same for every subject) instead of failing subject by subject
VOI_CHECK="${VOI_METHOD:-klunk}"      # the Python script's own default is klunk
VOI_BASE="${CENTILOID_BASE_DIR:-$PETPIPELINE_BASE/centiloid_input}"
if [ "$VOI_CHECK" == "avid" ]; then
    VOI_FOLDER="$VOI_BASE/VOIs_2mm"
    VOI_NEEDED="anterior_cingulate.nii.gz posterior_cingulate.nii.gz parietal.nii.gz precuneus.nii.gz temporal.nii.gz frontal_med_orb.nii.gz cere_all.nii.gz"
else
    VOI_FOLDER="$VOI_BASE/VOIs_klunk"
    VOI_NEEDED="voi_ctx_2mm.nii voi_WhlCbl_2mm.nii"
fi
VOI_MISSING=""
for f in $VOI_NEEDED; do [ -f "$VOI_FOLDER/$f" ] || VOI_MISSING="$VOI_MISSING $f"; done
if [ -n "$VOI_MISSING" ]; then
    echo "ERROR: VOI files not found for VOI_METHOD=$VOI_CHECK. This is NOT a problem with the subjects:"
    echo "  the VOI masks used to measure the SUVr are missing."
    echo "  VOI folder: $VOI_FOLDER"
    echo "  Missing:   $VOI_MISSING"
    echo "  Found there: $(ls "$VOI_FOLDER" 2>/dev/null | head -12 | tr '\n' ' ')"
    echo "  Put the VOI files in that folder (they are not distributed with the repository), or set CENTILOID_BASE_DIR."
    echo "  Check everything with: bash code/centiloid/check_install_centiloid.sh --voi_method $VOI_CHECK"
    exit 1
fi

N_TOTAL=${#SUBJECT_IDS[@]}
N_OK=0
N_ERR=0
FAILED_IDS=()

echo "════════════════════════════════════════════════════════"
echo "  A4 Florbetapir — $N_TOTAL subject(s)"
echo "  input_dir: $A4_DATA_DIR"
echo "  out_dir:   $A4_OUT_DIR"
echo "════════════════════════════════════════════════════════"

i=0
for sid in "${SUBJECT_IDS[@]}"; do
    i=$((i+1))
    echo ""
    echo "──[$i/$N_TOTAL] $sid ──────────────────────────────────"
    python "$PYTHON_SCRIPT" --test "$sid" --skip_dcm2niix --input_dir "$A4_DATA_DIR" --out "$A4_OUT_DIR" "${VOI_METHOD_FLAG[@]}"
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
echo "  Results: $A4_OUT_DIR/centiloid_results.csv"
