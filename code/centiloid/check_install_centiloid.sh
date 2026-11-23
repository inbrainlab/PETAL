#!/bin/bash
# check_install_centiloid.sh -- verify, BEFORE running anything, that everything the Centiloid (amyloid)
# pipeline needs is installed and in place, and say exactly how to fix whatever is not.
# Reads the same variables and defaults as centiloid_pipeline_tracers.py / run_all_A4_florbetapir.sh, so it
# checks what the pipeline will really use on this machine. It does not process any PET.
#
# Usage:  bash code/centiloid/check_install_centiloid.sh [--mode a4|gaain] [--voi_method avid|klunk]
#                                                        [--subject ID] [--test-spm]
# Exit code: 0 if every required check passed (optional checks only warn), 1 otherwise.

usage() {
cat <<'USAGE'
Usage: bash code/centiloid/check_install_centiloid.sh [options]

  --mode a4|gaain       a4    (default) A4 cohort: NIfTI T1/PET per subject, run with run_all_A4_florbetapir.sh
                        gaain GAAIN-style cohort: DICOM folders, run with centiloid_pipeline_tracers.py --all
  --voi_method avid|klunk
                        VOI set to check. Default: $VOI_METHOD if set, otherwise avid (the six Avid VOIs
                        used for A4); klunk = the standard Centiloid VOIs.
  --subject ID          (a4) check only this subject's input files; by default every subject folder is checked.
  --test-spm            actually launch SPM once to prove it starts (takes 1-2 min the first time it runs).
  -h, --help            show this help.

Checks: pipeline files, Python packages, FSL, SPM (standalone or MATLAB+SPM12), SPM templates, VOIs, input data.
Each line is OK, WARN (optional, the pipeline still runs) or FAIL (the pipeline would stop), with the fix.
USAGE
}

MODE="a4"; VOI="${VOI_METHOD:-avid}"; ONLY_SUBJECT=""; TEST_SPM=0
while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help) usage; exit 0 ;;
        --mode) MODE="${2:-}"; shift 2 ;;
        --voi_method) VOI="${2:-}"; shift 2 ;;
        --subject) ONLY_SUBJECT="${2:-}"; shift 2 ;;
        --test-spm) TEST_SPM=1; shift ;;
        *) echo "Unknown option: $1"; usage; exit 2 ;;
    esac
done
case "$MODE" in a4|gaain) ;; *) echo "--mode must be a4 or gaain"; exit 2 ;; esac
case "$VOI" in avid|klunk) ;; *) echo "--voi_method must be avid or klunk"; exit 2 ;; esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# ── same configuration as centiloid_pipeline_tracers.py / run_all_A4_florbetapir.sh ──────────────
PETPIPELINE_BASE="${PETPIPELINE_BASE:-$REPO_ROOT/pet_pipeline}"
BASE_DIR="${CENTILOID_BASE_DIR:-$PETPIPELINE_BASE/centiloid_input}"
A4_DATA_DIR="${A4_DATA_DIR:-$PETPIPELINE_BASE/A4_pipeline_input}"
A4_OUT_DIR="${A4_OUT_DIR:-$PETPIPELINE_BASE/A4_pipeline_output}"
PYTHON="${PYTHON:-$HOME/.venv_pet_pipeline/bin/python3}"

PASS=0; WARN=0; FAIL=0
ok()   { echo "  OK    $1"; PASS=$((PASS+1)); }
warn() { echo "  WARN  $1"; WARN=$((WARN+1)); shift; for l in "$@"; do echo "          -> $l"; done; }
bad()  { echo "  FAIL  $1"; FAIL=$((FAIL+1)); shift; for l in "$@"; do echo "          -> $l"; done; }
sec()  { echo ""; echo "── $1"; }

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Checking installation for the Centiloid pipeline (mode: $MODE, VOIs: $VOI)"
echo "  working directory (PETPIPELINE_BASE): $PETPIPELINE_BASE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 1. pipeline files ──────────────────────────────────────────────────────────────────────────
sec "Pipeline files"
if [ -f "$SCRIPT_DIR/centiloid_pipeline_tracers.py" ]; then ok "centiloid_pipeline_tracers.py present"
else bad "centiloid_pipeline_tracers.py NOT found next to this script ($SCRIPT_DIR)" \
         "The repository is incomplete: download it again (do not copy only part of code/)."; fi
if [ "$MODE" == "a4" ]; then
    if [ -f "$SCRIPT_DIR/run_all_A4_florbetapir.sh" ]; then ok "run_all_A4_florbetapir.sh present"
    else bad "run_all_A4_florbetapir.sh NOT found next to this script" "The repository is incomplete: download it again."; fi
fi

# ── 2. Python ──────────────────────────────────────────────────────────────────────────────────
sec "Python"
if [ -x "$PYTHON" ]; then PY="$PYTHON"; ok "virtualenv python found ($PYTHON)"
elif command -v python3 >/dev/null 2>&1; then
    PY="$(command -v python3)"
    warn "virtualenv not found at $PYTHON -- using $PY instead" \
         "Recommended: python3 -m venv ~/.venv_pet_pipeline && ~/.venv_pet_pipeline/bin/pip install nibabel numpy pandas scipy matplotlib openpyxl" \
         "(docs/INSTALL.md section 5). Or export PYTHON=/path/to/your/python3."
else PY=""; bad "no python3 found" "Install Python 3 (sudo apt-get install -y python3 python3-venv) and create the virtualenv (docs/INSTALL.md section 5)."; fi
if [ -n "$PY" ]; then
    MISSING=""
    for m in numpy pandas scipy nibabel matplotlib; do "$PY" -c "import $m" 2>/dev/null || MISSING="$MISSING $m"; done
    if [ -z "$MISSING" ]; then ok "numpy, pandas, scipy, nibabel, matplotlib importable"
    else bad "Python packages missing:$MISSING" "$PY -m pip install$MISSING   (inside a virtualenv; or add --break-system-packages for the system python)"; fi
    if "$PY" -c "import openpyxl" 2>/dev/null; then ok "openpyxl importable"
    elif [ "$MODE" == "gaain" ]; then bad "openpyxl missing (needed to read the GAAIN reference spreadsheet)" "$PY -m pip install openpyxl"
    else warn "openpyxl missing (only needed for the GAAIN validation, not for A4)" "$PY -m pip install openpyxl"; fi
fi
if [ "$MODE" == "a4" ]; then
    if command -v python >/dev/null 2>&1; then ok "'python' command found ($(command -v python)) -- run_all_A4_florbetapir.sh calls 'python'"
    else bad "'python' command not found (run_all_A4_florbetapir.sh calls 'python', not python3)" \
             "Debian/Ubuntu: sudo apt-get install -y python-is-python3" \
             "No root: mkdir -p ~/bin && ln -s \$(command -v python3) ~/bin/python && export PATH=\$HOME/bin:\$PATH"; fi
fi

# ── 3. FSL ─────────────────────────────────────────────────────────────────────────────────────
sec "FSL (flirt and fslstats resample the VOIs and measure the SUVR)"
FSL_MISSING=""
for t in flirt fslstats; do command -v "$t" >/dev/null 2>&1 || FSL_MISSING="$FSL_MISSING $t"; done
if [ -z "$FSL_MISSING" ]; then ok "flirt and fslstats found ($(command -v flirt))"
else bad "FSL commands not found:$FSL_MISSING" \
         "Install FSL: https://fsl.fmrib.ox.ac.uk/fsl/docs/#/install/index" \
         "Already installed? Load it in this terminal: export FSLDIR=\$HOME/fsl; source \$FSLDIR/etc/fslconf/fsl.sh; export PATH=\$FSLDIR/bin:\$PATH"; fi

# ── 4. SPM: standalone or MATLAB + SPM12 ──────────────────────────────────────────────────────
sec "SPM (standalone with MATLAB Runtime, or MATLAB + SPM12) -- same order the pipeline uses: standalone first"
SA_RUN="${CENTILOID_SPM_STANDALONE_RUN:-$(ls "$PETPIPELINE_BASE"/spm12_standalone/run_spm*.sh 2>/dev/null | sort | tail -n1)}"
SA_MCR="${CENTILOID_SPM_MCR_DIR:-}"
if [ -z "$SA_MCR" ]; then
    SA_MCR="$(ls -d "$PETPIPELINE_BASE"/spm12_standalone/MATLAB_Runtime/R*/v* /usr/local/MATLAB/MATLAB_Runtime/R*/v* 2>/dev/null | sort | tail -n1)"
fi
if [ -z "$SA_MCR" ]; then
    SA_MCR="$(ls -d "$PETPIPELINE_BASE"/spm12_standalone/MATLAB_Runtime/R*/bin /usr/local/MATLAB/MATLAB_Runtime/R*/bin 2>/dev/null | sed 's:/bin$::' | sort | tail -n1)"
fi
MATLAB_BIN="${CENTILOID_MATLAB_BIN:-$(ls -d /opt/MATLAB/R*/bin/matlab /usr/local/MATLAB/R*/bin/matlab 2>/dev/null | sort | tail -n1)}"
MATLAB_BIN="${MATLAB_BIN:-/opt/MATLAB/R2022b/bin/matlab}"
SPM12_PATH="${CENTILOID_SPM12_PATH:-$(dirname "$(dirname "$MATLAB_BIN")")/toolbox/spm12}"

SA_READY=0; ML_READY=0
[ -n "$SA_RUN" ] && [ -f "$SA_RUN" ] && [ -n "$SA_MCR" ] && [ -d "$SA_MCR" ] && SA_READY=1
[ -f "$MATLAB_BIN" ] && [ -d "$SPM12_PATH" ] && ML_READY=1

if [ $SA_READY -eq 1 ]; then
    ok "SPM standalone found ($SA_RUN + runtime $SA_MCR) -- no MATLAB license needed; the pipeline will use this"
    [ -x "$SA_RUN" ] || bad "launcher is not executable: $SA_RUN" "chmod +x $SA_RUN $(dirname "$SA_RUN")/spm12 2>/dev/null"
    if [ ! -d "$SA_MCR/bin" ]; then
        bad "the runtime folder has no bin/ inside: $SA_MCR" \
            "Point CENTILOID_SPM_MCR_DIR at the folder that contains bin/, runtime/, sys/ (e.g. .../MATLAB_Runtime/R2022b)."
    fi
    RELEASE="$(basename "$SA_MCR")"; case "$RELEASE" in v*) RELEASE="$(basename "$(dirname "$SA_MCR")")";; esac
    echo "          (runtime release: $RELEASE -- it must be the release named in the SPM standalone zip's file name)"
elif [ -n "$SA_RUN" ] && [ -f "$SA_RUN" ]; then
    bad "SPM launcher found ($SA_RUN) but the MATLAB Runtime was not found" \
        "Install the runtime of the release named in the SPM zip (R2022b for spm12_r7771_Linux_R2022b) -- docs/INSTALL.md section 8A." \
        "Already installed elsewhere? export CENTILOID_SPM_MCR_DIR=/path/to/MATLAB_Runtime/<release>"
elif [ -n "$SA_MCR" ] && [ -d "$SA_MCR" ]; then
    bad "MATLAB Runtime found ($SA_MCR) but the SPM standalone launcher (run_spm*.sh) was not found" \
        "Download and unzip SPM standalone into $PETPIPELINE_BASE/spm12_standalone/ -- docs/INSTALL.md section 8A." \
        "Already installed elsewhere? export CENTILOID_SPM_STANDALONE_RUN=/path/to/run_spmXX.sh"
fi
if [ $ML_READY -eq 1 ]; then
    if [ $SA_READY -eq 1 ]; then ok "MATLAB + SPM12 also present ($MATLAB_BIN) -- only used if the standalone is not ready"
    else ok "MATLAB + SPM12 found ($MATLAB_BIN + $SPM12_PATH)"; fi
fi
if [ $SA_READY -eq 0 ] && [ $ML_READY -eq 0 ] && [ -z "$SA_RUN" ] && [ -z "$SA_MCR" ]; then
    bad "neither SPM standalone nor MATLAB+SPM12 found" \
        "Option A (free, no license): follow docs/INSTALL.md section 8A (SPM standalone + MATLAB Runtime)." \
        "Option B: install MATLAB + SPM12, or export CENTILOID_MATLAB_BIN and CENTILOID_SPM12_PATH (docs/INSTALL.md section 8B)."
fi

# standalone runtime libraries (the MATLAB Runtime needs them; missing ones give errors with no hint)
if [ $SA_READY -eq 1 ] && command -v ldconfig >/dev/null 2>&1; then
    LIBS_MISSING=""
    for l in libXt libX11 libXext libXmu libXrender libasound libnsl; do
        [ "$(ldconfig -p 2>/dev/null | grep -c "$l.so")" -gt 0 ] || LIBS_MISSING="$LIBS_MISSING $l"
    done
    if [ -z "$LIBS_MISSING" ]; then ok "system libraries needed by the MATLAB Runtime are present"
    else warn "system libraries possibly missing for the MATLAB Runtime:$LIBS_MISSING" \
              "Debian/Ubuntu: sudo apt-get install -y libxt6 libxext6 libxmu6 libxrender1 libnsl2 libasound2t64   (libasound2 on Ubuntu < 24.04)" \
              "Only needed if SPM stops with an error about a missing .so file."; fi
fi

# ── 5. SPM templates (MNI template + Old Segment priors): must come from the SAME SPM that runs ──
sec "SPM templates (MNI template and Old Segment tissue priors)"
TPL=""; TPL_SRC=""
if [ -n "${CENTILOID_MNI_TEMPLATE:-}" ]; then TPL="$CENTILOID_MNI_TEMPLATE"; TPL_SRC="CENTILOID_MNI_TEMPLATE"
elif [ $SA_READY -eq 1 ]; then
    ROOT="$(dirname "$SA_RUN")"
    TPL="$(find "$ROOT" -maxdepth 9 -name MATLAB_Runtime -prune -o -path "*_mcr/*canonical/avg152T1.nii" -print 2>/dev/null | sort | tail -n1)"
    TPL_SRC="SPM standalone"
    if [ -z "$TPL" ]; then
        bad "SPM standalone is installed but not unpacked yet (no <spm>_mcr folder next to the launcher)" \
            "Run it once (takes 1-2 minutes the first time):" \
            "  $SA_RUN $SA_MCR eval \"disp(1)\"" \
            "Then run this check again."
    fi
else TPL="$SPM12_PATH/canonical/avg152T1.nii"; TPL_SRC="MATLAB's SPM12 toolbox"; fi
if [ -n "$TPL" ]; then
    if [ -f "$TPL" ]; then
        ok "MNI template found ($TPL_SRC): $TPL"
        PRI="$(cd "$(dirname "$TPL")/.." 2>/dev/null && pwd)/toolbox/OldSeg"; PRI_MISS=""
        for f in grey white csf; do [ -f "$PRI/$f.nii" ] || PRI_MISS="$PRI_MISS $f.nii"; done
        if [ -z "$PRI_MISS" ]; then ok "Old Segment tissue priors found ($PRI)"
        else bad "Old Segment priors missing in $PRI:$PRI_MISS" \
                 "They ship with SPM12 (toolbox/OldSeg). Reinstall SPM, or fix CENTILOID_MNI_TEMPLATE so that ../toolbox/OldSeg next to it holds grey.nii, white.nii and csf.nii."; fi
    else
        bad "MNI template not found: $TPL ($TPL_SRC)" \
            "Fix: export CENTILOID_MNI_TEMPLATE=/path/to/spm/canonical/avg152T1.nii   (it ships inside SPM's own canonical/ folder)"
    fi
fi
if [ $TEST_SPM -eq 1 ] && [ $SA_READY -eq 1 ]; then
    OUT="$("$SA_RUN" "$SA_MCR" eval "disp(spm('Ver'))" 2>&1 | grep -v -i fontconfig | tail -3)"
    if echo "$OUT" | grep -q "SPM"; then ok "SPM standalone starts correctly (it answered: $(echo "$OUT" | tr '\n' ' '))"
    else bad "SPM standalone did not start. Its output:" "$OUT" \
             "If it mentions a lock on the runtime cache: MCR_INHIBIT_CTF_LOCK=1 $SA_RUN $SA_MCR eval \"disp(1)\"" \
             "If it mentions a missing library: see the system libraries line above."; fi
elif [ $TEST_SPM -eq 0 ] && [ $SA_READY -eq 1 ]; then
    echo "          (add --test-spm to actually launch SPM once and prove it starts)"
fi

# ── 6. VOIs ───────────────────────────────────────────────────────────────────────────────────
sec "VOIs ($VOI) under $BASE_DIR"
if [ "$VOI" == "avid" ]; then
    VDIR="$BASE_DIR/VOIs_2mm"
    NEED="anterior_cingulate.nii.gz posterior_cingulate.nii.gz parietal.nii.gz precuneus.nii.gz temporal.nii.gz frontal_med_orb.nii.gz cere_all.nii.gz"
else
    VDIR="$BASE_DIR/VOIs_klunk"
    NEED="voi_ctx_2mm.nii voi_WhlCbl_2mm.nii"
fi
if [ ! -d "$VDIR" ]; then
    bad "VOI folder not found: $VDIR" "The VOIs are not distributed with the repository: copy the folder there (or export CENTILOID_BASE_DIR to the folder that contains it)."
else
    MISS=""; for f in $NEED; do [ -f "$VDIR/$f" ] || MISS="$MISS $f"; done
    if [ -z "$MISS" ]; then ok "all required VOI files present in $VDIR"
    else
        FIX="Copy the missing VOI files into $VDIR."
        if [ "$VOI" == "avid" ] && ls "$VDIR"/voi_*_2mm.nii >/dev/null 2>&1; then
            FIX="This folder holds the standard (Klunk) Centiloid VOIs (voi_*_2mm.nii), not the Avid VOIs. Either move them to $BASE_DIR/VOIs_klunk and run with --voi_method klunk, or put the Avid VOIs here."
        fi
        bad "VOI files missing in $VDIR:$MISS" "$FIX"
    fi
fi
if [ "$MODE" == "gaain" ] && [ ! -f "$BASE_DIR/Avid_Centiloid_standard_method.xlsx" ]; then
    warn "GAAIN reference spreadsheet not found: $BASE_DIR/Avid_Centiloid_standard_method.xlsx" "Only needed for the GAAIN validation plot; place the file there."
fi

# ── 7. Input data ─────────────────────────────────────────────────────────────────────────────
sec "Input data"
if [ "$MODE" == "a4" ]; then
    if [ ! -d "$A4_DATA_DIR" ]; then
        bad "A4 input folder not found: $A4_DATA_DIR" \
            "Create it and put one folder per subject: $A4_DATA_DIR/<ID>/<ID>_t1.nii and <ID>_pet.nii" \
            "Data somewhere else? export A4_DATA_DIR=/path/to/folder"
    else
        if [ -n "$ONLY_SUBJECT" ]; then SUBJ="$ONLY_SUBJECT"; else SUBJ="$(ls -d "$A4_DATA_DIR"/*/ 2>/dev/null | xargs -n1 basename 2>/dev/null)"; fi
        N=0; NBAD=0
        for s in $SUBJ; do
            N=$((N+1)); d="$A4_DATA_DIR/$s"
            T1="$(ls "$d"/${s}_t1*.nii 2>/dev/null | grep -v '_reor' | head -n1)"
            PET="$d/${s}_pet.nii"
            if [ ! -d "$d" ]; then bad "subject folder not found: $d" "Check the ID, or the folder name under $A4_DATA_DIR."; NBAD=$((NBAD+1)); continue; fi
            PROB=""
            [ -n "$T1" ] || PROB="$PROB no ${s}_t1*.nii;"
            [ -f "$PET" ] || PROB="$PROB no ${s}_pet.nii;"
            if [ -n "$PROB" ]; then
                NBAD=$((NBAD+1))
                bad "$s:$PROB found in folder: $(ls "$d" 2>/dev/null | grep -v '^\._' | tr '\n' ' ' | cut -c1-110)" \
                    "Rename/copy the files to exactly $s/${s}_t1.nii and $s/${s}_pet.nii (3D NIfTI, uncompressed). .nii.gz is not read: gunzip it."
            elif [ -n "$PY" ]; then
                INFO="$("$PY" - "$T1" "$PET" <<'PYEOF' 2>&1
import sys, nibabel as nib, numpy as np
t1, pet = sys.argv[1], sys.argv[2]
try:
    a, b = nib.load(t1), nib.load(pet)
    print("T1 %s | PET %s" % (a.shape, b.shape))
    if len(a.shape) != 3: print("PROBLEM: the T1 is not a 3D volume")
    if len(b.shape) not in (3, 4): print("PROBLEM: the PET is neither 3D nor 4D")
    if float(np.abs(np.asanyarray(b.dataobj)).max()) == 0: print("PROBLEM: the PET is all zeros")
except Exception as e:
    print("PROBLEM: cannot read the NIfTI: %s" % e)
PYEOF
)"
                if echo "$INFO" | grep -q PROBLEM; then NBAD=$((NBAD+1)); bad "$s: $(echo "$INFO" | grep PROBLEM | head -n1)" "Check the file is a valid NIfTI of the right image (T1 = anatomical MRI, PET = florbetapir)."
                elif [ -n "$ONLY_SUBJECT" ] || [ $N -le 3 ]; then ok "$s: files found and readable ($INFO)"; fi
            fi
        done
        if [ $N -eq 0 ]; then bad "no subject folders under $A4_DATA_DIR" "Create one folder per subject: $A4_DATA_DIR/<ID>/<ID>_t1.nii and <ID>_pet.nii"
        elif [ $NBAD -eq 0 ]; then ok "$N subject folder(s) with T1 and PET under $A4_DATA_DIR"
        else echo "          ($NBAD of $N subject folders have problems)"; fi
        ls "$A4_DATA_DIR"/*/._* >/dev/null 2>&1 && warn "macOS '._' files found inside the subject folders" "They are harmless for this pipeline; remove with: find $A4_DATA_DIR -name '._*' -delete"
    fi
    # nothing is created here: test the folder, or the closest existing parent if it does not exist yet
    OUTCHK="$A4_OUT_DIR"; while [ ! -d "$OUTCHK" ] && [ "$OUTCHK" != "/" ]; do OUTCHK="$(dirname "$OUTCHK")"; done
    if [ -w "$OUTCHK" ]; then ok "output folder usable: $A4_OUT_DIR ($(df -h "$OUTCHK" | awk 'NR==2{print $4}') free)"
    else bad "cannot write to the output folder: $A4_OUT_DIR" "Fix the permissions or export A4_OUT_DIR=/folder/you/can/write"; fi
else
    N=$(ls -d "$BASE_DIR"/florbetapir/*/*/ 2>/dev/null | wc -l)
    if [ "$N" -gt 0 ]; then ok "$N subject folder(s) under $BASE_DIR/florbetapir/<group>/"
    else bad "no PET subject folders under $BASE_DIR/florbetapir/Elder_subject_florbetapir/ or Young_Control_florbetapir/" \
             "Layout: $BASE_DIR/florbetapir/Elder_subject_florbetapir/<6-digit ID>*/...dcm and $BASE_DIR/*MRI*/<ID>*/...dcm (docs: README, 'Centiloid (florbetapir)')"; fi
    if command -v dcm2niix >/dev/null 2>&1; then ok "dcm2niix found"
    else bad "dcm2niix not found (GAAIN data are DICOM)" "sudo apt-get install -y dcm2niix   (or brew install dcm2niix; docs/INSTALL.md section 7)"; fi
fi

# ── summary ───────────────────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "RESULT: $PASS ok, $WARN warning(s), $FAIL failed"
if [ $FAIL -eq 0 ]; then
    echo "Everything required is in place. To run it:"
    if [ "$MODE" == "a4" ]; then echo "  VOI_METHOD=$VOI bash code/centiloid/run_all_A4_florbetapir.sh <ID>      # one subject (omit <ID> for all)"
    else echo "  python3 code/centiloid/centiloid_pipeline_tracers.py --test <ID> --voi_method $VOI --auto_reorient"
         echo "  (--auto_reorient picks its method from --voi_method: 'b' for klunk, 'a' otherwise; see README)"; fi
else
    echo "Fix the FAIL lines above (each one says how), then run this check again."
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
[ $FAIL -eq 0 ]
