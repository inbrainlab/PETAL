#!/bin/bash
# check_install.sh -- verify that everything run_public_pipeline.sh needs is installed and in place.
# Reads the same variables (and the same defaults) as run_public_pipeline.sh, so it checks exactly what the
# pipeline will actually use on this machine. Does not run any PET processing; only checks presence.
#
# Usage:  bash check_install.sh [--tracer FTP|FDG]
# Exit code: 0 if every required check passed (optional checks only warn), 1 otherwise.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRACER="FTP"
[ "$1" == "--tracer" ] && TRACER="${2:-FTP}"

# ── same configuration as run_public_pipeline.sh ───────────────────────────────
FASTSURFER_BASE="${FASTSURFER_BASE:-$HOME/pet_pipeline}"
MRI_DATA_DIR="${MRI_DATA_DIR:-$FASTSURFER_BASE/mri_data}"
SUBJECTS_DIR="$FASTSURFER_BASE/output"
FS_LICENSE_DIR="$FASTSURFER_BASE/fs_license"
FASTSURFER_IMAGE="deepmi/fastsurfer:cu126-v2.4.2"
FREESURFER_IMAGE="freesurfer/freesurfer:7.4.1"
PYTHON="${PYTHON:-$HOME/.venv_pet_pipeline/bin/python3}"
PUBLIC_PACKAGE="${PUBLIC_PACKAGE:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
FS_LUT="${FS_LUT:-$HOME/freesurfer/FreeSurferColorLUT.txt}"
if [ "$TRACER" == "FDG" ]; then
    FSROI_LIST="${FSROI_LIST:-$PUBLIC_PACKAGE/data/fdg_config_rois.csv}"
else
    FSROI_LIST="${FSROI_LIST:-$PUBLIC_PACKAGE/data/fsroi_list_FTP.csv}"
fi
MCR_DIR="$FASTSURFER_BASE/MCRv97"   # hardcoded Docker mount path in run_public_pipeline.sh, not a variable (derives from FASTSURFER_BASE)

PASS=0; WARN=0; FAIL=0
ok()   { echo "  OK    $1"; PASS=$((PASS+1)); }
warn() { echo "  WARN  $1"; WARN=$((WARN+1)); }
bad()  { echo "  FAIL  $1"; FAIL=$((FAIL+1)); }

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Checking installation for run_public_pipeline.sh (tracer: $TRACER)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 1. Docker
echo ""; echo "── Docker"
if command -v docker >/dev/null 2>&1; then
    ok "docker command found ($(command -v docker))"
    if docker info >/dev/null 2>&1; then
        ok "docker daemon is reachable"
    else
        bad "docker daemon not reachable (is it running? do you have permission -- check 'docker run --rm hello-world')"
    fi
else
    bad "docker command not found -- see docs/INSTALL.md section 1"
fi

# 2. Docker images
echo ""; echo "── Docker images"
if command -v docker >/dev/null 2>&1; then
    if docker image inspect "$FREESURFER_IMAGE" >/dev/null 2>&1; then
        ok "$FREESURFER_IMAGE present (required, classic recon-all)"
    else
        bad "$FREESURFER_IMAGE NOT found -- run: docker pull $FREESURFER_IMAGE"
    fi
    if docker image inspect "$FASTSURFER_IMAGE" >/dev/null 2>&1; then
        ok "$FASTSURFER_IMAGE present (optional, GPU path)"
    else
        warn "$FASTSURFER_IMAGE not found -- only needed for RECON_METHOD=fastsurfer"
    fi
else
    warn "skipped (docker command not found)"
fi

# 3. FreeSurfer license
echo ""; echo "── FreeSurfer license"
if [ -f "$FS_LICENSE_DIR/.license" ]; then
    ok "license found at $FS_LICENSE_DIR/.license"
else
    bad "license NOT found at $FS_LICENSE_DIR/.license -- see docs/INSTALL.md section 3 (FS_LICENSE_DIR derives from FASTSURFER_BASE=$FASTSURFER_BASE)"
fi

# 4. MCR (needed for FDG's segmentBS.sh; also used whenever classic recon-all runs the brainstem step)
echo ""; echo "── Matlab Compiled Runtime (MCR v97)"
if [ -d "$MCR_DIR" ] && [ -n "$(ls -A "$MCR_DIR" 2>/dev/null)" ]; then
    ok "MCR found at $MCR_DIR"
else
    bad "MCR NOT found at $MCR_DIR -- see docs/INSTALL.md section 4"
fi

# 5. Python virtualenv
echo ""; echo "── Python virtualenv (PYTHON=$PYTHON)"
if [ -f "$PYTHON" ]; then
    ok "python3 found at $PYTHON"
    if "$PYTHON" -c "import nibabel, numpy" >/dev/null 2>&1; then
        ok "nibabel and numpy importable"
    else
        bad "nibabel/numpy NOT importable with this python3 -- run: $PYTHON -m pip install nibabel numpy"
    fi
else
    bad "python3 NOT found at $PYTHON -- run: python3 -m venv $(dirname "$(dirname "$PYTHON")") && $PYTHON -m pip install nibabel numpy"
fi

# 6. progress_helpers.sh / evaluate_subject.py next to this script
echo ""; echo "── Helper scripts next to run_public_pipeline.sh"
[ -f "$SCRIPT_DIR/progress_helpers.sh" ] && ok "progress_helpers.sh present" || bad "progress_helpers.sh missing from $SCRIPT_DIR"
[ -f "$SCRIPT_DIR/evaluate_subject.py" ] && ok "evaluate_subject.py present" || warn "evaluate_subject.py missing -- comparison with published values will be skipped"

# 7. Comparison inputs (optional: only needed to compare against published values)
echo ""; echo "── Comparison with published values (optional)"
[ -f "$FS_LUT" ] && ok "FS_LUT found at $FS_LUT" || warn "FS_LUT not found at $FS_LUT -- see docs/INSTALL.md / extract it from the FreeSurfer image"
[ -f "$FSROI_LIST" ] && ok "FSROI_LIST found at $FSROI_LIST" || warn "FSROI_LIST not found at $FSROI_LIST"
[ -d "$PUBLIC_PACKAGE/data" ] && ok "PUBLIC_PACKAGE/data found at $PUBLIC_PACKAGE/data" || warn "PUBLIC_PACKAGE/data not found at $PUBLIC_PACKAGE/data"

# 8. Subject data folder
echo ""; echo "── Subject data (MRI_DATA_DIR=$MRI_DATA_DIR)"
if [ -d "$MRI_DATA_DIR" ]; then
    N=$(find "$MRI_DATA_DIR" -maxdepth 1 -mindepth 1 -type d | wc -l | tr -d ' ')
    if [ "$N" -gt 0 ]; then
        ok "$N subject folder(s) found directly under $MRI_DATA_DIR"
    else
        warn "$MRI_DATA_DIR exists but has no subject subfolders directly inside it (subjects must be one level deep, not grouped further)"
    fi
else
    bad "$MRI_DATA_DIR does not exist"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "RESULT: $PASS ok, $WARN warning(s), $FAIL failed"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
[ "$FAIL" -eq 0 ]
