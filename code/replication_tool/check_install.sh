#!/bin/bash
# check_install.sh -- verify that everything run_public_pipeline.sh needs is installed and in place.
# Reads the same variables (and the same defaults) as run_public_pipeline.sh, so it checks exactly what the
# pipeline will actually use on this machine. Does not run any PET processing; only checks presence.
#
# Usage:  bash check_install.sh [--tracer FTP|FDG]
# Exit code: 0 if every required check passed (optional checks only warn), 1 otherwise.

case "${1:-}" in
    -h|--help)
        cat <<USAGE
Usage: bash check_install.sh [--tracer FTP|FDG]

Verifies that everything run_public_pipeline.sh needs is installed and in
place: Docker, the FreeSurfer/FastSurfer images, the FreeSurfer license, the
MCR runtime, the Python virtualenv and its packages, MATLAB+SPM12/SPM standalone, the helper scripts, and
(for comparing against published values) FS_LUT/FSROI_LIST. Does not run any
PET processing -- only checks presence. Reads the same variables and the
same defaults as run_public_pipeline.sh, so it checks exactly what the
pipeline will use on this machine.

  --tracer FTP|FDG   Which tracer's FSROI_LIST default to check. Default: FTP.
  -h, --help         Show this help and exit.

Exit code: 0 if every required check passed (optional checks only warn), 1 otherwise.
USAGE
        exit 0
        ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRACER="FTP"
[ "$1" == "--tracer" ] && TRACER="${2:-FTP}"

# ── same configuration as run_public_pipeline.sh ───────────────────────────────
PETPIPELINE_BASE="${PETPIPELINE_BASE:-$(cd "$SCRIPT_DIR/../.." && pwd)/pet_pipeline}"  # defaults to this repo's own pet_pipeline/ folder
MRI_DATA_DIR="${MRI_DATA_DIR:-$PETPIPELINE_BASE/mri_data}"
SUBJECTS_DIR="$PETPIPELINE_BASE/output"
FS_LICENSE_DIR="$PETPIPELINE_BASE/fs_license"
FASTSURFER_IMAGE="deepmi/fastsurfer:cu126-v2.4.2"
FREESURFER_IMAGE="freesurfer/freesurfer:7.4.1"
PYTHON="${PYTHON:-$HOME/.venv_pet_pipeline/bin/python3}"
PUBLIC_PACKAGE="${PUBLIC_PACKAGE:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
# FreeSurferColorLUT.txt is not shipped with this repo: prefer a copy kept inside PETPIPELINE_BASE
# (same convention as MCRv97 and the SPM standalone), otherwise fall back to ~/freesurfer.
if [ -z "${FS_LUT:-}" ]; then
    if [ -f "$PETPIPELINE_BASE/FreeSurferColorLUT.txt" ]; then
        FS_LUT="$PETPIPELINE_BASE/FreeSurferColorLUT.txt"
    else
        FS_LUT="$HOME/freesurfer/FreeSurferColorLUT.txt"
    fi
fi
if [ "$TRACER" == "FDG" ]; then
    FSROI_LIST="${FSROI_LIST:-$PUBLIC_PACKAGE/data/rois_fdg.csv}"
else
    FSROI_LIST="${FSROI_LIST:-$PUBLIC_PACKAGE/data/rois_ftp.csv}"
fi
MCR_DIR="${MCR_DIR:-$PETPIPELINE_BASE/MCRv97}"               # same variable as run_public_pipeline.sh

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
    bad "license NOT found at $FS_LICENSE_DIR/.license -- see docs/INSTALL.md section 3 (FS_LICENSE_DIR derives from PETPIPELINE_BASE=$PETPIPELINE_BASE)"
fi

# 4. MCR (needed for FDG's segmentBS.sh; also used whenever classic recon-all runs the brainstem step)
#    Checks the two specific files Docker's freesurfer image actually loads, not just that the
#    folder is non-empty -- a non-empty folder can still be missing one of them (partial install)
#    or have them nested one level too deep (installer's own v97 subfolder quirk).
echo ""; echo "── Matlab Compiled Runtime (MCR v97)"
MCR_LAUNCHER="$MCR_DIR/bin/glnxa64/libmwlaunchermain.so"
MCR_RUNTIME="$MCR_DIR/runtime/glnxa64/libmwmclmcrrt.so.9.7"
MCR_LAUNCHER_NESTED="$MCR_DIR/v97/bin/glnxa64/libmwlaunchermain.so"
MCR_RUNTIME_NESTED="$MCR_DIR/v97/runtime/glnxa64/libmwmclmcrrt.so.9.7"
if [ -f "$MCR_LAUNCHER" ] && [ -f "$MCR_RUNTIME" ]; then
    ok "MCR completo en $MCR_DIR (launcher y runtime library presentes)"
elif [ -f "$MCR_LAUNCHER_NESTED" ] || [ -f "$MCR_RUNTIME_NESTED" ]; then
    bad "MCR anidado un nivel de mas en $MCR_DIR/v97 -- el instalador siempre crea su propia subcarpeta v97; muevela: mv \"$MCR_DIR/v97\"/* \"$MCR_DIR/\" && rmdir \"$MCR_DIR/v97\" -- ver docs/INSTALL.md seccion 4"
elif [ -d "$MCR_DIR" ] && [ -n "$(ls -A "$MCR_DIR" 2>/dev/null)" ]; then
    MISSING=""
    [ -f "$MCR_LAUNCHER" ] || MISSING="$MISSING bin/glnxa64/libmwlaunchermain.so"
    [ -f "$MCR_RUNTIME" ]  || MISSING="$MISSING runtime/glnxa64/libmwmclmcrrt.so.9.7"
    bad "MCR in $MCR_DIR is incomplete (partial/failed install) -- missing:$MISSING -- reinstall into a temporary folder and move it into place, see docs/INSTALL.md section 4"
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

# 5b. Centiloid/GAAIN-only Python packages (optional: not needed for Tau/FDG at all)
echo ""; echo "── Centiloid + GAAIN validation packages (optional, only for code/centiloid and code/gaain_validation)"
if [ -f "$PYTHON" ]; then
    if "$PYTHON" -c "import pandas, scipy, matplotlib" >/dev/null 2>&1; then
        ok "pandas, scipy and matplotlib importable (centiloid_pipeline_tracers.py)"
    else
        warn "pandas/scipy/matplotlib NOT importable with this python3 -- only needed for Centiloid; run: $PYTHON -m pip install pandas scipy matplotlib"
    fi
    if "$PYTHON" -c "import openpyxl" >/dev/null 2>&1; then
        ok "openpyxl importable (klunk_gaain_validation_plot.py)"
    else
        warn "openpyxl NOT importable with this python3 -- only needed for the GAAIN validation plot; run: $PYTHON -m pip install openpyxl"
    fi
else
    warn "skipped (python3 not found at $PYTHON -- see the Python virtualenv check above)"
fi

# 5c. Centiloid: MATLAB+SPM12 or SPM standalone (optional, only for code/centiloid)
echo ""; echo "-- Centiloid: MATLAB+SPM12 or SPM standalone (optional, only for code/centiloid)"
# Same version-scan as centiloid_pipeline_tracers.py: don't assume one exact
# MATLAB/MATLAB Runtime version, pick the newest one actually installed
# (ls -d sorts release names like R2022b/R2023a correctly; 2>/dev/null
# silences "no match" when nothing is installed yet).
if [ -z "${CENTILOID_MATLAB_BIN:-}" ]; then
    CENTILOID_MATLAB_BIN="$(ls -d /opt/MATLAB/R*/bin/matlab /usr/local/MATLAB/R*/bin/matlab 2>/dev/null | sort | tail -n1)"
fi
CENTILOID_MATLAB_BIN="${CENTILOID_MATLAB_BIN:-/opt/MATLAB/R2022b/bin/matlab}"
CENTILOID_SPM12_PATH="${CENTILOID_SPM12_PATH:-$(dirname "$(dirname "$CENTILOID_MATLAB_BIN")")/toolbox/spm12}"
# SPM standalone + MATLAB Runtime: looked for inside $PETPIPELINE_BASE (same
# convention as MCR_DIR above) and, for the Runtime, also in
# /usr/local/MATLAB/MATLAB_Runtime. Any SPM version works (SPM12, SPM25,
# SPM26, ...); the launcher script is named after its own version
# (run_spm12.sh, run_spm25.sh, run_spm26.sh, ...), so this globs for
# run_spm*.sh instead of hardcoding one literal filename.
if [ -z "${CENTILOID_SPM_STANDALONE_RUN:-}" ]; then
    CENTILOID_SPM_STANDALONE_RUN="$(ls "$PETPIPELINE_BASE"/spm12_standalone/run_spm*.sh 2>/dev/null | sort | tail -n1)"
fi
# Older MATLAB Runtime installers nest a version-code subfolder (R2022b/v913);
# newer ones (seen on R2026a) install directly into the release folder
# (R2026a/bin, no v9XX level) -- try the v* pattern first (more specific),
# then fall back to any release folder that has a bin/ directly inside it.
if [ -z "${CENTILOID_SPM_MCR_DIR:-}" ]; then
    CENTILOID_SPM_MCR_DIR="$(ls -d "$PETPIPELINE_BASE"/spm12_standalone/MATLAB_Runtime/R*/v* /usr/local/MATLAB/MATLAB_Runtime/R*/v* 2>/dev/null | sort | tail -n1)"
fi
if [ -z "${CENTILOID_SPM_MCR_DIR:-}" ]; then
    CENTILOID_SPM_MCR_DIR="$(ls -d "$PETPIPELINE_BASE"/spm12_standalone/MATLAB_Runtime/R*/bin /usr/local/MATLAB/MATLAB_Runtime/R*/bin 2>/dev/null | sed 's:/bin$::' | sort | tail -n1)"
fi
if [ -f "$CENTILOID_SPM_STANDALONE_RUN" ] && [ -d "$CENTILOID_SPM_MCR_DIR" ]; then
    ok "SPM standalone found ($CENTILOID_SPM_STANDALONE_RUN + $CENTILOID_SPM_MCR_DIR) -- no MATLAB license needed, centiloid_pipeline_tracers.py will use this"
elif [ -f "$CENTILOID_MATLAB_BIN" ] && [ -d "$CENTILOID_SPM12_PATH" ]; then
    ok "MATLAB + SPM12 found ($CENTILOID_MATLAB_BIN + $CENTILOID_SPM12_PATH)"
else
    warn "neither SPM standalone (searched $PETPIPELINE_BASE/spm12_standalone and /usr/local/MATLAB/MATLAB_Runtime) nor MATLAB+SPM12 ($CENTILOID_MATLAB_BIN) found -- only needed for Centiloid; see docs/INSTALL.md section 8"
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
