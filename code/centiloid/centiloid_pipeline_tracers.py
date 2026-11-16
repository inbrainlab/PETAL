"""
Complete Centiloid pipeline - Florbetapir / Avid VOIs / Standard Centiloid VOIs
===============================================================================
Converts DICOMs, sums PET frames, runs SPM (Coregister, Old Segment,
Normalise) and extracts SUVr / Centiloid.

TRACER: Florbetapir (F18-AV-45) or C-11 PiB (--tracer fbp|pib)
METHOD: Joshi et al. 2015 -- 6 cortical VOIs (medial orbital frontal,
        lateral temporal, parietal, anterior cingulate, posterior
        cingulate, precuneus) + whole cerebellum as reference.
        Positivity threshold: SUVr = 1.10.
CALIBRATION: derived from the reference spreadsheet
        Avid_Centiloid_standard_method.xlsx (cohort of 46 subjects).
        - FBP: CL = 175.18 * SUVr - 182.24
        - PiB: CL = 93.99  * SUVr - 94.41
        These differ slightly from the published equations of Navitsky
        2018 (FBP: 183/-177) and Klunk 2015 (PiB: 188.22/-189.16),
        because the spreadsheet used anchor points re-derived on the same
        cohort. Use these to validate against the spreadsheet; use the
        published ones when reporting against external literature.

Based on:
- Klunk et al. 2015 (Centiloid project, PiB level-2 procedure)
- Joshi et al. 2015 (Florbetapir PET semiautomated quantification)
- Navitsky et al. 2018 (Florbetapir SUVr -> Centiloid conversion)

Usage - test mode (one subject):
    python centiloid_pipeline_tracers.py --test <SUBJECT_ID>

Usage - full Florbetapir loop (produces a validation plot):
    python centiloid_pipeline_tracers.py --all --auto_reorient

Usage - PiB loop reusing the T1 images already converted in the FBP run:
    python centiloid_pipeline_tracers.py --all --tracer pib --auto_reorient \\
        --reuse_t1_from results

Additional options:
    --base_dir   Root directory of the data
    --ref_xlsx   Avid reference spreadsheet
    --voi        Folder with the 2 mm VOIs
    --out        Output folder (default: results/ or results_pib/)
    --skip_dcm2niix / --skip_coreg / --skip_spm
"""

# ── auto-use this pipeline's own virtualenv, if present ──────────────────────
# Lets you run this script with plain "python3" (as shown in the README/docs)
# and still pick up the packages installed in the pipeline's own virtualenv
# (~/.venv_pet_pipeline by default, or $PYTHON) without having to activate it
# yourself. Re-executes once under that interpreter if it exists and we are
# not already running under it; otherwise falls through unchanged.
import os as _os
import sys as _sys
_venv_python = _os.environ.get("PYTHON") or _os.path.expanduser("~/.venv_pet_pipeline/bin/python3")
if _os.path.exists(_venv_python) and _os.path.realpath(_sys.executable) != _os.path.realpath(_venv_python):
    _os.execv(_venv_python, [_venv_python] + _sys.argv)

import argparse
import os
import sys
import glob
import re
import subprocess
import numpy as np
import pandas as pd
from scipy import stats
import nibabel as nib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# =============================================
# CONFIGURATION
# =============================================
# BASE_DIR is read from the CENTILOID_BASE_DIR environment variable and defaults to
# PETPIPELINE_BASE/centiloid_input (PETPIPELINE_BASE defaults to ~/Downloads/pet_pipeline). The data
# layout (VOIs_2mm/, VOIs_klunk/, the reference xlsx) is expected under BASE_DIR.
#
# MATLAB_BIN / SPM12_PATH / MNI_TEMPLATE are machine specific (they depend
# on where MATLAB and SPM12 are installed). Set them by exporting
# CENTILOID_MATLAB_BIN / CENTILOID_SPM12_PATH / CENTILOID_MNI_TEMPLATE, or
# edit the defaults below.

# Same convention as run_public_pipeline.sh/check_install.sh/dicom_to_nifti.py: PETPIPELINE_BASE,
# defaulting to this repo's own pet_pipeline/ folder -- so all tracers share one working-directory root.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PETPIPELINE_BASE = os.environ.get("PETPIPELINE_BASE") or os.path.join(_REPO_ROOT, "pet_pipeline")
BASE_DIR   = os.environ.get("CENTILOID_BASE_DIR", os.path.join(_PETPIPELINE_BASE, "centiloid_input"))
REF_XLSX   = os.path.join(BASE_DIR, "Avid_Centiloid_standard_method.xlsx")
VOI_DIR    = os.path.join(BASE_DIR, "VOIs_2mm")        # Avid VOIs (default)
VOI_DIR_KLUNK = os.path.join(BASE_DIR, "VOIs_klunk")    # Standard Centiloid VOIs
OUT_DIR    = os.path.join(BASE_DIR, "results")

# SPM is run through either a regular MATLAB installation (MATLAB + SPM12) or
# SPM12 standalone + MATLAB Runtime -- see run_spm() below, which auto-detects
# whichever is actually present, no manual choice needed (docs/INSTALL.md
# section 8). Both auto-detections below scan every MATLAB/MATLAB Runtime
# *version* folder they can find (R2022b, R2023a, ...), since a given
# machine's installed version is not something this repo can assume --
# an explicit env var always wins over whatever auto-detection finds.

def _newest_glob_match(*patterns):
    """Return the lexicographically-last path matching any of these glob
    patterns (release names like R2022b/R2023a sort correctly this way), or
    None if nothing matches. Used so a machine with several MATLAB/MATLAB
    Runtime versions installed picks the newest one automatically."""
    matches = []
    for pattern in patterns:
        matches.extend(glob.glob(pattern))
    return sorted(matches)[-1] if matches else None


# MATLAB + SPM12 (regular, licensed install). Scans every version under the
# two common Linux/macOS install roots instead of assuming one exact version.
MATLAB_BIN = os.environ.get("CENTILOID_MATLAB_BIN") or _newest_glob_match(
    "/opt/MATLAB/R*/bin/matlab",
    "/usr/local/MATLAB/R*/bin/matlab",
) or "/opt/MATLAB/R2022b/bin/matlab"

# SPM12_PATH/MNI_TEMPLATE live under that same MATLAB installation's own
# toolbox/ folder, so they are derived from MATLAB_BIN's own version by
# default rather than hardcoding a version a second time.
_matlab_root = os.path.dirname(os.path.dirname(MATLAB_BIN))  # strip "/bin/matlab"
SPM12_PATH = os.environ.get(
    "CENTILOID_SPM12_PATH", os.path.join(_matlab_root, "toolbox", "spm12"))
MNI_TEMPLATE = os.environ.get(
    "CENTILOID_MNI_TEMPLATE", os.path.join(SPM12_PATH, "canonical", "avg152T1.nii"))

# SPM12 standalone + MATLAB Runtime (free, no MATLAB license needed).
#   CENTILOID_SPM_STANDALONE_RUN -> path to the run_spm12.sh script that ships
#                                   inside the SPM12 standalone download (no
#                                   fixed install location, so no version-scan
#                                   is possible here -- set it explicitly if
#                                   you installed this).
#   CENTILOID_SPM_MCR_DIR        -> path to the MATLAB Runtime folder whose
#                                   version matches that standalone build.
#                                   Scans every version under the MATLAB
#                                   Runtime installer's own default Linux path.
SPM_STANDALONE_RUN = os.environ.get(
    "CENTILOID_SPM_STANDALONE_RUN", "/opt/spm12_standalone/run_spm12.sh")
SPM_MCR_DIR = os.environ.get("CENTILOID_SPM_MCR_DIR") or _newest_glob_match(
    "/usr/local/MATLAB/MATLAB_Runtime/R*/v*",
) or "/usr/local/MATLAB/MATLAB_Runtime/R2022b/v912"

# ---------------------------------------------------------------
# PER-TRACER AND PER-VOI-METHOD CONFIGURATION (--tracer + --voi_method)
# ---------------------------------------------------------------
# Each (tracer, voi_method) combination has its own calibration, data
# folders and positivity threshold. The default tracer is Florbetapir (fbp).
#
# Available VOI methods:
#   - "avid":  6 cortical VOIs of Joshi 2015 (medial orbital frontal,
#              lateral temporal, parietal, anterior cingulate,
#              posterior cingulate, precuneus) + whole cerebellum.
#   - "klunk": GAAIN Standard Centiloid VOIs (voi_ctx_2mm.nii = a single
#              large cortical VOI, voi_WhlCbl_2mm.nii = whole cerebellum).
#              This is the official method of the Centiloid Project
#              (Klunk et al. 2015).
#
# Florbetapir calibrations according to Navitsky 2018:
#   - Equation 2A (Avid VOIs):  CL_FBP = 183.0 * SUVr - 177.0
#   - Equation 2B (Klunk VOIs): CL_FBP = 175.18 * SUVr - 182.24
#
# PiB (Klunk 2015, anchor points YC0=1.009 AD100=1.541):
#   CL = 100 * (SUVr - 1.009) / (1.541 - 1.009) = 188.22 * SUVr - 189.16
#   The coefficients used below (93.99 / -94.41) are instead the ones
#   derived from the reference spreadsheet (see the notes in the config).
#
# The VOI folders are independent:
#   VOIs_2mm/        -> Avid VOIs (6 cortical + cere_all)
#   VOIs_klunk/      -> Klunk Standard VOIs (voi_ctx_2mm + voi_WhlCbl_2mm)
#
# The output folder depends on the tracer so that runs do not get mixed:
#   results/      -- Florbetapir run
#   results_pib/  -- PiB run

# VOI maps per method
VOI_MAP_AVID = {
    "anterior_cingulate.nii.gz":  "lanterior_cingulate_2",
    "posterior_cingulate.nii.gz": "llposterior_cingulate_2",
    "parietal.nii.gz":            "lnew_parietal",
    "precuneus.nii.gz":           "lprecuneus_gm",
    "temporal.nii.gz":            "new_temporal_2",
    "frontal_med_orb.nii.gz":     "xlaal_frontal_med_orb",
    "cere_all.nii.gz":            "blcere_all",
}

VOI_MAP_KLUNK = {
    "voi_ctx_2mm.nii":     "ctx_klunk",
    "voi_WhlCbl_2mm.nii":  "wcb_klunk",
}

# Global variable, set according to --voi_method
VOI_MAP = VOI_MAP_AVID

TRACER_CONFIG = {
    "fbp": {
        "name":           "Florbetapir",
        # Layout: <base>/florbetapir/<group folder>/<id>...
        "pet_root_pattern": ["florbetapir/Elder_subject_florbetapir",
                      "florbetapir/Young_Control_florbetapir"],
        "out_subdir":     "results",
        # Calibrations per VOI method
        "calibration": {
            "avid": {
                # Equation 2A of Navitsky 2018 (Avid VOIs).
                # NOTE: the reference spreadsheet does NOT publish data with
                # Avid VOIs -- all of its columns use Standard VOIs.
                # Hence ref_col_* = None: there is no reference to compare to.
                "cl_slope":     183.0,
                "cl_intercept": -177.0,
                "cl_threshold":   24.1,
                "suvr_threshold": 1.10,
                "ref_col_id":        None,
                "ref_col_group":     None,
                "ref_col_suvr":      None,
                "ref_col_centiloid": None,
            },
            "klunk": {
                # Equation 2B of Navitsky 2018 (Standard Centiloid VOIs).
                # Matches the polyfit of column 8 of the spreadsheet.
                "cl_slope":     175.18,
                "cl_intercept": -182.24,
                "cl_threshold":   25.6,
                "suvr_threshold": 1.18,
                # Spreadsheet cols 0=id, 2=group, 3=SUVr_FBP, 8=CL_FBP
                "ref_col_id":        0,
                "ref_col_group":     2,
                "ref_col_suvr":      3,
                "ref_col_centiloid": 8,
            },
        },
    },
    "pib": {
        "name":           "C-11 PiB",
        # Layout: <base>/Elder_subject_PiB/ and Young_Control_PiB/
        "pet_root_pattern": ["Elder_subject_PiB", "Young_Control_PiB"],
        "out_subdir":     "results_pib",
        "calibration": {
            "avid": {
                # Calibration derived from the spreadsheet on the Avid cohort
                # (not the official Klunk one). The spreadsheet has no
                # reference for PiB + Avid VOIs because it only publishes
                # Standard VOIs.
                "cl_slope":     93.99,
                "cl_intercept": -94.41,
                "cl_threshold":   13.0,
                "suvr_threshold": 1.139,
                "ref_col_id":        None,
                "ref_col_group":     None,
                "ref_col_suvr":      None,
                "ref_col_centiloid": None,
            },
            "klunk": {
                # Spreadsheet calibration for PiB + Standard VOIs.
                # IMPORTANT: this is NOT the official Klunk 2015 PiB level-2
                # calibration (188.22*SUVr - 189.16, anchors YC0=1.009
                # AD100=1.541 on the GAAIN cohort). It is the calibration
                # derived from the Avid cohort: anchors YC0=1.005 AD100=2.069
                # on the same 46 subjects of the spreadsheet.
                # Use these coefficients to validate against the spreadsheet.
                # For a formal level-2 validation with GAAIN PiB data use
                # 188.22 / -189.16 (edit manually).
                "cl_slope":     93.99,
                "cl_intercept": -94.41,
                "cl_threshold":   13.0,
                "suvr_threshold": 1.139,
                # Spreadsheet cols 0=id, 2=group, 4=SUVr_PiB, 9=CL_PiB
                "ref_col_id":        0,
                "ref_col_group":     2,
                "ref_col_suvr":      4,
                "ref_col_centiloid": 9,
            },
        },
    },
}

# Variables set in main() according to --tracer + --voi_method
# (defaults = FBP + Avid)
CL_SLOPE                = TRACER_CONFIG["fbp"]["calibration"]["avid"]["cl_slope"]
CL_INTERCEPT            = TRACER_CONFIG["fbp"]["calibration"]["avid"]["cl_intercept"]
CL_THRESHOLD_POSITIVE   = TRACER_CONFIG["fbp"]["calibration"]["avid"]["cl_threshold"]
SUVR_THRESHOLD_POSITIVE = TRACER_CONFIG["fbp"]["calibration"]["avid"]["suvr_threshold"]

# Project Centiloid validation criteria (Klunk et al. 2015)
SLOPE_MIN     = 0.98
SLOPE_MAX     = 1.02
INTERCEPT_MAX = 2.0
R2_MIN        = 0.98

# Auto-reorientation (method "a"): a SHARED offset -COM_MRI is applied to
# both modalities. This keeps the original relative PET-MRI alignment and
# only moves both images close to the MNI origin (see
# auto_reorient_subject for the alternative, independent-offset method "b").
REORIENT_TH_MRI_MM = 30.0   # |COM_MRI| > th -> reorient
REORIENT_TH_PET_MM = 50.0   # |COM_PET| > th -> reorient
REORIENT_COM_FRAC  = 0.20   # intensity threshold used to compute the COM

# Columns of the results CSV (in this order)
CSV_COLUMNS = [
    "subject_id", "wpet_file", "ctx_suvr", "centiloid_pipeline",
    "suvr_lanterior_cingulate_2", "suvr_llposterior_cingulate_2",
    "suvr_lnew_parietal", "suvr_lprecuneus_gm",
    "suvr_new_temporal_2", "suvr_xlaal_frontal_med_orb",
    "status", "error",
]

# =============================================
# UTILITIES
# =============================================

def run(cmd, desc=""):
    """Run a command and show its output. Fails with a clear message.

    MATLAB (via run_spm) writes the real error to STDOUT
    (disp(getReport(e))), not to stderr, so both streams are printed on
    failure."""
    print(f"    -> {desc or ' '.join(cmd[:3])}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"    X Error (stdout, last 2000 characters):\n{result.stdout[-2000:]}")
        print(f"    X Error (stderr, last 500 characters):\n{result.stderr[-500:]}")
        raise RuntimeError(f"Failed: {' '.join(cmd[:4])}")
    return result.stdout.strip()


def find_dicom_dirs(base, subject_id, modality, tracer="fbp"):
    """
    Find ALL DICOM folders of a subject given its ID and modality.

    Returns a LIST of paths (may have one or several elements):
    - FBP: simple layout, 1 DICOM folder per modality.
    - PiB: sometimes 4 folders (= 4 temporal frames of 5 min) or
      2 folders (= 2 frames) are present. The pipeline sums them later.

    For MRI (T1) a single folder is always returned (T1 images are not
    shared between tracers; the DICOMs live only in the MRI folder).
    """
    if modality == "mri":
        # The T1 lives in the MRI* folder regardless of the tracer
        roots = glob.glob(os.path.join(base, "*MRI*"))
        for root in roots:
            subj_dirs = glob.glob(os.path.join(root, f"{subject_id}*"))
            for subj_dir in subj_dirs:
                # Look for any DICOM folder inside
                dicom_dirs = []
                for dirpath, _, filenames in os.walk(subj_dir, followlinks=True):
                    if os.path.basename(dirpath).upper() == "SNAPSHOTS":
                        continue
                    if any(f.lower().endswith(".dcm") for f in filenames):
                        dicom_dirs.append(dirpath)
                if dicom_dirs:
                    # For the T1 keep the first one (a single scan)
                    return [sorted(dicom_dirs)[0]]

        raise FileNotFoundError(
            f"No MRI DICOM folder found for {subject_id}")

    # PET: depends on the tracer
    cfg = TRACER_CONFIG[tracer]
    pattern = cfg["pet_root_pattern"]
    if isinstance(pattern, str):
        roots = glob.glob(os.path.join(base, pattern))
    else:
        # List of explicit folders
        roots = [os.path.join(base, p) for p in pattern
                 if os.path.isdir(os.path.join(base, p))]

    all_dicom_dirs = []
    for root in roots:
        # Look for subject folders matching the ID
        for entry in os.listdir(root):
            entry_path = os.path.join(root, entry)
            if not os.path.isdir(entry_path):
                continue
            # The subject ID must be at the start of the name or after "PiB-"
            if not (entry.startswith(subject_id) or
                    entry == subject_id or
                    f"PiB-{subject_id}" in entry):
                continue
            # Find all DICOM folders inside this subject
            for dirpath, _, filenames in os.walk(entry_path, followlinks=True):
                if os.path.basename(dirpath).upper() == "SNAPSHOTS":
                    continue
                if any(f.lower().endswith(".dcm") for f in filenames):
                    all_dicom_dirs.append(dirpath)

    if not all_dicom_dirs:
        raise FileNotFoundError(
            f"No PET DICOM folder found for {subject_id} (tracer={tracer})")

    return sorted(all_dicom_dirs)


def find_dicom_dir(base, subject_id, modality, tracer="fbp"):
    """Return the FIRST DICOM folder.
    Use find_dicom_dirs() to get all of them (needed for PiB with
    several frames stored in separate folders).
    """
    return find_dicom_dirs(base, subject_id, modality, tracer)[0]


def get_all_subject_ids(base_dir, tracer="fbp"):
    """Extract all unique subject IDs from the PET folders of the tracer."""
    ids = set()
    cfg = TRACER_CONFIG[tracer]
    pattern = cfg["pet_root_pattern"]

    if isinstance(pattern, str):
        roots = glob.glob(os.path.join(base_dir, pattern))
    else:
        roots = [os.path.join(base_dir, p) for p in pattern
                 if os.path.isdir(os.path.join(base_dir, p))]

    for pet_root in roots:
        if not os.path.isdir(pet_root):
            continue
        for entry in os.scandir(pet_root):
            if not entry.is_dir():
                continue
            # ID at the start (FBP/PiB): "105858_..." or "231642"
            m = re.match(r"(\d{6})(?:[_\-.]|$)", entry.name)
            if m:
                ids.add(m.group(1))
                continue
            # PiB-<id> variant
            m = re.search(r"PiB-(\d{6})", entry.name)
            if m:
                ids.add(m.group(1))
    return sorted(ids)


# =============================================
# INCREMENTAL CSV
# =============================================

def init_csv(csv_path, subject_ids):
    """
    Create the CSV at the start of the run, with one row per subject in
    'pending' state. If the CSV already exists, extend it with the missing
    subjects without overwriting previous results.
    """
    if os.path.exists(csv_path):
        df_existing = pd.read_csv(csv_path)
        # Make sure all expected columns exist
        for col in CSV_COLUMNS:
            if col not in df_existing.columns:
                df_existing[col] = np.nan
        df_existing = df_existing[CSV_COLUMNS]
        existing_ids = set(df_existing["subject_id"].astype(str))
        new_ids = [sid for sid in subject_ids if str(sid) not in existing_ids]
        if new_ids:
            new_rows = pd.DataFrame({
                "subject_id": new_ids,
                "status": "pending",
            })
            for col in CSV_COLUMNS:
                if col not in new_rows.columns:
                    new_rows[col] = np.nan
            new_rows = new_rows[CSV_COLUMNS]
            df = pd.concat([df_existing, new_rows], ignore_index=True)
        else:
            df = df_existing
    else:
        df = pd.DataFrame({
            "subject_id": [str(s) for s in subject_ids],
            "status": "pending",
        })
        for col in CSV_COLUMNS:
            if col not in df.columns:
                df[col] = np.nan
        df = df[CSV_COLUMNS]

    df.to_csv(csv_path, index=False)
    print(f"  CSV initialized: {csv_path} ({len(df)} subjects in total)")
    return csv_path


def update_csv_row(csv_path, subject_id, data):
    """
    Update a subject's row in the CSV. If the row does not exist it is
    created. Full read/write: the CSV is small, so this is not a problem.

    Columns are converted to dtype 'object' before writing to avoid
    coercion problems in pandas 2.x when strings and NaN are mixed.
    """
    df = pd.read_csv(csv_path)
    df["subject_id"] = df["subject_id"].astype(str)
    sid = str(subject_id)

    if sid in df["subject_id"].values:
        idx = df.index[df["subject_id"] == sid][0]
        for k, v in data.items():
            if k not in df.columns:
                # Create the new column as object to accept mixed types
                df[k] = pd.Series([np.nan] * len(df), dtype="object")
            else:
                # If the column exists but its dtype cannot hold the value,
                # promote it to object
                if isinstance(v, str) and df[k].dtype != "object":
                    df[k] = df[k].astype("object")
            df.at[idx, k] = v
    else:
        new_row = {"subject_id": sid, **data}
        for col in CSV_COLUMNS:
            if col not in new_row:
                new_row[col] = np.nan
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

    # Keep column order (extra columns at the end)
    cols = CSV_COLUMNS + [c for c in df.columns if c not in CSV_COLUMNS]
    df = df[cols]
    df.to_csv(csv_path, index=False)


# =============================================
# STEP 1 - DICOM -> NIfTI CONVERSION
# =============================================

def convert_dicom(dicom_dirs, out_dir, prefix):
    """Convert one or several DICOM folders to NIfTI using dcm2niix.

    Accepts a str (one folder) or a list (several folders, e.g. PiB with
    4 frames in separate folders). Each folder produces one or several
    NIfTI files. Returns the combined list of all generated NIfTI files,
    ready to be passed to sum_pet_frames().
    """
    os.makedirs(out_dir, exist_ok=True)
    if isinstance(dicom_dirs, str):
        dicom_dirs = [dicom_dirs]

    all_niftis = []
    for i, ddir in enumerate(dicom_dirs):
        # With several folders, add a suffix to the prefix so that
        # dcm2niix does not overwrite the files of the previous frame
        prefix_i = prefix if len(dicom_dirs) == 1 else f"{prefix}_p{i+1}"
        run(
            ["dcm2niix", "-z", "n", "-f", prefix_i, "-o", out_dir, ddir],
            f"dcm2niix -> {prefix_i}"
        )
        niftis = sorted(glob.glob(os.path.join(out_dir, f"{prefix_i}*.nii")))
        if not niftis:
            raise FileNotFoundError(
                f"dcm2niix did not produce a .nii for {prefix_i} (folder {ddir})")
        all_niftis.extend(niftis)

    if not all_niftis:
        raise FileNotFoundError(f"dcm2niix did not produce a .nii for {prefix}")
    return all_niftis


# =============================================
# STEP 2 - PET FRAME SUMMATION
# =============================================

def sum_pet_frames(nifti_files, out_dir, subject_id):
    """
    Sum PET frames (50-70 min).
    - A single file: use it directly (3D) or sum over time (4D)
    - Several files: detect and discard duplicates, then sum
    """
    import nibabel as nib

    out_file = os.path.join(out_dir, f"{subject_id}_pet_summed.nii")

    if len(nifti_files) == 1:
        img  = nib.load(nifti_files[0])
        data = img.get_fdata()
        summed = data.sum(axis=3) if data.ndim == 4 else data
        nib.save(nib.Nifti1Image(summed, img.affine, img.header), out_file)

    else:
        imgs  = [nib.load(f) for f in nifti_files]
        datas = [img.get_fdata() for img in imgs]

        # Detect and remove duplicates (identical frames)
        unique_datas  = [datas[0]]
        unique_imgs   = [imgs[0]]
        for i in range(1, len(datas)):
            is_dup = any(np.allclose(datas[i], u, atol=1e-3)
                         for u in unique_datas)
            if is_dup:
                print(f"    !  Duplicate frame detected and discarded: "
                      f"{os.path.basename(nifti_files[i])}")
            else:
                unique_datas.append(datas[i])
                unique_imgs.append(imgs[i])

        print(f"    -> Unique frames: {len(unique_datas)} / {len(nifti_files)}")

        if len(unique_datas) == 1:
            summed = unique_datas[0]
        else:
            summed = np.sum(unique_datas, axis=0)

        nib.save(nib.Nifti1Image(
            summed, unique_imgs[0].affine, unique_imgs[0].header), out_file)

    print(f"    -> Summed PET: {out_file}")
    return out_file


# =============================================
# STEP 2.5 - AUTO-REORIENTATION
# =============================================
# Computes the center of mass (COM) of each image and shifts the MRI and
# PET so that both end up centered near the MNI origin before the SPM
# Coregister step.
#
# Only the translation of the affine (header) is modified, NOT the data.
# *_reor.nii files are written next to the originals.

def _center_of_mass_world(data, affine, threshold_frac=REORIENT_COM_FRAC):
    """Intensity-weighted COM in world coordinates (mm).
    Thresholds at threshold_frac of the maximum to discard background."""
    if data.ndim == 4:
        data = data.mean(axis=3)
    data = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
    max_val = float(np.nanmax(data))
    if max_val <= 0:
        return np.array([np.nan, np.nan, np.nan])
    mask = data > (threshold_frac * max_val)
    if not mask.any():
        return np.array([np.nan, np.nan, np.nan])
    coords = np.argwhere(mask).astype(float)
    weights = data[mask].astype(float)
    com_voxel = (coords.T @ weights) / weights.sum()
    return affine[:3, :3] @ com_voxel + affine[:3, 3]


def _shift_affine_origin(affine, offset_mm):
    """Apply an offset to the translation of the affine only. Data untouched."""
    new_affine = affine.copy()
    new_affine[:3, 3] = affine[:3, 3] + np.asarray(offset_mm, dtype=float)
    return new_affine


def auto_reorient_subject(t1_file, pet_file, work_dir,
                          th_mri=REORIENT_TH_MRI_MM,
                          th_pet=REORIENT_TH_PET_MM,
                          method="a"):
    """
    Auto-reorientation, two methods available via `method`:

    "a" (SHARED offset, default): -COM_MRI for both modalities.
        Fixes the absolute position relative to the origin WITHOUT
        touching the relative PET-MRI alignment the data already had.
        Safe (does not break subjects that already worked), but it does
        not correct a relative displacement that is already large in the
        raw data; it only preserves it.

    "b" (INDEPENDENT offsets): offset_MRI=-COM_MRI, offset_PET=-COM_PET
        separately -- forces the PET center of mass to coincide with the
        MRI one (centroid pre-alignment, a standard technique to correct
        LARGE displacements). Risk: if PET and MRI were already reasonably
        aligned, this introduces an artificial relative displacement that
        can take the SPM coregistration out of its capture range. Use "b"
        for subjects where "a" failed, not as a general default.

    Reorientation is only applied if |COM_MRI|>th_mri or |COM_PET|>th_pet
    (same trigger for both methods).

    Returns (t1_out, pet_out, info_dict). If no reorientation is applied,
    t1_out = t1_file and pet_out = pet_file (originals untouched).
    """
    import nibabel as nib

    if method not in ("a", "b"):
        raise ValueError(f"method must be 'a' or 'b', got: {method!r}")

    t1_img  = nib.load(t1_file)
    pet_img = nib.load(pet_file)

    com_mri = _center_of_mass_world(t1_img.get_fdata(),  t1_img.affine)
    com_pet = _center_of_mass_world(pet_img.get_fdata(), pet_img.affine)

    if np.isnan(com_mri).any() or np.isnan(com_pet).any():
        print(f"    !  COM is NaN -- skipping auto-reorientation")
        return t1_file, pet_file, {"reoriented": False, "reason": "com_nan"}

    dist_mri = float(np.linalg.norm(com_mri))
    dist_pet = float(np.linalg.norm(com_pet))
    relative_dist = float(np.linalg.norm(com_mri - com_pet))

    if dist_mri <= th_mri and dist_pet <= th_pet:
        print(f"    -> No reorientation: |COM_MRI|={dist_mri:.1f}mm, "
              f"|COM_PET|={dist_pet:.1f}mm (both below threshold)")
        return t1_file, pet_file, {
            "reoriented":  False,
            "reason":      "below_threshold",
            "com_mri_old": dist_mri,
            "com_pet_old": dist_pet,
        }

    if method == "a":
        # SHARED OFFSET -- preserves the original relative alignment
        offset_mri = -com_mri
        offset_pet = -com_mri
    else:
        # INDEPENDENT OFFSETS -- forces COM_PET to coincide with COM_MRI
        offset_mri = -com_mri
        offset_pet = -com_pet

    t1_out = os.path.join(work_dir,
        os.path.basename(t1_file).replace(".nii", "_reor.nii"))
    pet_out = os.path.join(work_dir,
        os.path.basename(pet_file).replace(".nii", "_reor.nii"))

    nib.save(nib.Nifti1Image(t1_img.get_fdata(),
                              _shift_affine_origin(t1_img.affine, offset_mri),
                              t1_img.header), t1_out)
    nib.save(nib.Nifti1Image(pet_img.get_fdata(),
                              _shift_affine_origin(pet_img.affine, offset_pet),
                              pet_img.header), pet_out)

    # Verify the result
    com_mri_new = _center_of_mass_world(
        nib.load(t1_out).get_fdata(),  nib.load(t1_out).affine)
    com_pet_new = _center_of_mass_world(
        nib.load(pet_out).get_fdata(), nib.load(pet_out).affine)
    new_mri_dist = float(np.linalg.norm(com_mri_new))
    new_pet_dist = float(np.linalg.norm(com_pet_new))
    new_relative_dist = float(np.linalg.norm(com_mri_new - com_pet_new))

    label = "method A, shared offset" if method == "a" else "method B, independent offsets"
    print(f"    -> Auto-reoriented ({label}):")
    print(f"       MRI: |COM| {dist_mri:.1f} -> {new_mri_dist:.1f} mm")
    print(f"       PET: |COM| {dist_pet:.1f} -> {new_pet_dist:.1f} mm")
    print(f"       |COM_MRI-COM_PET|: {relative_dist:.1f}mm -> {new_relative_dist:.1f}mm")

    return t1_out, pet_out, {
        "reoriented":  True,
        "method":      method,
        "com_mri_old": dist_mri,
        "com_pet_old": dist_pet,
        "com_mri_new": new_mri_dist,
        "com_pet_new": new_pet_dist,
        "relative_dist_old": relative_dist,
        "relative_dist_new": new_relative_dist,
        "offset_mri": offset_mri.tolist(),
        "offset_pet": offset_pet.tolist(),
    }


# =============================================
# STEP 3 - SPM BATCH
# =============================================

def normalize_pet(pet_file, out_dir, subject_id):
    """
    Normalize the PET by dividing by its mean (relative scale).
    This improves the SPM coregistration when the PET is in BQML.
    The SUVr is independent of the absolute scale.

    The output file name derives from the input PET name, so that different
    variants (originals vs _reor.nii) do not overwrite each other and it is
    possible to trace which file generated each wPET.
    """
    import nibabel as nib
    in_base = os.path.basename(pet_file).replace(".nii", "")
    # If the input already has "_summed" or "_reor", use that basename;
    # otherwise fall back to the subject-based name
    if "_summed" in in_base or "_reor" in in_base:
        out_file = os.path.join(out_dir, f"{in_base}_norm.nii")
    else:
        out_file = os.path.join(out_dir, f"{subject_id}_pet_norm.nii")
    img  = nib.load(pet_file)
    data = img.get_fdata()
    mean = data[data > 0].mean()
    if mean > 0:
        data_norm = data / mean
    else:
        data_norm = data
    nib.save(nib.Nifti1Image(data_norm.astype(np.float32),
                              img.affine, img.header), out_file)
    print(f"    -> PET normalized (mean={mean:.1f}): {out_file}")
    return out_file

def generate_batch_mat(t1_file, pet_file, subject_id, work_dir,
                      skip_coreg=False):
    """Generate the SPM batch script with Old Segment (SPM8-compatible).
    If skip_coreg=True the Coregister steps are omitted."""
    batch_m = os.path.join(work_dir, f"batch_{subject_id}.m")

    t1_dir      = os.path.dirname(t1_file)
    t1_basename = os.path.basename(t1_file)

    # Old Segment generates _seg_sn.mat
    seg_sn_file = os.path.join(t1_dir,
                               t1_basename.replace('.nii', '_seg_sn.mat'))

    # SPM tissue priors for Old Segment (in toolbox/OldSeg)
    spm_oldseg = os.path.normpath(os.path.join(os.path.dirname(MNI_TEMPLATE),
                                                '..', 'toolbox', 'OldSeg'))
    grey  = os.path.join(spm_oldseg, 'grey.nii')
    white = os.path.join(spm_oldseg, 'white.nii')
    csf   = os.path.join(spm_oldseg, 'csf.nii')

    if skip_coreg:
        script = f"""% Centiloid batch - Subject {subject_id} (no Coregister - Old Segment)
% Automatically generated by centiloid_pipeline_tracers.py

spm('defaults', 'PET');
spm_jobman('initcfg');

matlabbatch{{1}}.spm.tools.oldseg.data           = {{'{t1_file},1'}};
matlabbatch{{1}}.spm.tools.oldseg.output.GM      = [0 0 1];
matlabbatch{{1}}.spm.tools.oldseg.output.WM      = [0 0 1];
matlabbatch{{1}}.spm.tools.oldseg.output.CSF     = [0 0 0];
matlabbatch{{1}}.spm.tools.oldseg.output.biascor = 1;
matlabbatch{{1}}.spm.tools.oldseg.output.cleanup = 0;
matlabbatch{{1}}.spm.tools.oldseg.opts.tpm       = {{'{grey}';'{white}';'{csf}'}};
matlabbatch{{1}}.spm.tools.oldseg.opts.ngaus     = [2 2 2 4];
matlabbatch{{1}}.spm.tools.oldseg.opts.regtype   = 'mni';
matlabbatch{{1}}.spm.tools.oldseg.opts.warpreg   = 1;
matlabbatch{{1}}.spm.tools.oldseg.opts.warpco    = 25;
matlabbatch{{1}}.spm.tools.oldseg.opts.biasreg   = 0.0001;
matlabbatch{{1}}.spm.tools.oldseg.opts.biasfwhm  = 60;
matlabbatch{{1}}.spm.tools.oldseg.opts.samp      = 3;
matlabbatch{{1}}.spm.tools.oldseg.opts.msk       = {{''}};

matlabbatch{{2}}.spm.spatial.normalise.write.subj.matname  = {{'{seg_sn_file}'}};
matlabbatch{{2}}.spm.spatial.normalise.write.subj.resample = {{'{t1_file},1'; '{pet_file},1'}};
matlabbatch{{2}}.spm.spatial.normalise.write.woptions.bb   = [-90 -126 -72; 90 90 108];
matlabbatch{{2}}.spm.spatial.normalise.write.woptions.vox  = [2 2 2];
matlabbatch{{2}}.spm.spatial.normalise.write.woptions.interp = 1;
matlabbatch{{2}}.spm.spatial.normalise.write.woptions.wrap   = [0 0 0];
matlabbatch{{2}}.spm.spatial.normalise.write.woptions.prefix = 'w';

spm_jobman('run', matlabbatch);
exit;
"""
    else:
        script = f"""% Centiloid batch - Subject {subject_id} (Old Segment)
% Automatically generated by centiloid_pipeline_tracers.py

spm('defaults', 'PET');
spm_jobman('initcfg');

matlabbatch{{1}}.spm.spatial.coreg.estimate.ref    = {{'{MNI_TEMPLATE},1'}};
matlabbatch{{1}}.spm.spatial.coreg.estimate.source = {{'{t1_file},1'}};
matlabbatch{{1}}.spm.spatial.coreg.estimate.other  = {{''}};
matlabbatch{{1}}.spm.spatial.coreg.estimate.eoptions.cost_fun = 'nmi';
matlabbatch{{1}}.spm.spatial.coreg.estimate.eoptions.sep      = [4 2];
matlabbatch{{1}}.spm.spatial.coreg.estimate.eoptions.tol      = [0.02 0.02 0.02 0.001 0.001 0.001 0.01 0.01 0.01 0.001 0.001 0.001];
matlabbatch{{1}}.spm.spatial.coreg.estimate.eoptions.fwhm     = [7 7];

matlabbatch{{2}}.spm.spatial.coreg.estimate.ref    = {{'{t1_file},1'}};
matlabbatch{{2}}.spm.spatial.coreg.estimate.source = {{'{pet_file},1'}};
matlabbatch{{2}}.spm.spatial.coreg.estimate.other  = {{''}};
matlabbatch{{2}}.spm.spatial.coreg.estimate.eoptions.cost_fun = 'nmi';
matlabbatch{{2}}.spm.spatial.coreg.estimate.eoptions.sep      = [4 2];
matlabbatch{{2}}.spm.spatial.coreg.estimate.eoptions.tol      = [0.02 0.02 0.02 0.001 0.001 0.001 0.01 0.01 0.01 0.001 0.001 0.001];
matlabbatch{{2}}.spm.spatial.coreg.estimate.eoptions.fwhm     = [7 7];

matlabbatch{{3}}.spm.tools.oldseg.data           = {{'{t1_file},1'}};
matlabbatch{{3}}.spm.tools.oldseg.output.GM      = [0 0 1];
matlabbatch{{3}}.spm.tools.oldseg.output.WM      = [0 0 1];
matlabbatch{{3}}.spm.tools.oldseg.output.CSF     = [0 0 0];
matlabbatch{{3}}.spm.tools.oldseg.output.biascor = 1;
matlabbatch{{3}}.spm.tools.oldseg.output.cleanup = 0;
matlabbatch{{3}}.spm.tools.oldseg.opts.tpm       = {{'{grey}';'{white}';'{csf}'}};
matlabbatch{{3}}.spm.tools.oldseg.opts.ngaus     = [2 2 2 4];
matlabbatch{{3}}.spm.tools.oldseg.opts.regtype   = 'mni';
matlabbatch{{3}}.spm.tools.oldseg.opts.warpreg   = 1;
matlabbatch{{3}}.spm.tools.oldseg.opts.warpco    = 25;
matlabbatch{{3}}.spm.tools.oldseg.opts.biasreg   = 0.0001;
matlabbatch{{3}}.spm.tools.oldseg.opts.biasfwhm  = 60;
matlabbatch{{3}}.spm.tools.oldseg.opts.samp      = 3;
matlabbatch{{3}}.spm.tools.oldseg.opts.msk       = {{''}};

matlabbatch{{4}}.spm.spatial.normalise.write.subj.matname  = {{'{seg_sn_file}'}};
matlabbatch{{4}}.spm.spatial.normalise.write.subj.resample = {{'{t1_file},1'; '{pet_file},1'}};
matlabbatch{{4}}.spm.spatial.normalise.write.woptions.bb   = [-90 -126 -72; 90 90 108];
matlabbatch{{4}}.spm.spatial.normalise.write.woptions.vox  = [2 2 2];
matlabbatch{{4}}.spm.spatial.normalise.write.woptions.interp = 1;
matlabbatch{{4}}.spm.spatial.normalise.write.woptions.wrap   = [0 0 0];
matlabbatch{{4}}.spm.spatial.normalise.write.woptions.prefix = 'w';

spm_jobman('run', matlabbatch);
exit;
"""
    with open(batch_m, "w") as f:
        f.write(script)

    return batch_m



def run_spm(batch_m):
    """Run the SPM batch, auto-detecting whether to go through SPM12
    standalone + MATLAB Runtime (no MATLAB license needed) or a real MATLAB +
    SPM12 install -- whichever is actually present on this machine, no manual
    choice needed (see docs/INSTALL.md section 8). batch_m already ends with
    its own exit/spm_jobman('run', ...) call, which matches both invocation
    styles: MATLAB's -r runs it as a script, and SPM12 standalone's "batch"
    subcommand accepts a self-contained .m script the same way."""
    standalone_ready = bool(
        SPM_STANDALONE_RUN and SPM_MCR_DIR
        and os.path.exists(SPM_STANDALONE_RUN)
        and os.path.isdir(SPM_MCR_DIR)
    )
    if standalone_ready:
        run(
            [SPM_STANDALONE_RUN, SPM_MCR_DIR, "batch", batch_m],
            "SPM12 standalone (no MATLAB license)"
        )
        return

    if not os.path.exists(MATLAB_BIN):
        sys.exit(
            "ERROR: neither SPM12 standalone nor MATLAB were found.\n"
            f"  Standalone: CENTILOID_SPM_STANDALONE_RUN={SPM_STANDALONE_RUN!r}, "
            f"CENTILOID_SPM_MCR_DIR={SPM_MCR_DIR!r}\n"
            f"  MATLAB:     CENTILOID_MATLAB_BIN={MATLAB_BIN!r} (does not exist)\n"
            "Install one of the two and set its path(s) -- see docs/INSTALL.md section 8."
        )

    matlab_cmd = (
        f"addpath('{SPM12_PATH}'); "
        f"try, run('{batch_m}'); catch e, disp(getReport(e)); exit(1); end; "
        f"exit(0);"
    )
    run(
        [MATLAB_BIN, "-nodisplay", "-nosplash", "-nodesktop", "-r", matlab_cmd],
        "SPM12 via MATLAB"
    )


# =============================================
# STEP 4 - EXTRACT SUVr
# =============================================

def fslstats_mean(pet_file, mask_file):
    result = subprocess.run(
        ["fslstats", pet_file, "-k", mask_file, "-M"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"fslstats failed:\n{result.stderr}")
    value = result.stdout.strip()
    if not value:
        raise ValueError("fslstats returned no value")
    val = float(value)
    if val == 0.0:
        raise ValueError(
            f"fslstats returned 0 for {os.path.basename(mask_file)} -- "
            "the PET does not overlap with the VOI. "
            "Check the registration with: fsleyes wPET.nii avg152T1.nii"
        )
    return val


def extract_suvr(wpet_file, voi_dir, voi_map, voi_method="avid"):
    """Extract the CTX SUVr and Centiloid from the normalized PET.

    Supports two VOI methods:
    - "avid"  (default): 6 cortical VOIs of Joshi 2015 + whole cerebellum
              (cere_all.nii.gz). CTX SUVr = mean(6 VOIs) / cerebellum.
    - "klunk": GAAIN Standard Centiloid VOIs. A single cortical VOI
              (voi_ctx_2mm.nii) + whole cerebellum (voi_WhlCbl_2mm.nii).
              CTX SUVr = ctx_voi / cerebellum.

    If the wPET shape does not match the VOIs, it is adjusted to the
    correct space using padding/cropping without interpolation.
    """
    import nibabel as nib

    # Determine the cerebellum file and region name according to the method
    if voi_method == "klunk":
        ref_voi_file = "voi_WhlCbl_2mm.nii"
        cere_region  = "wcb_klunk"
    else:  # avid
        ref_voi_file = "cere_all.nii.gz"
        cere_region  = "blcere_all"

    # Check dimensions against the reference VOI
    ref_voi  = os.path.join(voi_dir, ref_voi_file)
    pet_img  = nib.load(wpet_file)
    voi_img  = nib.load(ref_voi)

    if pet_img.shape[:3] != voi_img.shape[:3]:
        print(f"    ! wPET shape {pet_img.shape[:3]} != VOI shape {voi_img.shape[:3]}")
        print(f"    -> Adjusting to the standard MNI space without interpolation...")

        pet_data = pet_img.get_fdata()
        tgt_shape = voi_img.shape[:3]
        tgt_affine = voi_img.affine

        new_data = np.zeros(tgt_shape, dtype=np.float32)

        pet_origin  = np.array(pet_img.affine[:3, 3])
        voi_origin  = np.array(voi_img.affine[:3, 3])
        vox_signed  = np.diag(voi_img.affine[:3, :3])
        offset      = np.round((pet_origin - voi_origin) / vox_signed).astype(int)

        src_start = np.maximum(0, -offset)
        src_end   = np.minimum(np.array(pet_data.shape[:3]),
                               np.array(tgt_shape) - offset)

        dst_start = np.maximum(0, offset)
        dst_end   = dst_start + (src_end - src_start)

        if np.all(src_end > src_start) and np.all(dst_end > dst_start):
            new_data[dst_start[0]:dst_end[0],
                     dst_start[1]:dst_end[1],
                     dst_start[2]:dst_end[2]] = \
                pet_data[src_start[0]:src_end[0],
                         src_start[1]:src_end[1],
                         src_start[2]:src_end[2]]
        else:
            raise ValueError(
                "wPET and VOI space do not intersect -- "
                "registration probably failed"
            )

        adjusted = os.path.splitext(wpet_file)[0] + "_adjusted.nii"
        nib.save(nib.Nifti1Image(new_data, tgt_affine), adjusted)
        wpet_file = adjusted
        print(f"    -> Adjusted: {adjusted}")

    raw_values = {}
    for voi_file, region_name in voi_map.items():
        mask_path = os.path.join(voi_dir, voi_file)
        if not os.path.exists(mask_path):
            raise FileNotFoundError(f"VOI not found: {mask_path}")
        raw_values[region_name] = fslstats_mean(wpet_file, mask_path)

    cere = raw_values[cere_region]

    if cere == 0 or np.isnan(cere):
        raise ValueError(
            "Cerebellum value is 0 or nan -- the PET does not overlap with the VOI. "
            "Check the registration with: fsleyes wPET.nii avg152T1.nii"
        )

    suvr = {r: v / cere for r, v in raw_values.items()
            if r != cere_region}

    bad = [r for r, v in suvr.items() if np.isnan(v) or v == 0]
    if bad:
        raise ValueError(
            f"Regions with value 0 or nan: {bad} -- "
            "registration probably failed. "
            "Check with: fsleyes wPET.nii avg152T1.nii"
        )

    # CTX SUVr:
    #  - Avid: mean of the 6 cortical regions (Joshi et al. 2015)
    #  - Klunk: the single cortical VOI (Standard Centiloid)
    ctx_suvr  = float(np.mean(list(suvr.values())))
    centiloid = CL_SLOPE * ctx_suvr + CL_INTERCEPT

    return raw_values, suvr, ctx_suvr, centiloid


# =============================================
# IMMEDIATE PER-SUBJECT QC
# =============================================

def qc_inline(subject_id, ctx_suvr, centiloid, ref_xlsx, wpet_file,
              tracer="fbp", voi_method="avid", suvr_thresh=0.05, cl_thresh=5.0):
    """
    Compare the subject's SUVr and Centiloid against the reference
    spreadsheet. The spreadsheet columns are read according to the
    (tracer, voi_method) combination defined in TRACER_CONFIG.
    If the difference exceeds the threshold, a warning with a suggestion
    is shown.
    """
    if not ref_xlsx or not os.path.exists(ref_xlsx):
        return

    cfg = TRACER_CONFIG[tracer]["calibration"][voi_method]
    col_id   = cfg["ref_col_id"]
    col_suvr = cfg["ref_col_suvr"]
    col_cl   = cfg["ref_col_centiloid"]

    # If this mode has no reference in the spreadsheet (e.g. voi_method=avid),
    # silently skip the inline QC
    if col_id is None or col_suvr is None or col_cl is None:
        return

    try:
        raw = pd.read_excel(ref_xlsx, header=None)
        df  = raw.iloc[2:, [col_id, col_suvr, col_cl]].copy()
        df.columns = ["subject_id", "suvr_published", "centiloid_published"]
        df["subject_id"] = df["subject_id"].astype(str).str.strip()
        row = df[df["subject_id"] == str(subject_id)]
        if row.empty:
            return

        try:
            suvr_ref = float(row["suvr_published"].values[0])
            cl_ref   = float(row["centiloid_published"].values[0])
        except (ValueError, TypeError):
            print(f"  (Immediate QC: non-numeric values in spreadsheet columns "
                  f"{col_suvr}/{col_cl} for {subject_id})")
            return

        diff_suvr = abs(ctx_suvr - suvr_ref) / suvr_ref * 100
        diff_cl   = abs(centiloid - cl_ref)

        sep = "-" * 55
        print(f"\n{sep}")
        print(f"  Immediate QC -- {subject_id}")
        print(sep)
        print(f"  {'Metric':<18} {'Pipeline':>10} {'Reference':>12} {'Difference':>12}")
        print(f"  {'-'*52}")
        print(f"  {'CTX SUVr':<18} {ctx_suvr:>10.4f} {suvr_ref:>12.4f} {diff_suvr:>11.2f}%")
        print(f"  {'Centiloid':<18} {centiloid:>10.2f} {cl_ref:>12.2f} {diff_cl:>11.2f} CL")
        print(f"  {'-'*52}")

        suvr_ok = diff_suvr <= suvr_thresh * 100
        cl_ok   = diff_cl   <= cl_thresh

        if suvr_ok and cl_ok:
            print(f"  OK  SUVr {diff_suvr:.2f}% | Centiloid {diff_cl:.2f} CL -- within threshold")
        else:
            print(f"  WARNING: differences outside the threshold:")
            if not suvr_ok:
                print(f"    SUVr:      {diff_suvr:.2f}% (threshold: {suvr_thresh*100:.0f}%)")
            if not cl_ok:
                print(f"    Centiloid: {diff_cl:.2f} CL (threshold: {cl_thresh:.0f} CL)")
            print(f"\n  Suggestion: redo the coregistration for {subject_id}")
            print(f"    1. Delete the processed files of this subject")
            print(f"    2. Reorient manually in SPM Display")
            print(f"    3. Run Coregister MRI->MNI and PET->MRI in SPM")
            print(f"    4. Re-run the pipeline:")
            print(f"       python centiloid_pipeline_tracers.py --test {subject_id} --skip_dcm2niix --skip_coreg")
            print(f"    5. Check the wPET with:")
            print(f"       fsleyes {wpet_file} avg152T1.nii")
        print(sep)

    except Exception as e:
        print(f"  (Immediate QC not available: {e})")


# =============================================
# FULL PIPELINE PER SUBJECT
# =============================================

def process_subject(subject_id, base_dir, voi_dir, out_dir, ref_xlsx,
                    skip_dcm2niix=False, skip_coreg=False, skip_spm=False,
                    use_reor=False, auto_reorient=False,
                    tracer="fbp", reuse_t1_from=None, voi_method="avid",
                    reorient_method="a"):
    """
    Run the full pipeline for one subject:
    DICOM -> NIfTI -> PET sum -> [auto-reorient] -> SPM -> SUVr

    If use_reor=True, look for pre-existing *_reor.nii files in the
    subject's work folder. If they do not exist, fall back to the
    originals.

    If auto_reorient=True, compute the *_reor.nii files internally
    (method given by reorient_method; "a" = shared offset) and use them
    instead of the originals for SPM. Reorientation is only applied if
    |COM_MRI|>30mm or |COM_PET|>50mm.

    tracer: "fbp" or "pib" -- determines the Centiloid calibration and
        where to look for the PET DICOMs. Default: "fbp".

    voi_method: "avid" (6 VOIs of Joshi 2015) or "klunk" (Standard
        Centiloid VOIs). Determines which VOIs are used and the
        calibration. Default: "avid".

    reuse_t1_from: path to a folder with already converted T1 images (e.g.
        from a previous FBP run). If provided and the T1 exists there,
        it is copied to the current work_dir instead of re-converting
        the DICOM. Useful to process PiB reusing the T1 images of an FBP run.
    """
    print(f"\n{'='*55}")
    print(f"  Subject: {subject_id}  (tracer: {tracer}, VOIs: {voi_method})")
    print(f"{'='*55}")

    work_dir = os.path.join(out_dir, subject_id)
    os.makedirs(work_dir, exist_ok=True)

    # -- Step 1: Convert DICOMs ----------------------------
    if skip_dcm2niix:
        print("\n[1/4] Skipping DICOM conversion (--skip_dcm2niix)...")

        if use_reor:
            # Prefer reoriented files if they exist
            t1_reor  = glob.glob(os.path.join(work_dir, f"{subject_id}_t1*_reor.nii"))
            pet_reor = glob.glob(os.path.join(work_dir, f"{subject_id}_pet_summed_reor.nii")) + \
                       glob.glob(os.path.join(work_dir, f"{subject_id}_pet_reor.nii"))
            if t1_reor and pet_reor:
                t1_file    = t1_reor[0]
                pet_summed = pet_reor[0]
                print(f"    [use_reor] T1:  {os.path.basename(t1_file)}")
                print(f"    [use_reor] PET: {os.path.basename(pet_summed)}")
            else:
                missing = []
                if not t1_reor:  missing.append("T1_reor")
                if not pet_reor: missing.append("PET_reor")
                print(f"    !  --use_reor but not found: {missing}")
                print(f"       Falling back to the original files (not reoriented)")
                use_reor = False  # flag for the following steps

        if not use_reor:
            t1_candidates  = [f for f in
                glob.glob(os.path.join(work_dir, f"{subject_id}_t1*.nii"))
                if "_reor" not in os.path.basename(f)]
            pet_candidates = [f for f in
                glob.glob(os.path.join(work_dir, f"{subject_id}_pet.nii"))
                if "_reor" not in os.path.basename(f)]
            if not t1_candidates:
                raise FileNotFoundError(f"T1 not found in {work_dir}")
            if not pet_candidates:
                raise FileNotFoundError(f"PET not found in {work_dir}")
            t1_file    = t1_candidates[0]
            pet_summed = pet_candidates[0]
            print(f"    T1:  {os.path.basename(t1_file)}")
            print(f"    PET: {os.path.basename(pet_summed)}")
    else:
        print("\n[1/4] Converting DICOMs...")

        # T1: if reuse_t1_from exists and has the subject's T1, copy it
        # instead of re-converting the DICOM. Common when processing PiB
        # after FBP -- the T1 images are already converted.
        t1_file = None
        if reuse_t1_from:
            src_dir = os.path.join(reuse_t1_from, subject_id)
            t1_src = [f for f in glob.glob(os.path.join(src_dir, f"{subject_id}_t1*.nii"))
                      if "_reor" not in os.path.basename(f)
                      and not os.path.basename(f).startswith("w")]
            if t1_src:
                import shutil
                t1_file = os.path.join(work_dir, os.path.basename(t1_src[0]))
                if not os.path.exists(t1_file):
                    shutil.copy2(t1_src[0], t1_file)
                print(f"    T1 reused from {reuse_t1_from}: {os.path.basename(t1_file)}")

        if t1_file is None:
            mri_dicom_dirs = find_dicom_dirs(base_dir, subject_id, "mri", tracer=tracer)
            print(f"    MRI DICOM: {mri_dicom_dirs[0]}")
            mri_niftis = convert_dicom(mri_dicom_dirs[0], work_dir, f"{subject_id}_t1")
            t1_file    = mri_niftis[0]

        # PET: there may be 1 or several DICOM folders (PiB with separate frames)
        pet_dicom_dirs = find_dicom_dirs(base_dir, subject_id, "pet", tracer=tracer)
        print(f"    PET DICOM: {len(pet_dicom_dirs)} folder(s)")
        for d in pet_dicom_dirs:
            print(f"      - {d}")
        pet_niftis = convert_dicom(pet_dicom_dirs, work_dir, f"{subject_id}_pet")

        # -- Step 2: Sum PET frames -----------------------
        print("\n[2/4] Summing PET frames...")
        pet_summed = sum_pet_frames(pet_niftis, work_dir, subject_id)

    # -- Step 2.5: Auto-reorientation ---------------------
    # Only if explicitly requested and we are not already using
    # pre-reoriented files (use_reor) nor skipping SPM (skip_spm).
    if auto_reorient and not skip_spm:
        if "_reor" in os.path.basename(t1_file):
            print("\n[2.5/4] Auto-reorientation: input is already _reor, skipping")
        else:
            label = "method A" if reorient_method == "a" else "method B"
            print(f"\n[2.5/4] Auto-reorientation ({label})...")
            t1_file, pet_summed, _info = auto_reorient_subject(
                t1_file, pet_summed, work_dir,
                th_mri=REORIENT_TH_MRI_MM, th_pet=REORIENT_TH_PET_MM,
                method=reorient_method)

    # -- Step 3: SPM (Coreg + Segment + Normalise) --------
    if skip_spm:
        print("\n[3/4] Skipping SPM (--skip_spm)...")
        # Look for the wPET corresponding to the chosen pet_summed.
        # Convention: SPM prepends "w" to the *_norm.nii file it receives.
        pet_summed_base = os.path.basename(pet_summed).replace(".nii", "")
        wpet_candidates = (
            glob.glob(os.path.join(work_dir, f"w{pet_summed_base}_norm.nii")) +
            glob.glob(os.path.join(work_dir, f"w{pet_summed_base}.nii"))
        )
        if not wpet_candidates:
            # Broad fallback
            wpet_candidates = glob.glob(
                os.path.join(work_dir, f"w{subject_id}_pet*.nii"))
    else:
        print("\n[3/4] Running SPM...")
        pet_norm = normalize_pet(pet_summed, work_dir, subject_id)
        batch_m  = generate_batch_mat(t1_file, pet_norm, subject_id, work_dir,
                                      skip_coreg=skip_coreg)
        run_spm(batch_m)
        pet_norm_basename = os.path.basename(pet_norm)
        wpet_candidates = glob.glob(
            os.path.join(work_dir, f"w{pet_norm_basename}"))

    if not wpet_candidates:
        raise FileNotFoundError(
            f"SPM did not generate a wPET for {subject_id}. "
            f"Check the log in {work_dir}")
    wpet_file = wpet_candidates[0]
    print(f"    -> wPET: {wpet_file}")

    # -- Step 4: Extract SUVr -----------------------------
    print("\n[4/4] Extracting SUVr...")
    # Use the correct VOI map for the method
    current_voi_map = VOI_MAP_KLUNK if voi_method == "klunk" else VOI_MAP_AVID
    raw_values, suvr, ctx_suvr, centiloid = \
        extract_suvr(wpet_file, voi_dir, current_voi_map, voi_method=voi_method)

    print(f"    CTX SUVr:  {ctx_suvr:.4f}")
    print(f"    Centiloid: {centiloid:.2f}")

    # Immediate QC vs reference (if available)
    qc_inline(subject_id, ctx_suvr, centiloid, ref_xlsx=ref_xlsx,
              wpet_file=wpet_file, tracer=tracer, voi_method=voi_method)

    return {
        "subject_id":         subject_id,
        "wpet_file":          wpet_file,
        "ctx_suvr":           ctx_suvr,
        "centiloid_pipeline": centiloid,
        **{f"suvr_{k}": v for k, v in suvr.items()},
        "status":             "ok",
        "error":              "",
    }


# =============================================
# GLOBAL QC (--all only)
# =============================================

def load_reference(path, tracer="fbp", voi_method="avid"):
    """Read the reference spreadsheet using the columns that correspond
    to the (tracer, voi_method) combination.
    Returns None if there is no reference for that mode."""
    cfg = TRACER_CONFIG[tracer]["calibration"][voi_method]
    col_id    = cfg["ref_col_id"]
    col_group = cfg["ref_col_group"]
    col_suvr  = cfg["ref_col_suvr"]
    col_cl    = cfg["ref_col_centiloid"]

    if col_id is None or col_suvr is None or col_cl is None:
        # Mode without a reference in the spreadsheet
        return None

    raw = pd.read_excel(path, header=None)
    df  = raw.iloc[2:, [col_id, col_group, col_suvr, col_cl]].copy()
    df.columns = ["subject_id", "group",
                  "suvr_published", "centiloid_published"]
    df["subject_id"]          = df["subject_id"].astype(str).str.strip()
    df["centiloid_published"]  = pd.to_numeric(
        df["centiloid_published"], errors="coerce")
    df["suvr_published"]       = pd.to_numeric(
        df["suvr_published"],      errors="coerce")
    return df.dropna(subset=["centiloid_published"])


def generate_qc(csv_path, ref_xlsx, out_dir, tracer="fbp", voi_method="avid"):
    """Compute slope, intercept and R2 and generate a scatter plot.
    Only called in --all mode once all subjects have finished."""
    df_results = pd.read_csv(csv_path)
    df_results["subject_id"] = df_results["subject_id"].astype(str)

    # Only subjects with status=ok
    df_results = df_results[df_results["status"] == "ok"].copy()
    df_results["centiloid_pipeline"] = pd.to_numeric(
        df_results["centiloid_pipeline"], errors="coerce")

    df_ref    = load_reference(ref_xlsx, tracer=tracer, voi_method=voi_method)
    if df_ref is None:
        print(f"\n  Mode {tracer}+{voi_method} has no reference in the spreadsheet")
        print(f"  (the spreadsheet columns are only comparable with voi_method=klunk).")
        print(f"  Skipping global QC and scatter plot.")
        return
    df_merged = df_results.merge(df_ref, on="subject_id", how="inner")

    if df_merged.empty:
        print("!  No match between processed subjects and the reference.")
        return

    df_valid = df_merged.dropna(subset=["centiloid_pipeline", "centiloid_published"])
    n_total  = len(df_merged)
    n_valid  = len(df_valid)
    n_nan    = n_total - n_valid

    if n_nan > 0:
        nan_ids = df_merged[df_merged["centiloid_pipeline"].isna()]["subject_id"].tolist()
        print(f"\n  ! {n_nan} subjects excluded from the QC due to nan/zero: {nan_ids}")
        print(f"  Suggestion: redo the coregistration for these subjects\n")

    if n_valid < 3:
        print("  X Fewer than 3 valid subjects to compute the regression.")
        return

    x = df_valid["centiloid_published"].values
    y = df_valid["centiloid_pipeline"].values
    slope, intercept, r, _, _ = stats.linregress(x, y)
    r2 = r ** 2

    slope_ok     = SLOPE_MIN <= slope <= SLOPE_MAX
    intercept_ok = abs(intercept) <= INTERCEPT_MAX
    r2_ok        = r2 >= R2_MIN

    sep = "-" * 55
    print(f"\n{sep}")
    print(f"  Global QC - {n_valid}/{n_total} valid subjects")
    print(sep)
    print(f"\n  {'Metric':<15} {'Value':>10}  {'Criterion':<12} {'OK?':>4}")
    print(f"  {'-'*45}")
    print(f"  {'Slope':<15} {slope:>10.4f}  {'0.98-1.02':<12} "
          f"{'OK' if slope_ok else 'X':>4}")
    print(f"  {'Intercept':<15} {intercept:>10.4f}  {'+-2 CL':<12} "
          f"{'OK' if intercept_ok else 'X':>4}")
    print(f"  {'R2':<15} {r2:>10.4f}  {'>0.98':<12} "
          f"{'OK' if r2_ok else 'X':>4}")
    print(f"\n  {'-'*45}")
    if slope_ok and intercept_ok and r2_ok:
        print("  OK Pipeline PASSED")
    else:
        print("  X Pipeline REJECTED - check the registration")
    print(f"{sep}\n")

    # Scatter plot
    fig, ax = plt.subplots(figsize=(7, 7))
    group_col = "group" if "group" in df_valid.columns else None
    if group_col:
        for grp, color in [("YHC", "#2196F3"), ("AD", "#F44336"),
                           ("NC", "#4CAF50"),  ("MCI", "#FF9800"),
                           ("Clinical AD", "#9C27B0")]:
            mask = df_valid[group_col] == grp
            if mask.any():
                ax.scatter(df_valid.loc[mask, "centiloid_published"],
                           df_valid.loc[mask, "centiloid_pipeline"],
                           c=color, label=grp, alpha=0.8,
                           edgecolors="white", s=60)
        ax.legend(fontsize=10)
    else:
        ax.scatter(x, y, c="#5C6BC0", alpha=0.8, edgecolors="white", s=60)

    vmin = min(x.min(), y.min()) - 5
    vmax = max(x.max(), y.max()) + 5
    xl   = np.linspace(vmin, vmax, 200)
    ax.plot(xl, xl, "--", color="gray", linewidth=1.2, label="Identity")
    ax.plot(xl, slope * xl + intercept, "-", color="#E91E63", linewidth=2,
            label=f"y={slope:.3f}x+{intercept:.2f}  R2={r2:.4f}")

    txt = (f"Slope:     {slope:.4f}  {'OK' if slope_ok else 'X'}\n"
           f"Intercept: {intercept:.4f}  {'OK' if intercept_ok else 'X'}\n"
           f"R2:        {r2:.4f}  {'OK' if r2_ok else 'X'}\n"
           f"n valid:   {n_valid}/{n_total}")
    ax.text(0.03, 0.97, txt, transform=ax.transAxes, fontsize=10,
            va="top", fontfamily="monospace",
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.8))

    ax.set_xlabel("Published Centiloid", fontsize=12)
    ax.set_ylabel("Centiloid - this pipeline", fontsize=12)
    ax.set_title("Project Centiloid validation", fontsize=13, fontweight="bold")
    ax.legend(fontsize=10)
    ax.set_xlim(vmin, vmax)
    ax.set_ylim(vmin, vmax)
    ax.grid(True, alpha=0.3)

    plot_path = os.path.join(out_dir, "centiloid_validation.png")
    fig.savefig(plot_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Plot saved: {plot_path}")


# =============================================
# ARGUMENTS
# =============================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="Complete Centiloid pipeline - DICOM -> SUVr -> QC",
        formatter_class=argparse.RawTextHelpFormatter
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--test", metavar="SUBJECT_ID",
        help="Run a single subject (e.g. --test <SUBJECT_ID>)")
    mode.add_argument("--all", action="store_true",
        help="Run all subjects in a loop (generates a validation plot)")

    parser.add_argument("--skip_dcm2niix", action="store_true",
        help="Skip DICOM conversion and frame summation (use existing NIfTIs)")
    parser.add_argument("--skip_coreg", action="store_true",
        help="Skip Coregister in SPM (use already modified headers)")
    parser.add_argument("--skip_spm", action="store_true",
        help="Skip SPM entirely (use an existing wPET, only extract the SUVr)")
    parser.add_argument("--use_reor", action="store_true",
        help="Use pre-existing *_reor.nii files "
             "(requires --skip_dcm2niix). If they do not exist, fall back "
             "to the originals.")
    parser.add_argument("--auto_reorient", action="store_true",
        help="Auto-reorient the images (see --reorient_method; default: shared "
             "offset) before SPM. Recommended: rescues subjects whose center "
             "of mass is far from MNI without affecting the ones that are fine.")
    parser.add_argument("--reorient_method", choices=["a", "b"], default="a",
        help="Method of --auto_reorient. 'a' (default, shared offset): "
             "safe, does not break subjects that already worked, but does not "
             "correct large PET-MRI displacements already present in the raw "
             "data. 'b' (independent offsets, centroids): directly addresses "
             "large displacements, but may break subjects that 'a' handles "
             "if PET and MRI were already reasonably aligned "
             "-- use it selectively on subjects where 'a' failed, not as a "
             "general default.")

    parser.add_argument("--tracer", choices=["fbp", "pib"], default="fbp",
        help="Tracer to process: 'fbp' (Florbetapir, default) or 'pib' (C-11 PiB).\n"
             "Changes: Centiloid calibration, DICOM search folders,\n"
             "and the default output folder (results/ vs results_pib/).")
    parser.add_argument("--voi_method", choices=["avid", "klunk"], default="klunk",
        help="VOI method: 'avid' (6 cortical VOIs of Joshi 2015) or\n"
             "'klunk' (GAAIN Standard Centiloid VOIs, voi_ctx_2mm + voi_WhlCbl_2mm, default).\n"
             "Changes: VOIs read, Centiloid calibration (Eq 2A vs 2B in Navitsky\n"
             "2018) and output folder (suffix '_klunk').")
    parser.add_argument("--reuse_t1_from", default=None,
        help="Path to a results folder of another run (e.g. 'results').\n"
             "If it has the subject's converted T1, it is copied instead of\n"
             "re-converting the DICOM. Useful for PiB after an FBP run on the same cohort.")

    parser.add_argument("--base_dir", default=BASE_DIR,
        help=f"Root directory of the data (default: {BASE_DIR})")
    parser.add_argument("--ref_xlsx", default=REF_XLSX,
        help="Avid reference spreadsheet")
    parser.add_argument("--voi", default=None,
        help="VOI folder (default: derived from --voi_method:\n"
             f"  avid  -> {VOI_DIR}\n"
             f"  klunk -> {VOI_DIR_KLUNK})")
    parser.add_argument("--out", default=None,
        help="Output folder (default: derived from tracer + voi_method:\n"
             "  fbp + avid  -> results/\n"
             "  fbp + klunk -> results_klunk/\n"
             "  pib + avid  -> results_pib/\n"
             "  pib + klunk -> results_pib_klunk/)")

    return parser.parse_args()


# =============================================
# MAIN
# =============================================

def main():
    global CL_SLOPE, CL_INTERCEPT, CL_THRESHOLD_POSITIVE, SUVR_THRESHOLD_POSITIVE

    args = parse_args()

    # ---- Apply the (tracer, voi_method) configuration ----
    tracer_cfg = TRACER_CONFIG[args.tracer]
    cal_cfg    = tracer_cfg["calibration"][args.voi_method]
    CL_SLOPE                = cal_cfg["cl_slope"]
    CL_INTERCEPT            = cal_cfg["cl_intercept"]
    CL_THRESHOLD_POSITIVE   = cal_cfg["cl_threshold"]
    SUVR_THRESHOLD_POSITIVE = cal_cfg["suvr_threshold"]

    # If the user did not pass --voi, derive it from voi_method
    if args.voi is None:
        args.voi = VOI_DIR_KLUNK if args.voi_method == "klunk" else VOI_DIR

    # If the user did not pass --out, derive it from (tracer, voi_method)
    # Convention: <base>/<tracer.out_subdir>[_klunk]/
    if args.out is None:
        out_sub = tracer_cfg["out_subdir"]
        if args.voi_method == "klunk":
            out_sub = out_sub + "_klunk"
        args.out = os.path.join(args.base_dir, out_sub)

    os.makedirs(args.out, exist_ok=True)

    # Check that the VOI folder exists and warn if not
    if not os.path.isdir(args.voi):
        print(f"\nX VOI folder does not exist: {args.voi}")
        if args.voi_method == "klunk":
            print(f"  To use --voi_method klunk, download the Standard Centiloid VOIs")
            print(f"  from GAAIN (https://www.gaain.org/centiloid-project) and unzip them")
            print(f"  into {args.voi}. Required: voi_ctx_2mm.nii, voi_WhlCbl_2mm.nii")
        sys.exit(1)

    print("\n=== Centiloid Pipeline ===")
    print(f"  Tracer:        {tracer_cfg['name']} ({args.tracer})")
    print(f"  VOI method:    {args.voi_method}")
    print(f"  Calibration:   CL = {CL_SLOPE} * SUVr + ({CL_INTERCEPT})")
    print(f"  Threshold:     {CL_THRESHOLD_POSITIVE} CL = SUVr {SUVR_THRESHOLD_POSITIVE}")
    print(f"  VOI dir:       {args.voi}")
    print(f"  Out dir:       {args.out}")
    if cal_cfg['ref_col_id'] is None:
        print(f"  Excel ref:     N/A (the spreadsheet columns only apply to voi_method=klunk)")
    else:
        print(f"  Excel ref:     col {cal_cfg['ref_col_id']}=id, "
              f"col {cal_cfg['ref_col_suvr']}=SUVr, col {cal_cfg['ref_col_centiloid']}=CL")
    if args.reuse_t1_from:
        print(f"  Reuse T1 from: {args.reuse_t1_from}")

    # Validation: --use_reor only makes sense with --skip_dcm2niix
    if args.use_reor and not args.skip_dcm2niix:
        print("\n  ! --use_reor requires --skip_dcm2niix (the _reor.nii files")
        print("    are generated from already converted NIfTIs).")
        print("    Enabling --skip_dcm2niix automatically.\n")
        args.skip_dcm2niix = True

    # Validation: --auto_reorient + --use_reor is redundant.
    # auto_reorient generates the _reor.nii files internally; use_reor reads them from disk.
    # If both are given, auto_reorient prevails (recomputing is safe).
    if args.auto_reorient and args.use_reor:
        print("\n  ! --auto_reorient and --use_reor are redundant.")
        print("    auto_reorient recomputes the reorientation on every run.")
        print("    Disabling --use_reor.\n")
        args.use_reor = False

    # Validation: --auto_reorient + --skip_spm makes no sense (it would not be used)
    if args.auto_reorient and args.skip_spm:
        print("\n  ! --auto_reorient with --skip_spm: the reorientation would have no")
        print("    effect because SPM is not going to be re-run. Ignoring --auto_reorient.\n")
        args.auto_reorient = False

    # Determine the subjects to process
    if args.test:
        subject_ids = [args.test]
        print(f"\nTest mode - subject: {args.test}\n")
    else:
        subject_ids = get_all_subject_ids(args.base_dir, tracer=args.tracer)
        print(f"\nFull mode - {len(subject_ids)} subjects: "
              f"{subject_ids}\n")

    if not subject_ids:
        print("X No subjects found to process.")
        sys.exit(1)

    # ---- Initial CSV: one row per subject, status='pending' ----
    csv_path = os.path.join(args.out, "centiloid_results.csv")
    init_csv(csv_path, subject_ids)

    n_ok    = 0
    n_error = 0

    for sid in subject_ids:
        try:
            result = process_subject(
                sid, args.base_dir, args.voi, args.out, args.ref_xlsx,
                skip_dcm2niix=args.skip_dcm2niix,
                skip_coreg=args.skip_coreg,
                skip_spm=args.skip_spm,
                use_reor=args.use_reor,
                auto_reorient=args.auto_reorient,
                tracer=args.tracer,
                reuse_t1_from=args.reuse_t1_from,
                voi_method=args.voi_method,
                reorient_method=args.reorient_method)
            # Save the result in the CSV immediately
            update_csv_row(csv_path, sid, result)
            n_ok += 1
            print(f"\n  OK Subject {sid} saved to CSV ({n_ok}/{len(subject_ids)})")

        except ValueError as e:
            # Overlap/zero error -- failed registration
            msg = str(e)
            print(f"\n  WARNING {sid}: {msg}")
            if "does not overlap" in msg or "zero" in msg.lower() or "0" in msg:
                print(f"  Suggestion: redo the coregistration for {sid}")
                print(f"    (reorient in SPM and re-run with --skip_dcm2niix --skip_coreg)")
            update_csv_row(csv_path, sid,
                           {"status": "error", "error": msg[:200]})
            n_error += 1
            print(f"  Continuing with the next subject...\n")

        except Exception as e:
            print(f"\n  X Failed {sid}: {e}")
            update_csv_row(csv_path, sid,
                           {"status": "error", "error": str(e)[:200]})
            n_error += 1
            print(f"  Continuing with the next subject...\n")

    # =========================================
    # Final summary
    # =========================================
    sep = "=" * 55
    print(f"\n{sep}")
    print(f"  FINAL SUMMARY")
    print(sep)
    print(f"  Total subjects:   {len(subject_ids)}")
    print(f"  Processed OK:     {n_ok}")
    print(f"  With errors:      {n_error}")
    print(f"\n  Accumulated results: {csv_path}")

    if n_error > 0:
        # List subjects with errors from the CSV
        df_csv = pd.read_csv(csv_path)
        df_csv["subject_id"] = df_csv["subject_id"].astype(str)
        df_err = df_csv[df_csv["status"] == "error"]
        df_err = df_err[df_err["subject_id"].isin([str(s) for s in subject_ids])]

        if not df_err.empty:
            print(f"\n  REDO COREGISTRATION ({len(df_err)} subjects):")
            for _, row in df_err.iterrows():
                err_msg = str(row.get("error", ""))[:60]
                print(f"    - {row['subject_id']}: {err_msg}...")
            print(f"\n  Then, for each one:")
            print(f"    1. Reorient in SPM Display")
            print(f"    2. Coregister MRI->MNI and PET->MRI in SPM")
            print(f"    3. python centiloid_pipeline_tracers.py --test <ID> --skip_dcm2niix --skip_coreg")

            # Save the list of subjects to redo
            redo_path = os.path.join(args.out, "subjects_to_redo.txt")
            with open(redo_path, "w") as f:
                f.write("subject_id\terror\n")
                for _, row in df_err.iterrows():
                    f.write(f"{row['subject_id']}\t{row.get('error','')}\n")
            print(f"\n  List saved to: {redo_path}")

    print(sep)

    # =========================================
    # Global QC and plot - ONLY in --all mode
    # =========================================
    if args.all:
        if n_ok < 1:
            print("\nX No subject was processed successfully -- no global QC.")
            sys.exit(1)
        if os.path.exists(args.ref_xlsx):
            generate_qc(csv_path, args.ref_xlsx, args.out,
                        tracer=args.tracer, voi_method=args.voi_method)
        else:
            print(f"\n  (ref_xlsx not found: {args.ref_xlsx})")
            print(f"  No global QC or plot.")
    else:
        print(f"\n  (--test mode: the global validation plot is not generated)")


if __name__ == "__main__":
    main()
