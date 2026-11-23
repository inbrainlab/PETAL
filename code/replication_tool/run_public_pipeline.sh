#!/bin/bash
# run_public_pipeline.sh -- PET processing for Tau (Flortaucipir, FTP) and FDG.
# Usage:  bash run_public_pipeline.sh <SUBJECT> [--tracer FTP|FDG] [--rewrite N|0b|all]
#
# Expected layout (PETPIPELINE_BASE, default ~/pet_pipeline):
#   mri_data/<SUBJECT>/<SUBJECT>_T1.nii[.gz]
#   mri_data/<SUBJECT>/<PET>.nii           (accepted names: see PET_GLOB_CANDIDATES;
#                                           or set PET_GLOB_FTP / PET_GLOB_FDG)
#   output/                                (outputs; created if missing)
#   fs_license/.license                    (FreeSurfer license: NOT distributed)
#
# Requirements: Docker (images freesurfer/freesurfer:7.4.1 and
# deepmi/fastsurfer:cu126-v2.4.2), a Python environment with nibabel (PYTHON,
# default ~/.venv_pet_pipeline/bin/python3) and progress_helpers.sh in the same
# folder as this script (recon_progress.py is optional).
#
# Per-subject outputs (in output/<SUBJECT>/):
#   FTP: output.csv (segstats per region), gtmpvc_T1space_mask.output/gtm.stats.dat
#   FDG: output_fdg.csv and output_brainstem_fdg.csv (pons = label 174); no PVC.
#   The Tau SUVR (whole cerebellum reference) and the FDG SUVR (pons reference)
#   are computed by evaluate_subject.py.
#
# At the end, if you define PUBLIC_PACKAGE (folder of the public package, with
# data/), FS_LUT (FreeSurferColorLUT.txt) and FSROI_LIST (data/rois_ftp.csv for
# Tau; for FDG data/rois_fdg.csv is used if you do not set it),
# evaluate_subject.py is run: if the subject is among the published values, your
# result is compared against them; otherwise only your output is reported.

set -e

# ── configuration ─────────────────────────────────────────────────────────────
PETPIPELINE_BASE="${PETPIPELINE_BASE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/pet_pipeline}"  # working directory root -- defaults to this repo's own pet_pipeline/ folder; override by exporting PETPIPELINE_BASE
MRI_DATA_DIR="${MRI_DATA_DIR:-$PETPIPELINE_BASE/mri_data}"   # raw T1/PET source files, one subdirectory per subject
SUBJECTS_DIR="$PETPIPELINE_BASE/output"                      # FreeSurfer SUBJECTS_DIR -- recon-all output and this pipeline's own result CSVs land here
FS_LICENSE_DIR="$PETPIPELINE_BASE/fs_license"                # directory holding the FreeSurfer license file (.license)
FASTSURFER_IMAGE="deepmi/fastsurfer:cu126-v2.4.2"           # optional GPU path, RECON_METHOD=fastsurfer
FREESURFER_IMAGE="freesurfer/freesurfer:7.4.1"              # classic recon-all, the default method
PYTHON="${PYTHON:-$HOME/.venv_pet_pipeline/bin/python3}"    # virtualenv python3, used for small inline NIfTI-reading steps
PUBLIC_PACKAGE="${PUBLIC_PACKAGE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"  # folder of the public package (with data/) used for comparison; defaults to this repo's own root
# FreeSurferColorLUT.txt is not shipped with this repo: prefer a copy kept inside PETPIPELINE_BASE
# (same convention as MCRv97 and the SPM standalone), otherwise fall back to ~/freesurfer.
if [ -z "${FS_LUT:-}" ]; then
    if [ -f "$PETPIPELINE_BASE/FreeSurferColorLUT.txt" ]; then
        FS_LUT="$PETPIPELINE_BASE/FreeSurferColorLUT.txt"
    else
        FS_LUT="$HOME/freesurfer/FreeSurferColorLUT.txt"
    fi
fi
FSROI_LIST_USER_SET="${FSROI_LIST:+1}"                       # remembers whether YOU exported FSROI_LIST, before the FTP default below overwrites it (needed so the FDG default further down can still kick in)
FSROI_LIST="${FSROI_LIST:-$PUBLIC_PACKAGE/data/rois_ftp.csv}"  # Tau ROI list, shipped in data/ and regenerable with code/replication_tool/make_roi_lists.py (FDG instead defaults to data/rois_fdg.csv further below)
MCR_DIR="${MCR_DIR:-$PETPIPELINE_BASE/MCRv97}"                # Matlab Compiled Runtime v97, needed by segmentBS.sh (FDG and classic recon-all brainstem step)

# ── arguments ──────────────────────────────────────────────────────────────────────
# Non-positional parsing: --tracer and --rewrite may appear in any order after $1.
print_usage() {
    cat <<USAGE
Usage: bash run_public_pipeline.sh <SUBJECT> [--tracer FTP|FDG] [--rewrite N|0b|all]

  <SUBJECT>          Subject ID (matches the folder under MRI_DATA_DIR and the
                      file prefix, e.g. <SUBJECT>_T1.nii -- see docs/REPLICATION.md).
  --tracer FTP|FDG   Which PET tracer to process. Default: FTP (Flortaucipir).
  --rewrite N        Force STEP N (and everything after it) to re-run, even if
                      its output already exists. See "Resuming from any step"
                      in docs/REPLICATION.md for the full list of step numbers.
  --rewrite 0b       Force talairach.m3z / segmentBS.sh to re-run.
  --rewrite all      Start over from recon-all (STEP 0).
  -h, --help         Show this help and exit.

Without --rewrite, the script resumes automatically: any step whose output
already exists under <PETPIPELINE_BASE>/output/<SUBJECT>/ is skipped.

Environment variables (all optional, see the configuration block at the top
of this script for their defaults): PETPIPELINE_BASE, MRI_DATA_DIR, PYTHON,
PUBLIC_PACKAGE, FS_LUT, FSROI_LIST, MCR_DIR, RECON_METHOD, OPENMP_THREADS.

Example:
  bash run_public_pipeline.sh 011_S_4912 --tracer FDG
USAGE
}

case "${1:-}" in
    -h|--help) print_usage; exit 0 ;;
esac

SUBJECT=${1:-}
if [ -z "$SUBJECT" ] || [[ "$SUBJECT" == --* ]]; then
    print_usage; exit 1
fi
REWRITE_FROM=999
REWRITE_0B=0
TRACER="FTP"

shift || true
while [ $# -gt 0 ]; do
    case "$1" in
        --rewrite)
            if [ "$2" == "all" ]; then REWRITE_FROM=0; REWRITE_0B=1
            elif [ "$2" == "0b" ]; then REWRITE_0B=1
            elif [[ "$2" =~ ^[0-9]+$ ]]; then REWRITE_FROM=$2
            else echo "ERROR: --rewrite requires a number, '0b' or 'all'"; exit 1
            fi
            shift 2
            ;;
        --tracer)
            TRACER=$(echo "$2" | tr '[:lower:]' '[:upper:]')
            if [ "$TRACER" != "FTP" ] && [ "$TRACER" != "FDG" ]; then
                echo "ERROR: --tracer must be FTP or FDG (received: $2)"; exit 1
            fi
            shift 2
            ;;
        -h|--help)
            print_usage; exit 0
            ;;
        *)
            echo "ERROR: unrecognized argument: $1"; exit 1
            ;;
    esac
done

# ── per-tracer tags ───────────────────────────────────────────────────────────
# FTP uses unsuffixed file names. FDG uses the suffix _fdg so that FTP and FDG
# outputs of the same subject can coexist without colliding.
if [ "$TRACER" == "FTP" ]; then
    PET_TAG="tau"; PET_SUFFIX=""
else
    PET_TAG="fdg"; PET_SUFFIX="_fdg"
fi
PET_SUMMED_RAW="${PET_TAG}_pet_summed.nii"
PET_SUMMED_R="r${PET_TAG}_pet_summed.nii"
LTA_P2M="template_PET2MRI${PET_SUFFIX}.lta"
LTA_M2P="template_MRI2PET${PET_SUFFIX}.lta"
RNU_NII="mri/rnu${PET_SUFFIX}.nii"
RAPARC_NII="mri/raparc+aseg${PET_SUFFIX}.nii"
OUTPUT_CSV="output${PET_SUFFIX}.csv"
FRAMES_DONE_FLAG=".frames_done${PET_SUFFIX}"

# ── validation ──────────────────────────────────────────────────────────────
if [ ! -d "$MRI_DATA_DIR/$SUBJECT" ]; then
    echo "ERROR: Folder not found: $MRI_DATA_DIR/$SUBJECT"; exit 1
fi
T1_FILE=$(ls "$MRI_DATA_DIR/$SUBJECT/${SUBJECT}_T1.nii" "$MRI_DATA_DIR/$SUBJECT/${SUBJECT}_T1.nii.gz" \
    "$MRI_DATA_DIR/$SUBJECT/${SUBJECT}"_I*_T1.nii "$MRI_DATA_DIR/$SUBJECT/${SUBJECT}"_I*_T1.nii.gz \
    "$MRI_DATA_DIR/$SUBJECT/${SUBJECT}"_*_I*_T1.nii "$MRI_DATA_DIR/$SUBJECT/${SUBJECT}"_*_I*_T1.nii.gz \
    2>/dev/null | head -1)
if [ -z "$T1_FILE" ]; then
    echo "ERROR: T1 not found in $MRI_DATA_DIR/$SUBJECT/ (expected: ${SUBJECT}_T1.nii[.gz])"; exit 1
fi

# PET file-name patterns per tracer. The A4-style names are tried first, then
# ADNI-style names (e.g. ${SUBJECT}_${TRACER}.nii[.gz]). Set PET_GLOB_FTP or
# PET_GLOB_FDG if none of them matches your data.
if [ "$TRACER" == "FTP" ]; then
    TRACER_LABEL="Flortaucipir (FTP)"
    ACQ_WINDOW_MIN=75; ACQ_WINDOW_MAX=105
    PET_GLOB_CANDIDATES=("${PET_GLOB_FTP:-}" "A4_${SUBJECT}_MR_Flortaucipir_Br_*.nii" "${SUBJECT}_AV1451.nii*" "${SUBJECT}_FTP.nii*" "${SUBJECT}_I*_FTP.nii*" "${SUBJECT}_I*_AV1451.nii*" "${SUBJECT}_*_I*_FTP.nii*" "${SUBJECT}_*_I*_AV1451.nii*" "${SUBJECT}_*_I*_FTP*.nii*" "${SUBJECT}_*_I*_AV1451*.nii*")
else
    TRACER_LABEL="FDG"
    ACQ_WINDOW_MIN=30; ACQ_WINDOW_MAX=60
    PET_GLOB_CANDIDATES=("${PET_GLOB_FDG:-}" "A4_${SUBJECT}_MR_FDG_Br_*.nii" "${SUBJECT}_FDG.nii*" "${SUBJECT}_I*_FDG.nii*" "${SUBJECT}_*_I*_FDG.nii*" "${SUBJECT}_*_I*_FDG*.nii*")
fi
PET_FILE=""
for pat in "${PET_GLOB_CANDIDATES[@]}"; do
    [ -z "$pat" ] && continue
    MATCH=$(ls "$MRI_DATA_DIR/$SUBJECT"/$pat 2>/dev/null | head -1)
    if [ -n "$MATCH" ]; then PET_FILE="$MATCH"; PET_GLOB="$pat"; break; fi
done
if [ -z "$PET_FILE" ]; then
    echo "ERROR: PET $TRACER_LABEL not found in $MRI_DATA_DIR/$SUBJECT/ -- tried: ${PET_GLOB_CANDIDATES[*]}"
    echo "       If your file naming differs, export PET_GLOB_FTP or PET_GLOB_FDG before running."
    exit 1
fi
PET_BASENAME=$(basename "$PET_FILE")

# Resolution reminder only, does not block.
if [ "$TRACER" == "FDG" ] && [[ "$PET_BASENAME" != A4_* ]]; then
    echo "  ℹ️  ADNI source detected: ADNI distributes FDG at several uniform resolutions."
    echo "      The published values were computed from the 'Uniform 6mm Res' series; a different"
    echo "      series changes the resolution and therefore the SUVR."
fi
if [ ! -f "$PYTHON" ]; then
    echo "ERROR: Python not found at $PYTHON"
    echo "Run: python3 -m venv ~/.venv_pet_pipeline && ~/.venv_pet_pipeline/bin/pip install nibabel"
    exit 1
fi

mkdir -p "$SUBJECTS_DIR"
SUBJECT_DIR="$SUBJECTS_DIR/$SUBJECT"

# ── timer ─────────────────────────────────────────────────────────────────────
PIPELINE_START=$(date +%s)
STEP_START=0
step_start() { STEP_START=$(date +%s); }
step_end() {
    local end=$(date +%s); local elapsed=$((end - STEP_START))
    printf "  ⏱  %-45s %02d:%02d\n" "$1" $((elapsed/60)) $((elapsed%60))
}
pipeline_end() {
    local end=$(date +%s); local elapsed=$((end - PIPELINE_START))
    printf "  ⏱  %-45s %02d:%02d\n" "TOTAL" $((elapsed/60)) $((elapsed%60))
}
check_file() {
    if [ -f "$SUBJECT_DIR/$1" ]; then
        printf "  ✅ %-40s %s\n" "$2" "$(du -sh $SUBJECT_DIR/$1 2>/dev/null | cut -f1)"
    else
        printf "  ❌ %-40s NOT FOUND\n" "$2"
    fi
}
should_run() {
    local step_num=$1; local output="$SUBJECT_DIR/$2"; local label=$3
    if [ "$REWRITE_FROM" -le "$step_num" ]; then
        [[ "$2" == .frames_done* ]] && rm -f "$SUBJECT_DIR/$2"
        return 0
    fi
    if [ -f "$output" ]; then
        echo ""; echo "── STEP $step_num: $label"
        printf "  ⏭  skipping — %s already exists\n" "$(basename $output)"
        return 1
    fi
    return 0
}

# ── FreeSurfer license ────────────────────────────────────────────────────────
# Only the steps that actually run FreeSurfer or FastSurfer inside Docker need the license.
# A subject whose outputs already exist skips every one of those steps, so this is checked
# where it is used rather than up front: re-running a finished subject (to regenerate only
# the comparison with the published values, say) must not be blocked by a license it will
# never read.
require_license() {
    if [ -f "$FS_LICENSE_DIR/.license" ]; then return 0; fi
    # To stderr on purpose: run_fs is also called inside $( ), where anything on stdout is
    # captured into the variable and the user would see nothing at all.
    echo "ERROR: License not found at $FS_LICENSE_DIR/.license" >&2
    echo "  This step runs FreeSurfer/FastSurfer in Docker, which requires it." >&2
    echo "  It is free: https://surfer.nmr.mgh.harvard.edu/registration.html -- save the file" >&2
    echo "  you receive as $FS_LICENSE_DIR/.license (note the leading dot)." >&2
    exit 1
}

# ── FreeSurfer docker helper ──────────────────────────────────────────────────
run_fs() {
    require_license
    docker run --rm \
        -v "$MRI_DATA_DIR":/data \
        -v "$SUBJECTS_DIR":/output \
        -v "$FS_LICENSE_DIR/.license":/usr/local/freesurfer/.license \
        -v "$MCR_DIR":/usr/local/freesurfer/MCRv97 \
        -e SUBJECTS_DIR=/output \
        --entrypoint bash \
        "$FREESURFER_IMAGE" -c "$1"
}

# ── live progress helper (recon-all and segmentBS.sh) ─────────────────────────
# run_with_progress runs the given command in the background and, while it is
# running, prints the percentage of progress (via recon_progress.py) every
# POLL_INLINE_INTERVAL seconds. It preserves the command's real exit code
# (important for should_run / set -e).
PROGRESS_HELPERS="$(dirname "${BASH_SOURCE[0]}")/progress_helpers.sh"
if [ ! -f "$PROGRESS_HELPERS" ]; then
    echo "ERROR: $PROGRESS_HELPERS not found (required for run_with_progress)"
    exit 1
fi
source "$PROGRESS_HELPERS"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Subject:      $SUBJECT"
echo "Tracer:       $TRACER_LABEL"
echo "T1:           $(basename $T1_FILE)"
echo "PET:          $PET_BASENAME"
[ "$REWRITE_FROM" -le 999 ] && echo "Rewrite from: STEP $REWRITE_FROM" || echo "Mode:         resume"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── STEP 0a: recon-all (classic FreeSurfer by default, FastSurfer optional) ──
# RECON_METHOD=freesurfer (default) runs classic CPU recon-all.
# RECON_METHOD=fastsurfer uses the GPU-accelerated reconstruction (minutes
# instead of hours), but it is a different tool with its own results -- use it
# only if that is what you want.
RECON_METHOD="${RECON_METHOD:-freesurfer}"
OPENMP_THREADS="${OPENMP_THREADS:-4}"

if should_run 0 "mri/aparc+aseg.mgz" "recon-all ($RECON_METHOD)"; then
    require_license
    RECON_LOG_0A="$SUBJECTS_DIR/$SUBJECT/scripts/recon-all.log"

    if [ "$RECON_METHOD" == "fastsurfer" ]; then
        echo ""; echo "── STEP 0a: FastSurfer recon-all (GPU)..."
        step_start
        run_with_progress "$RECON_LOG_0A" \
            docker run --gpus all --rm \
                -u $(id -u):$(id -g) \
                -v "$MRI_DATA_DIR":/data \
                -v "$SUBJECTS_DIR":/output \
                -v "$FS_LICENSE_DIR":/fs_license \
                "$FASTSURFER_IMAGE" \
                --t1 /data/$SUBJECT/$(basename $T1_FILE) \
                --sid $SUBJECT \
                --sd /output \
                --fs_license /fs_license/.license \
                --no_hypothal \
                --fsaparc
        step_end "STEP 0a: FastSurfer recon-all"
    else
        echo ""; echo "── STEP 0a: recon-all -all (classic FreeSurfer, CPU, ~3-4h)..."
        step_start
        run_with_progress "$RECON_LOG_0A" \
            docker run --rm \
                -e HOME=/tmp \
                -v "$MRI_DATA_DIR":/data \
                -v "$SUBJECTS_DIR":/output \
                -v "$FS_LICENSE_DIR/.license":/usr/local/freesurfer/.license \
                --entrypoint bash \
                "$FREESURFER_IMAGE" -c "
                    export SUBJECTS_DIR=/output
                    recon-all -s $SUBJECT -i /data/$SUBJECT/$(basename $T1_FILE) \
                        -all -parallel -openmp $OPENMP_THREADS
                "
        # Classic recon-all runs as root in the container -- give ownership
        # back to the current user.
        docker run --rm -v "$SUBJECTS_DIR":/output --entrypoint bash \
            "$FREESURFER_IMAGE" -c "chown -R $(id -u):$(id -g) /output/$SUBJECT" 2>/dev/null || true
        step_end "STEP 0a: recon-all (classic FreeSurfer)"
    fi
    echo "  recon-all complete ✅"
fi

# ── STEP 0b: generate talairach.m3z ────────────────────────────────────────────
if should_run 0 "mri/transforms/talairach.m3z" "talairach.m3z" || [ "$REWRITE_0B" -eq 1 ]; then
    echo ""; echo "── STEP 0b: Generating talairach.m3z..."
    step_start
    run_fs "
        export SUBJECTS_DIR=/output
        rm -f /output/$SUBJECT/mri/transforms/talairach.m3z
        recon-all -s $SUBJECT -careg -no-isrunning > /dev/null 2>&1
    "
    step_end "STEP 0b: talairach.m3z"
    echo "  talairach.m3z ✅"
fi

# ── STEP 0c: segmentBS.sh (pons mask, ONLY needed for FDG) ───────────────────
# Its only consumers are STEP 13b/14b, which are limited to --tracer FDG. For
# FTP it would be wasted work (and would require the Matlab Runtime), so it is
# skipped entirely.
if [ "$TRACER" != "FDG" ]; then
    echo ""; echo "── STEP 0c: segmentBS.sh -- skipped (only applies to --tracer FDG)"
elif should_run 0 "mri/brainstemSsLabels.v13.FSvoxelSpace.mgz" "segmentBS.sh"; then
    echo ""; echo "── STEP 0c: segmentBS.sh (brainstem substructures / pons)..."
    step_start
    SEGMENTBS_LOG="$SUBJECTS_DIR/$SUBJECT/scripts/brainstem-substructures-T1.log"
    run_with_progress "$SEGMENTBS_LOG" run_fs "
        export SUBJECTS_DIR=/output
        segmentBS.sh $SUBJECT > /dev/null 2>&1
    "
    step_end "STEP 0c: segmentBS.sh"
    check_file "mri/brainstemSsLabels.v13.FSvoxelSpace.mgz" "brainstemSsLabels (pons)"
fi

# ── get number of frames ──────────────────────────────────────────────────
# NFRAMES is used only by STEPS 1-7. Asking for it means running FreeSurfer in Docker, so when
# those steps are already done it must not be asked for at all: otherwise a fully processed
# subject still demands Docker and the license to produce a number nothing will read.
if [ "$REWRITE_FROM" -gt 7 ] \
   && [ -f "$SUBJECT_DIR/$FRAMES_DONE_FLAG" ] \
   && [ -f "$SUBJECT_DIR/$PET_SUMMED_RAW" ]; then
    NFRAMES=""
    echo ""; echo "PET frames: not queried -- STEPS 1-7 are already done for this subject"
else
    NFRAMES=$(run_fs "mri_info /data/$SUBJECT/$PET_BASENAME 2>/dev/null | grep nframes | awk '{print \$2}'")
    if ! [[ "$NFRAMES" =~ ^[0-9]+$ ]] || [ "$NFRAMES" -lt 1 ]; then
        echo "ERROR: invalid NFRAMES ('$NFRAMES') for $SUBJECT -- aborting"
        exit 1
    fi
    echo ""; echo "PET frames: $NFRAMES"
fi
if [ "$NFRAMES" == "1" ]; then
    echo "  ℹ️  Single frame detected: the PET is probably already preprocessed (ADNI-style"
    echo "      'Coreg, Avg, Std Img and Vox Siz'). STEPS 1-7 will run as safe no-ops"
    echo "      (coregistering a frame to itself, summing a single frame) -- this is not an error."
fi

# ── acquisition window: informational check, non-blocking ────────────────────
# Requires a BIDS JSON sidecar next to the PET with FrameDuration/FrameTimesStart.
# If it does not exist the check is silently skipped; it is not a pipeline requirement.
PET_JSON="${PET_FILE%.nii}.json"
if [ -f "$PET_JSON" ]; then
    WIN_CHECK=$($PYTHON -c "
import json
try:
    d = json.load(open('$PET_JSON'))
    dur = d.get('FrameDuration') or d.get('FrameTimesStart')
    fts = d.get('FrameTimesStart')
    if fts and isinstance(fts, list):
        span_min = (fts[-1] - fts[0]) / 60.0
        print(round(span_min, 1))
    else:
        print('NA')
except Exception:
    print('NA')" 2>/dev/null)
    if [ "$WIN_CHECK" != "NA" ] && [ -n "$WIN_CHECK" ]; then
        IN_WINDOW=$($PYTHON -c "print(1 if $ACQ_WINDOW_MIN <= $WIN_CHECK <= $((ACQ_WINDOW_MAX+5)) else 0)" 2>/dev/null)
        if [ "$IN_WINDOW" != "1" ]; then
            echo "  ⚠️  WARNING: frame window (~${WIN_CHECK} min) outside the expected range for $TRACER_LABEL (${ACQ_WINDOW_MIN}-${ACQ_WINDOW_MAX} min) -- check the JSON sidecar"
        else
            echo "  frame window: ~${WIN_CHECK} min (expected ${ACQ_WINDOW_MIN}-${ACQ_WINDOW_MAX} min for $TRACER_LABEL) ✅"
        fi
    fi
fi

SPM_SEP="1.5"; SPM_FWHM="1"; SPM_INTERP="cubic"; COREG_RUNS=5

# Intermediate frame files carry the tracer suffix so that FTP and FDG outputs
# of the same subject can coexist without overwriting each other.
FRAME_PFX="frame${PET_SUFFIX}"

# ── STEP 1: extract frames ────────────────────────────────────────────────────
if should_run 1 "$FRAMES_DONE_FLAG" "Extract frames"; then
    echo ""; echo "── STEP 1: Extracting $NFRAMES frames..."
    step_start
    run_fs "
        cd /output/$SUBJECT
        for i in \$(seq 0 $((NFRAMES-1))); do
            mri_convert /data/$SUBJECT/$PET_BASENAME --frame \$i ${FRAME_PFX}_\${i}.nii > /dev/null 2>&1 &
        done
        wait
        NGOT=\$(ls ${FRAME_PFX}_*.nii 2>/dev/null | wc -l)
        echo \"Frames generated: \$NGOT/$NFRAMES\"
        if [ \"\$NGOT\" -ne $NFRAMES ]; then
            echo \"ERROR: expected $NFRAMES frames, generated \$NGOT\" >&2
            exit 1
        fi
    "
    step_end "STEP 1: Extract frames"; echo "  frames extracted ✅"
fi

# ── STEP 2: initial mean ──────────────────────────────────────────────────────
if should_run 2 "$FRAMES_DONE_FLAG" "Initial mean"; then
    echo ""; echo "── STEP 2: Computing initial mean..."
    step_start
    run_fs "cd /output/$SUBJECT && mri_concat /data/$SUBJECT/$PET_BASENAME --mean --o ${FRAME_PFX}_mean.nii > /dev/null 2>&1"
    step_end "STEP 2: Initial mean"; echo "  ${FRAME_PFX}_mean.nii ✅"
fi

# ── STEP 3: iteration 1 coreg ─────────────────────────────────────────────────
if should_run 3 "$FRAMES_DONE_FLAG" "Iteration 1 coreg"; then
    echo ""; echo "── STEP 3: Iteration 1 coreg..."
    step_start
    run_fs "
        cd /output/$SUBJECT
        for i in \$(seq 0 $((NFRAMES-1))); do
            (mri_coreg --mov ${FRAME_PFX}_\${i}.nii --ref ${FRAME_PFX}_mean.nii --no-ref-mask \
                --reg ${FRAME_PFX}_\${i}.lta --sep $SPM_SEP --ref-fwhm $SPM_FWHM \
                --threads 2 > /dev/null 2>&1 && \
             mri_vol2vol --mov ${FRAME_PFX}_\${i}.nii --reg ${FRAME_PFX}_\${i}.lta \
                --targ ${FRAME_PFX}_mean.nii --interp $SPM_INTERP \
                --o ${FRAME_PFX}_\${i}_aligned.nii > /dev/null 2>&1) &
        done
        wait
        NGOT=\$(ls ${FRAME_PFX}_*_aligned.nii 2>/dev/null | wc -l)
        echo \"Aligned frames (iter1): \$NGOT/$NFRAMES\"
        if [ \"\$NGOT\" -ne $NFRAMES ]; then
            echo \"ERROR: expected $NFRAMES aligned frames (iter1), generated \$NGOT\" >&2
            exit 1
        fi
    "
    step_end "STEP 3: Iteration 1 coreg"; echo "  iteration 1 done ✅"
fi

# ── STEP 4: recompute mean ────────────────────────────────────────────────────
if should_run 4 "$FRAMES_DONE_FLAG" "Recompute mean"; then
    echo ""; echo "── STEP 4: Recomputing mean..."
    step_start
    run_fs "
        cd /output/$SUBJECT
        mri_concat \$(for i in \$(seq 0 $((NFRAMES-1))); do echo ${FRAME_PFX}_\${i}_aligned.nii; done) \
            --mean --o ${FRAME_PFX}_mean2.nii > /dev/null 2>&1
    "
    step_end "STEP 4: Recompute mean"; echo "  ${FRAME_PFX}_mean2.nii ✅"
fi

# ── STEP 5: iteration 2 coreg ─────────────────────────────────────────────────
if should_run 5 "$FRAMES_DONE_FLAG" "Iteration 2 coreg"; then
    echo ""; echo "── STEP 5: Iteration 2 coreg..."
    step_start
    run_fs "
        cd /output/$SUBJECT
        for i in \$(seq 0 $((NFRAMES-1))); do
            (mri_coreg --mov ${FRAME_PFX}_\${i}.nii --ref ${FRAME_PFX}_mean2.nii --no-ref-mask \
                --reg ${FRAME_PFX}_\${i}_iter2.lta --sep $SPM_SEP --ref-fwhm $SPM_FWHM \
                --threads 2 > /dev/null 2>&1 && \
             mri_vol2vol --mov ${FRAME_PFX}_\${i}.nii --reg ${FRAME_PFX}_\${i}_iter2.lta \
                --targ ${FRAME_PFX}_mean2.nii --interp $SPM_INTERP \
                --o ${FRAME_PFX}_\${i}_aligned2.nii > /dev/null 2>&1) &
        done
        wait
        NGOT=\$(ls ${FRAME_PFX}_*_aligned2.nii 2>/dev/null | wc -l)
        echo \"Aligned frames (iter2): \$NGOT/$NFRAMES\"
        if [ \"\$NGOT\" -ne $NFRAMES ]; then
            echo \"ERROR: expected $NFRAMES aligned frames (iter2), generated \$NGOT\" >&2
            exit 1
        fi
    "
    step_end "STEP 5: Iteration 2 coreg"; echo "  iteration 2 done ✅"
fi

# ── STEP 6: sum frames ────────────────────────────────────────────────────────
if should_run 6 "$PET_SUMMED_RAW" "Sum frames"; then
    echo ""; echo "── STEP 6: Summing aligned frames..."
    step_start
    run_fs "
        cd /output/$SUBJECT
        mri_concat \$(for i in \$(seq 0 $((NFRAMES-1))); do echo ${FRAME_PFX}_\${i}_aligned2.nii; done) \
            --sum --o $PET_SUMMED_RAW > /dev/null 2>&1
    "
    step_end "STEP 6: Sum frames"; echo "  $PET_SUMMED_RAW ✅"

    MEAN_CHECK=$($PYTHON -c "
import nibabel as nib, numpy as np
d = nib.load('$SUBJECT_DIR/$PET_SUMMED_RAW').get_fdata()
print(float(np.mean(d[d>0])))" 2>/dev/null)
    echo "  mean intensity (>0): $MEAN_CHECK"
    $PYTHON -c "exit(0 if float('$MEAN_CHECK') > 500 else 1)" 2>/dev/null || \
        echo "  ⚠️  WARNING: unusual intensity scale ($MEAN_CHECK) -- probably different reconstruction units. The pipeline continues normally; STEP 18 uses a percentile-based relative threshold that does not depend on the scale."
fi

# ── STEP 7: cleanup ───────────────────────────────────────────────────────────
if should_run 7 "$FRAMES_DONE_FLAG" "Cleanup"; then
    echo ""; echo "── STEP 7: Cleaning up temporary files..."
    step_start
    run_fs "
        cd /output/$SUBJECT
        rm -f ${FRAME_PFX}_*.nii ${FRAME_PFX}_*.lta ${FRAME_PFX}_mean.nii ${FRAME_PFX}_mean2.nii
        touch $FRAMES_DONE_FLAG
    "
    step_end "STEP 7: Cleanup"; echo "  cleanup done ✅"
fi

# ── STEP 8: coreg PET -> MRI (best of N runs) -- local Python ─────────────────
if should_run 8 "$LTA_P2M" "mri_coreg PET->MRI (best of $COREG_RUNS)"; then
    echo ""; echo "── STEP 8: Coregistering PET -> MRI (best of $COREG_RUNS runs)..."
    step_start
    COREG_LOG_DIR="$SUBJECT_DIR/.coreg_runs${PET_SUFFIX}"
    mkdir -p "$COREG_LOG_DIR"
    SEEDS=(42 1234 9999 31415 777777)
    BEST_COST=999999
    BEST_LTA=""

    for i in $(seq 1 $COREG_RUNS); do
        LTA_I="$COREG_LOG_DIR/${LTA_P2M%.lta}_run${i}.lta"
        COST_I="$COREG_LOG_DIR/coreg_run${i}.cost"
        printf "  run %d/%d (seed=%d) ... " $i $COREG_RUNS ${SEEDS[$((i-1))]}

        run_fs "
            cd /output/$SUBJECT
            mri_coreg --s $SUBJECT --mov $PET_SUMMED_RAW \
                --ref nu.mgz --no-ref-mask \
                --reg /output/$SUBJECT/.coreg_runs${PET_SUFFIX}/${LTA_P2M%.lta}_run${i}.lta \
                --final-cost /output/$SUBJECT/.coreg_runs${PET_SUFFIX}/coreg_run${i}.cost \
                --seed ${SEEDS[$((i-1))]} --threads 4 > /dev/null 2>&1
        " || true

        [ ! -f "$COST_I" ] && printf "ERROR\n" && continue
        COST=$(cat "$COST_I" | tr -d '[:space:]')
        [ -z "$COST" ] && printf "empty cost\n" && continue
        printf "cost = %s\n" "$COST"

        IS_BETTER=$($PYTHON -c "print(1 if float('$COST') < float('$BEST_COST') else 0)" 2>/dev/null)
        [ "$IS_BETTER" == "1" ] && BEST_COST=$COST && BEST_LTA=$LTA_I
    done

    [ -z "$BEST_LTA" ] && echo "ERROR: no run produced a valid cost" && exit 1
    cp "$BEST_LTA" "$SUBJECT_DIR/$LTA_P2M"
    echo "  Best cost: $BEST_COST -- $LTA_P2M ✅"

    COST_OK=$($PYTHON -c "print(1 if -1.3 < $BEST_COST < -0.8 else 0)" 2>/dev/null)
    if [ "$COST_OK" != "1" ]; then
        echo "  ⚠️  WARNING: unusual best coregistration cost ($BEST_COST, expected ~-1.07 to -1.10, limits -1.3/-0.8) -- inspect the registration manually in STEP 9"
    else
        echo "  cost $BEST_COST within the expected range (limits: -1.3 to -0.8; typical: ~-1.07 to -1.10)"
    fi

    step_end "STEP 8: mri_coreg PET->MRI"
fi

# ── STEP 9: QC ───────────────────────────────────────────────────────────────
echo ""; echo "── STEP 9: QC -- check manually (requires GUI)"

# ── STEP 10: reslice PET to MRI ──────────────────────────────────────────────
# Nearest-neighbour interpolation is used so that voxel intensities are not
# smoothed when resampling the summed PET into MRI space.
if should_run 10 "$PET_SUMMED_R" "mri_vol2vol PET->MRI"; then
    echo ""; echo "── STEP 10: Reslicing PET to MRI space..."
    step_start
    run_fs "
        cd /output/$SUBJECT
        mri_vol2vol --mov $PET_SUMMED_RAW --reg $LTA_P2M \
            --targ mri/nu.mgz --interp nearest --o $PET_SUMMED_R > /dev/null 2>&1
    "
    step_end "STEP 10: mri_vol2vol PET->MRI"; echo "  $PET_SUMMED_R ✅"
fi

# ── STEP 11: invert transform ─────────────────────────────────────────────────
if should_run 11 "$LTA_M2P" "lta_convert invert"; then
    echo ""; echo "── STEP 11: Inverting transform..."
    step_start
    run_fs "
        cd /output/$SUBJECT
        lta_convert --inlta $LTA_P2M --outlta $LTA_M2P --invert > /dev/null 2>&1
    "
    step_end "STEP 11: lta_convert invert"; echo "  $LTA_M2P ✅"
fi

# ── STEP 12: rnu for QC ───────────────────────────────────────────────────────
if should_run 12 "$RNU_NII" "rnu.nii QC"; then
    echo ""; echo "── STEP 12: Generating rnu.nii..."
    step_start
    run_fs "
        cd /output/$SUBJECT
        mri_vol2vol --mov mri/nu.mgz --reg $LTA_M2P \
            --targ $PET_SUMMED_RAW --interp trilin --o $RNU_NII > /dev/null 2>&1
    "
    step_end "STEP 12: rnu.nii"; echo "  $RNU_NII ✅"
fi

# ── STEP 13: aparc+aseg to PET space ─────────────────────────────────────────
if should_run 13 "$RAPARC_NII" "raparc+aseg.nii"; then
    echo ""; echo "── STEP 13: Projecting aparc+aseg to PET space..."
    step_start
    run_fs "
        cd /output/$SUBJECT
        mri_vol2vol --mov mri/aparc+aseg.mgz --reg $LTA_M2P \
            --targ $PET_SUMMED_RAW --interp nearest --o $RAPARC_NII > /dev/null 2>&1
    "
    step_end "STEP 13: raparc+aseg.nii"; echo "  $RAPARC_NII ✅"
fi

# ── STEP 13b: pons (brainstem) to PET space -- FDG ONLY ──────────────────────
# Same pattern as STEP 13 but for brainstemSsLabels (STEP 0c). It does not
# touch aparc+aseg or any file of the FTP branch.
RBSTEM_NII="mri/rbrainstemSsLabels${PET_SUFFIX}.nii"
if [ "$TRACER" == "FDG" ]; then
    if should_run 13 "$RBSTEM_NII" "rbrainstemSsLabels.nii"; then
        echo ""; echo "── STEP 13b: Projecting brainstemSsLabels (pons) to PET space..."
        step_start
        run_fs "
            cd /output/$SUBJECT
            mri_vol2vol --mov mri/brainstemSsLabels.v13.FSvoxelSpace.mgz --reg $LTA_M2P \
                --targ $PET_SUMMED_RAW --interp nearest --o $RBSTEM_NII > /dev/null 2>&1
        "
        step_end "STEP 13b: rbrainstemSsLabels.nii"; echo "  $RBSTEM_NII ✅"
    fi
fi

# ── STEP 14: mri_segstats ─────────────────────────────────────────────────────
if should_run 14 "$OUTPUT_CSV" "mri_segstats no-PVC"; then
    echo ""; echo "── STEP 14: mri_segstats (no-PVC)..."
    step_start
    run_fs "
        cd /output/$SUBJECT
        mri_segstats --seg $RAPARC_NII --i $PET_SUMMED_RAW \
            --sum $OUTPUT_CSV --ctab \$FREESURFER_HOME/FreeSurferColorLUT.txt > /dev/null 2>&1
    "
    step_end "STEP 14: mri_segstats"

    NROWS_CSV=$(grep -vc '^#' "$SUBJECT_DIR/$OUTPUT_CSV" 2>/dev/null || echo 0)
    # recon-all produces a more complete segmentation than FastSurfer (~109
    # regions vs 107; the extra ones are legitimate structures outside the tau
    # analysis: WM-hypointensities, Optic-Chiasm, etc). The gate is only a
    # warning; it aborts only if the count is clearly broken (<100).
    if [ "$NROWS_CSV" -lt 100 ]; then
        echo "  ❌ ERROR: $OUTPUT_CSV has only $NROWS_CSV rows (<100) -- broken segmentation"
        exit 1
    elif [ "$NROWS_CSV" -ne 107 ]; then
        echo "  ⚠️  WARNING: $OUTPUT_CSV has $NROWS_CSV regions (FastSurfer gives 107; recon-all usually gives ~109) -- acceptable"
    fi
    echo "  $OUTPUT_CSV ✅ ($NROWS_CSV regions)"
fi

# ── STEP 14b: mri_segstats on pons/brainstem -- FDG ONLY ───────────────────
# FDG reference region (pons = label 174 of brainstemSsLabels). Same pattern as
# STEP 14 but on the brainstem mask instead of aparc+aseg. The SUVR
# (target/pons) is computed downstream (evaluate_subject.py), dividing the
# target-region row of $OUTPUT_CSV by the pons row (label 174) of this file,
# in the same way the cerebellum division is done for tau.
OUTPUT_BSTEM_CSV="output_brainstem${PET_SUFFIX}.csv"
if [ "$TRACER" == "FDG" ]; then
    if should_run 14 "$OUTPUT_BSTEM_CSV" "mri_segstats pons/brainstem"; then
        echo ""; echo "── STEP 14b: mri_segstats (pons/brainstem)..."
        step_start
        run_fs "
            cd /output/$SUBJECT
            mri_segstats --seg $RBSTEM_NII --i $PET_SUMMED_RAW \
                --sum $OUTPUT_BSTEM_CSV --ctab \$FREESURFER_HOME/FreeSurferColorLUT.txt > /dev/null 2>&1
        "
        step_end "STEP 14b: mri_segstats pons"

        PONS_ROW=$(grep -v '^#' "$SUBJECT_DIR/$OUTPUT_BSTEM_CSV" 2>/dev/null | awk '$2==174')
        if [ -z "$PONS_ROW" ]; then
            echo "  ❌ ERROR: label 174 (pons) not found in $OUTPUT_BSTEM_CSV -- check segmentBS.sh"
            exit 1
        fi
        echo "  $OUTPUT_BSTEM_CSV ✅ (pons: $(echo $PONS_ROW | awk '{print $6}') mean intensity)"
    fi
fi

# ── STEP 15: gtmseg (FTP ONLY -- FDG does not use PVC) ──────────────────────────────
if [ "$TRACER" == "FDG" ]; then
    echo ""; echo "── STEPS 15-20: skipped -- FDG does not use PVC"
fi
if [ "$TRACER" == "FTP" ] && should_run 15 "mri/gtmseg.mgz" "gtmseg"; then
    echo ""; echo "── STEP 15: gtmseg..."
    step_start
    run_fs "
        export SUBJECTS_DIR=/output
        cd /output/$SUBJECT
        gtmseg --s $SUBJECT --usf 1 --output-usf 1 --xcerseg > /dev/null 2>&1
    "
    step_end "STEP 15: gtmseg"

    NLABELS=$($PYTHON -c "
import nibabel as nib, numpy as np
d = nib.load('$SUBJECT_DIR/mri/gtmseg.mgz').get_fdata()
print(len(np.unique(d[d>0])))" 2>/dev/null)
    # gtmseg on a recon-all segmentation can yield more labels than the 107 of
    # FastSurfer. The gate is only a warning; it aborts only if <100.
    if [ "$NLABELS" -lt 100 ]; then
        echo "  ❌ ERROR: gtmseg.mgz has only $NLABELS labels (<100) -- broken segmentation"
        exit 1
    elif [ "$NLABELS" -ne 107 ]; then
        echo "  ⚠️  WARNING: gtmseg.mgz has $NLABELS labels (FastSurfer gives 107) -- acceptable"
    fi
    echo "  gtmseg.mgz ✅ ($NLABELS labels)"
fi

# ── STEP 16: reslice gtmseg (FTP ONLY) ────────────────────────────────────────
if [ "$TRACER" == "FTP" ] && should_run 16 "mri/gtmseg_256.mgz" "gtmseg_256.mgz"; then
    echo ""; echo "── STEP 16: Reslicing gtmseg..."
    step_start
    run_fs "
        cd /output/$SUBJECT
        mri_vol2vol --mov mri/gtmseg.mgz --targ mri/orig.mgz \
            --regheader --interp nearest --o mri/gtmseg_256.mgz > /dev/null 2>&1
        cp mri/gtmseg.ctab mri/gtmseg_256.ctab
    "
    step_end "STEP 16: gtmseg_256.mgz"; echo "  gtmseg_256.mgz ✅"
fi

# ── STEP 17: identity LTA (FTP ONLY) ──────────────────────────────────────────
if [ "$TRACER" == "FTP" ] && should_run 17 "PET_T1_identity.lta" "PET_T1_identity.lta"; then
    echo ""; echo "── STEP 17: Generating identity LTA..."
    step_start
    run_fs "
        cd /output/$SUBJECT
        lta_convert --inlta identity.nofile --src rtau_pet_summed.nii \
            --trg mri/gtmseg_256.mgz --outlta PET_T1_identity.lta > /dev/null 2>&1
    "
    step_end "STEP 17: PET_T1_identity.lta"; echo "  PET_T1_identity.lta ✅"
fi

# ── STEP 18: brain mask -- local Python (FTP ONLY) ────────────────────────────
if [ "$TRACER" == "FTP" ] && should_run 18 "rPET_bin.nii" "brain mask"; then
    echo ""; echo "── STEP 18: Generating brain mask (auto threshold)..."
    step_start

    STATS=$($PYTHON -c "
import nibabel as nib, numpy as np
img = nib.load('$SUBJECT_DIR/rtau_pet_summed.nii')
data = img.get_fdata()
pos = data[data > 0]
print(float(np.mean(pos)), float(np.percentile(pos, 95)))" 2>/dev/null)
    MEAN_VAL=$(echo $STATS | awk '{print $1}')
    P95_VAL=$(echo $STATS | awk '{print $2}')

    if [ -z "$P95_VAL" ]; then
        echo "  ❌ ERROR: could not compute intensity for $SUBJECT"; exit 1
    fi

    # relative threshold (95th percentile), no absolute floor -- invariant to the PET scale
    AUTO_THRESHOLD=$($PYTHON -c "print(round(float('$P95_VAL') * 0.10, 4))")
    echo "  threshold: $AUTO_THRESHOLD (10% of the 95th percentile=$P95_VAL; mean=$MEAN_VAL)"

    BIN_LOG="$SUBJECT_DIR/.step18_binarize.log"
    set +e
    run_fs "cd /output/$SUBJECT && mri_binarize --i rtau_pet_summed.nii --min $AUTO_THRESHOLD --o rPET_bin.nii" > "$BIN_LOG" 2>&1
    BIN_STATUS=$?
    set -e
    if [ $BIN_STATUS -ne 0 ]; then
        echo "  ❌ ERROR: mri_binarize failed (exit $BIN_STATUS) for $SUBJECT"
        tail -20 "$BIN_LOG"
        exit 1
    fi
    echo "  mri_binarize finished OK (exit 0)"

    # sanity check: the mask must be neither nearly empty nor nearly the whole FOV (limits: 0.15-0.40)
    FRAC=$($PYTHON -c "
import nibabel as nib, numpy as np
d = nib.load('$SUBJECT_DIR/rPET_bin.nii').get_fdata()
print(round(float(np.mean(d > 0)), 4))")
    PASS=$($PYTHON -c "print(1 if 0.15 < $FRAC < 0.40 else 0)")
    if [ "$PASS" != "1" ]; then
        echo "  ❌ ERROR: implausible mask for $SUBJECT ($FRAC of the FOV, limits 0.15-0.40) -- aborting"
        exit 1
    fi
    echo "  mask fraction: $FRAC (limits: 0.15-0.40)"

    # IoU vs brainmask.mgz -- informational, complements (does not replace) the fraction check
    IOU=$($PYTHON -c "
import nibabel as nib, numpy as np
pet_mask = nib.load('$SUBJECT_DIR/rPET_bin.nii').get_fdata() > 0
brain = nib.load('$SUBJECT_DIR/mri/brainmask.mgz').get_fdata() > 0
if pet_mask.shape != brain.shape:
    print('NA')
else:
    inter = np.logical_and(pet_mask, brain).sum()
    union = np.logical_or(pet_mask, brain).sum()
    print(round(inter/union, 4) if union > 0 else 0.0)" 2>/dev/null)
    echo "  IoU vs brainmask.mgz: $IOU (informational, no automatic gate -- inspect manually if it is very low)"

    step_end "STEP 18: brain mask"
    echo "  rPET_bin.nii ✅ (${FRAC} of the FOV)"
fi

# ── STEP 19: nu.nii (FTP ONLY) ────────────────────────────────────────────────
if [ "$TRACER" == "FTP" ] && should_run 19 "mri/nu.nii" "nu.nii"; then
    echo ""; echo "── STEP 19: Converting nu.mgz to nu.nii..."
    step_start
    run_fs "
        cd /output/$SUBJECT
        mri_convert mri/nu.mgz mri/nu.nii > /dev/null 2>&1
    "
    step_end "STEP 19: nu.nii"; echo "  mri/nu.nii ✅"
fi

# ── STEP 20: mri_gtmpvc (FTP ONLY) ────────────────────────────────────────────
if [ "$TRACER" == "FTP" ] && should_run 20 "gtmpvc_T1space_mask.output/gtm.stats.dat" "mri_gtmpvc PVC"; then
    echo ""; echo "── STEP 20: mri_gtmpvc (PVC)..."
    step_start

    GTMPVC_LOG="$SUBJECT_DIR/.gtmpvc_step20.log"
    set +e
    run_fs "
        cd /output/$SUBJECT
        mri_gtmpvc --i rtau_pet_summed.nii --reg PET_T1_identity.lta \
            --psf 6 --seg mri/gtmseg_256.mgz --mask rPET_bin.nii \
            --mgx 0.01 --default-seg-merge --rescale 8 47 \
            --o gtmpvc_T1space_mask.output
    " > "$GTMPVC_LOG" 2>&1
    GTMPVC_STATUS=$?
    set -e

    if [ $GTMPVC_STATUS -ne 0 ]; then
        echo "  ❌ ERROR: mri_gtmpvc failed (exit $GTMPVC_STATUS) for $SUBJECT"
        echo "     last lines of the log ($GTMPVC_LOG):"
        tail -20 "$GTMPVC_LOG"
        exit 1
    fi
    echo "  mri_gtmpvc finished OK (exit 0)"

    STATS_FILE="$SUBJECT_DIR/gtmpvc_T1space_mask.output/gtm.stats.dat"
    if [ ! -s "$STATS_FILE" ]; then
        echo "  ❌ ERROR: gtm.stats.dat was not generated or is empty for $SUBJECT"
        exit 1
    fi

    NROWS=$(wc -l < "$STATS_FILE")
    if [ "$NROWS" -lt 90 ]; then
        echo "  ❌ ERROR: gtm.stats.dat has only $NROWS rows (expected 100) -- suspicious, check"
        exit 1
    elif [ "$NROWS" -ne 100 ]; then
        echo "  ⚠️  WARNING: gtm.stats.dat has $NROWS rows (expected 100) -- check whether a structure is missing"
    fi

    step_end "STEP 20: mri_gtmpvc"
    echo "  gtmpvc_T1space_mask.output ✅ ($NROWS regions)"
fi

# ── FINAL SUMMARY ─────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Pipeline complete for $SUBJECT ($TRACER_LABEL)"
pipeline_end
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "── Outputs ──────────────────────────────────────────"
check_file "$PET_SUMMED_RAW"                          "$PET_SUMMED_RAW"
check_file "$PET_SUMMED_R"                            "$PET_SUMMED_R"
check_file "$LTA_P2M"                                 "$LTA_P2M"
check_file "$LTA_M2P"                                 "$LTA_M2P"
check_file "$RNU_NII"                                 "$RNU_NII"
check_file "$RAPARC_NII"                              "$RAPARC_NII"
check_file "$OUTPUT_CSV"                              "$OUTPUT_CSV (target regions, raw)"
if [ "$TRACER" == "FDG" ]; then
    check_file "mri/brainstemSsLabels.v13.FSvoxelSpace.mgz" "brainstemSsLabels (pons)"
    check_file "$RBSTEM_NII"                          "$RBSTEM_NII"
    check_file "$OUTPUT_BSTEM_CSV"                    "$OUTPUT_BSTEM_CSV (pons, raw)"
else
    check_file "mri/gtmseg.mgz"                           "mri/gtmseg.mgz"
    check_file "mri/gtmseg_256.mgz"                       "mri/gtmseg_256.mgz"
    check_file "PET_T1_identity.lta"                      "PET_T1_identity.lta"
    check_file "rPET_bin.nii"                             "rPET_bin.nii"
    check_file "mri/nu.nii"                               "mri/nu.nii"
    check_file "gtmpvc_T1space_mask.output/gtm.stats.dat" "gtmpvc_T1space_mask.output"
fi
echo ""
echo "── Pending ──────────────────────────────────────────"
echo "  ⚠️  STEP 9 -- QC coregistration (requires GUI, do it locally):"
echo "     tkregisterfv --mov $PET_SUMMED_RAW \\"
echo "         --reg $LTA_P2M \\"
echo "         --s $SUBJECT --surfs"
if [ "$TRACER" == "FDG" ]; then
    echo ""
    echo "  ℹ️  The FDG SUVR is computed by evaluate_subject.py: target mean / pons mean (label 174, $OUTPUT_BSTEM_CSV)."
fi
echo ""
echo "── Rewrite options ──────────────────────────────────"
echo "  bash run_public_pipeline.sh $SUBJECT --tracer $TRACER --rewrite 8"
echo "  bash run_public_pipeline.sh $SUBJECT --tracer $TRACER --rewrite all"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Comparison with the published values (optional) ──────────────────────────
# If the subject is in data/ of the public package, your value is compared with
# the published one; otherwise only your output is reported (no comparison).
EVAL_PY="$(dirname "${BASH_SOURCE[0]}")/evaluate_subject.py"
if [ "$TRACER" == "FTP" ]; then EVAL_TYPE="tau"; else EVAL_TYPE="fdg"; fi
if [ "$EVAL_TYPE" == "fdg" ] && [ -z "${FSROI_LIST_USER_SET:-}" ] && [ -n "${PUBLIC_PACKAGE:-}" ]; then
    FSROI_LIST="$PUBLIC_PACKAGE/data/rois_fdg.csv"
fi
echo ""
echo "── Comparison with the published values ──────────────"
if [ -f "$EVAL_PY" ]; then
    "$PYTHON" "$EVAL_PY" --type "$EVAL_TYPE" --package "$PUBLIC_PACKAGE" \
        --output_dir "$SUBJECTS_DIR" --subject "$SUBJECT" \
        --fsroi-list "$FSROI_LIST" --lut "$FS_LUT" \
        --output "$SUBJECT_DIR/evaluation_$EVAL_TYPE" \
        || echo "  ⚠️  evaluate_subject.py finished with an error (the processing itself is complete)"
else
    echo "  (skipped) evaluate_subject.py not found next to this script."
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
