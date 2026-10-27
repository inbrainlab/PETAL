#!/usr/bin/env python3
"""
dicom_to_nifti.py -- DICOM -> NIfTI conversion and organisation for downloaded ADNI / LEADS-style scans, in plain Python.

It reproduces the "setup" stage that the LEADS pipeline (https://github.com/dschonhaut/leads_processing,
GPL-3.0) runs before processing, without MATLAB. The code is a new implementation of the same steps; the
dcm2niix call is identical (`dcm2niix -d 9 -o <dir> <dir>`, default output names).

Layout (the folder names `indir` and `outdir` are only suggestions):
    <base>/indir/<ADNI|LEADS|...>/<subject>/<series>/<date>/<image id>/*.dcm   (or *.zip files)
    <base>/outdir/<subject>/<series>/<date>/<image id>/*.nii (+ .json)

Steps (run one by one or all together):
    python3 dicom_to_nifti.py unzip    --indir DIR
    python3 dicom_to_nifti.py convert  --indir DIR [--dcm2niix PATH] [--jobs N]
    python3 dicom_to_nifti.py organize --indir DIR --outdir DIR [--overwrite] [--wipe]
    python3 dicom_to_nifti.py index    --outdir DIR --out scans_index.csv
    python3 dicom_to_nifti.py rename   --outdir DIR [--rename [DIR]] [--overwrite]
    python3 dicom_to_nifti.py all      --indir DIR --outdir DIR --out scans_index.csv [--rename [DIR]]

`index` writes one row per NIfTI in outdir: subject, scan_type (tracer or MRI-T1), scan_date, image_id, pet_res_mm.
Scan type comes from file and folder names (table SCAN_TYPES below; change it for your data).

`rename` (run on its own, or add --rename to include it when running `all`) copies each subject's NIfTI
files from outdir/ into the folder named by --rename, using exactly the file names
run_public_pipeline.sh expects: <subject>/<subject>_T1.nii, <subject>/<subject>_FTP.nii,
<subject>/<subject>_FDG.nii, etc. -- no manual renaming needed afterward. --rename on its own (no folder
after it) uses the same mri_data folder run_public_pipeline.sh itself defaults to
(PETPIPELINE_BASE/mri_data, i.e. ~/Downloads/pet_pipeline/mri_data unless you export
PETPIPELINE_BASE), so you normally don't need to pass a folder; only add one if you want the renamed
files somewhere else (--rename /some/other/folder). If a subject has more than one file of the same scan
type, the one with the earliest scan date (the first part of the file name) is used, and the rest are
reported for manual review.

Requires dcm2niix (https://github.com/rordenlab/dcm2niix) and Python >= 3.8. No other packages.
"""
import argparse
import csv
import datetime as dt
import os
import re
import shutil
import subprocess
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor

# name found in file/folder name (lower case) -> scan type
SCAN_TYPES = {
    "fbb": "FBB", "florbetaben": "FBB", "neuraceq": "FBB",
    "amyvid": "FBP", "av-45": "FBP", "av45": "FBP", "fbp": "FBP", "florbetapir": "FBP",
    "fdg": "FDG", "fludeoxyglucose": "FDG", "fluorodeoxyglucose": "FDG",
    "flutametamol": "FLUTE", "flute": "FLUTE",
    "av-1451": "FTP", "av1451": "FTP", "flortaucipir": "FTP", "ftp": "FTP", "tauvid": "FTP",
    "mk-6240": "MK6240", "mk6240": "MK6240",
    "ir-fspgr": "MRI-T1", "ir-spgr": "MRI-T1", "mprage": "MRI-T1", "t1": "MRI-T1",
    "azd-4694": "NAV", "azd4694": "NAV", "flutafuranol": "NAV", "nav-4694": "NAV", "nav4694": "NAV",
    "pi-2620": "PI2620", "pi2620": "PI2620",
    "pib": "PIB", "pittsburgh compound b": "PIB", "pittsburgh compound-b": "PIB",
}
# ADNI "step 4" FDG images carry no tracer word; they are recognised by this series name
FDG_SERIES = ("coreg,_avg,_std_img_and_vox_siz,_uniform", "coreg__avg__std_img_and_vox_siz__uniform")
TOP_LEVEL_TO_STRIP = {"LEADS", "ADNI", "IDEAS", "SCAN", "PAD"}
UNKNOWN, MULTIPLE = "UNKNOWN", "MULTIPLE"


# ------------------------------------------------------------------ unzip
def unzip(indir):
    zips = sorted(f for f in os.listdir(indir) if f.lower().endswith(".zip"))
    print(f"unzip: {len(zips)} zip file(s) in {indir}")
    for z in zips:
        p = os.path.join(indir, z)
        try:
            with zipfile.ZipFile(p) as zf:
                zf.extractall(indir)
            print(f"  extracted {z}")
        except zipfile.BadZipFile:
            print(f"  ERROR: {z} is not a valid zip file")


# ------------------------------------------------------------------ convert
def _has(files, exts):
    return any(f.lower().endswith(exts) for f in files)


def dirs_to_convert(indir, dcm_ext=(".dcm",)):
    """Folders with DICOM files and no NIfTI inside them."""
    out = []
    for root, _, files in os.walk(indir):
        if _has(files, dcm_ext) and not _has(files, (".nii", ".nii.gz")):
            out.append(root)
    return sorted(out)


def convert(indir, dcm2niix="dcm2niix", jobs=1, dcm_ext=(".dcm",)):
    if shutil.which(dcm2niix) is None and not os.path.isfile(dcm2niix):
        sys.exit(f"ERROR: dcm2niix not found ({dcm2niix}). Install it or pass --dcm2niix PATH")
    dirs = dirs_to_convert(indir, dcm_ext)
    print(f"convert: {len(dirs)} folder(s) with DICOMs and no NIfTI")

    def run(d):
        r = subprocess.run([dcm2niix, "-d", "9", "-o", d, d], capture_output=True, text=True)
        return d, r.returncode, r.stdout[-300:] + r.stderr[-300:]

    failed = 0
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        for d, code, tail in ex.map(run, dirs):
            if code != 0:
                failed += 1
                print(f"  ERROR (exit {code}) in {d}\n{tail}")
    print(f"convert: done, {len(dirs) - failed} ok, {failed} failed")
    return failed


# ------------------------------------------------------------------ organize
def organize(indir, outdir, overwrite=False, wipe=False):
    niis = []
    for root, _, files in os.walk(indir):
        if _has(files, (".nii", ".nii.gz")):
            niis.append(root)
    print(f"organize: {len(niis)} folder(s) with NIfTI in {indir}")
    moved = 0
    for src in sorted(niis):
        if not os.path.isdir(src):          # already moved with a parent folder
            continue
        rel = os.path.relpath(src, indir).split(os.sep)
        if rel[0].upper() in TOP_LEVEL_TO_STRIP and len(rel) > 1:
            rel = rel[1:]
        dst = os.path.join(outdir, *rel)
        if os.path.exists(dst):
            if not overwrite:
                print(f"  skip (exists): {dst}")
                continue
            shutil.rmtree(dst)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
        moved += 1
    print(f"organize: {moved} folder(s) moved to {outdir}")
    if wipe:
        for name in os.listdir(indir):
            p = os.path.join(indir, name)
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
        print(f"organize: {indir} emptied")


# ------------------------------------------------------------------ index
def scan_type_of(name_or_path):
    s = name_or_path.lower()
    vals = {v for k, v in SCAN_TYPES.items() if k in s}
    if any(k in s for k in FDG_SERIES):
        vals.add("FDG")
    return vals


def classify(nii_path, outdir):
    base = os.path.basename(nii_path)
    vals = scan_type_of(base)
    if not vals:
        vals = scan_type_of(os.path.dirname(os.path.relpath(nii_path, outdir)))
    if len(vals) == 1:
        return next(iter(vals))
    return MULTIPLE if vals else UNKNOWN


def scan_date_of(nii_path, outdir):
    def test(token):
        t = token.replace("-", "").replace("_", "")
        if not re.match(r"^\d{8}", t):
            return None
        try:
            d = dt.datetime.strptime(t[:8], "%Y%m%d").date()
        except ValueError:
            return None
        return d.isoformat() if dt.date(2000, 1, 1) <= d <= dt.date.today() else None

    for part in os.path.basename(nii_path).split("_"):
        if test(part):
            return test(part)
    for part in os.path.relpath(os.path.dirname(nii_path), outdir).split(os.sep):
        if test(part):
            return test(part)
    return ""


def image_id_of(nii_path, outdir):
    for part in os.path.basename(nii_path).split("_") + os.path.relpath(nii_path, outdir).split(os.sep):
        if re.match(r"^I\d+$", part):
            return part
    return ""


def pet_res_of(nii_path, outdir):
    m = re.search(r"uniform_?(\d)mm_?res", nii_path.lower().replace(",", "_"))
    return int(m.group(1)) if m else ""


def build_index(outdir, out):
    rows = []
    for root, _, files in os.walk(outdir):
        for f in files:
            if f.endswith(".nii"):
                p = os.path.join(root, f)
                rel = os.path.relpath(p, outdir).split(os.sep)
                rows.append({"subject": rel[0], "scan_type": classify(p, outdir), "scan_date": scan_date_of(p, outdir),
                             "image_id": image_id_of(p, outdir), "pet_res_mm": pet_res_of(p, outdir),
                             "nifti": os.path.relpath(p, outdir)})
    rows.sort(key=lambda r: (r["subject"], r["scan_type"], r["scan_date"]))
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["subject", "scan_type", "scan_date", "image_id", "pet_res_mm", "nifti"])
        w.writeheader()
        w.writerows(rows)
    counts = {}
    for r in rows:
        counts[r["scan_type"]] = counts.get(r["scan_type"], 0) + 1
    print(f"index: {len(rows)} NIfTI file(s) -> {out}")
    print("  by scan type:", dict(sorted(counts.items())))
    bad = [r for r in rows if r["scan_type"] in (UNKNOWN, MULTIPLE) or not r["scan_date"]]
    if bad:
        print(f"  WARNING: {len(bad)} file(s) with unknown/multiple scan type or no date (check the index)")


# ------------------------------------------------------------------ rename for pipeline
# Scan type (classify()) -> suffix run_public_pipeline.sh expects in <SUBJECT>_<suffix>.nii.
# Every scan type not listed here keeps its own name (FTP, FDG, FBP, FBB, PIB, MK6240, NAV, PI2620, FLUTE
# already match what the pipeline's PET_GLOB_CANDIDATES look for).
PIPELINE_SUFFIX = {"MRI-T1": "T1"}


def rename_for_pipeline(outdir, mri_data, overwrite=False):
    """Copy each subject's NIfTI files from outdir/ into mri_data/<subject>/<subject>_<suffix>.nii -- the
    exact names run_public_pipeline.sh looks for, so no manual renaming is needed afterward. If a subject
    has more than one file of the same scan type, the one with the earliest scan date (the first part of
    the file name, see scan_date_of()) is used."""
    by_subject_type = {}
    for root, _, files in os.walk(outdir):
        for f in files:
            if f.endswith(".nii"):
                p = os.path.join(root, f)
                subject = os.path.relpath(p, outdir).split(os.sep)[0]
                t = classify(p, outdir)
                if t in (UNKNOWN, MULTIPLE):
                    continue
                by_subject_type.setdefault((subject, t), []).append(p)

    copied = skipped = 0
    for (subject, t), paths in sorted(by_subject_type.items()):
        # earliest scan_date first; files with no date sort last, path as tie-break
        paths = sorted(paths, key=lambda p: (scan_date_of(p, outdir) or "9999-99-99", p))
        if len(paths) > 1:
            print(f"  WARNING: {subject} has {len(paths)} {t} file(s), using the earliest-dated: {paths[0]}"
                  f" -- check the others manually: {paths[1:]}")
        src = paths[0]
        suffix = PIPELINE_SUFFIX.get(t, t)
        dst_dir = os.path.join(mri_data, subject)
        dst = os.path.join(dst_dir, f"{subject}_{suffix}.nii")
        if os.path.exists(dst) and not overwrite:
            print(f"  skip (exists): {dst}")
            skipped += 1
            continue
        os.makedirs(dst_dir, exist_ok=True)
        shutil.copy2(src, dst)
        src_json = src[:-len(".nii")] + ".json"
        if os.path.isfile(src_json):
            shutil.copy2(src_json, dst[:-len(".nii")] + ".json")
        copied += 1
    print(f"rename: {copied} file(s) copied into {mri_data} ({skipped} already existed, skipped)")
    unknown = sum(1 for root, _, files in os.walk(outdir) for f in files
                  if f.endswith(".nii") and classify(os.path.join(root, f), outdir) in (UNKNOWN, MULTIPLE))
    if unknown:
        print(f"  NOTE: {unknown} file(s) in {outdir} have unknown/multiple scan type and were not copied -- "
              f"see the scans_index.csv UNKNOWN/MULTIPLE rows and rename those manually if needed")


def main():
    # same default as run_public_pipeline.sh/check_install.sh: PETPIPELINE_BASE/mri_data
    petpipeline_base = os.environ.get("PETPIPELINE_BASE") or os.path.expanduser("~/Downloads/pet_pipeline")
    default_rename = os.path.join(petpipeline_base, "mri_data")

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=["unzip", "convert", "organize", "index", "rename", "all"])
    p.add_argument("--indir")
    p.add_argument("--outdir")
    p.add_argument("--out", default="scans_index.csv")
    p.add_argument("--rename", nargs="?", const=default_rename, default=None, metavar="DIR",
                   help="copy converted NIfTI files into DIR using the exact names "
                        "run_public_pipeline.sh expects (<SUBJECT>_T1.nii, <SUBJECT>_FTP.nii, "
                        "<SUBJECT>_FDG.nii, ...). Used alone (no DIR) it defaults to the same "
                        "mri_data folder run_public_pipeline.sh itself uses "
                        "(PETPIPELINE_BASE/mri_data); pass a DIR only if you want the renamed "
                        "files somewhere else. When step is 'all', including --rename at all "
                        "(with or without DIR) also runs the rename step afterward")
    p.add_argument("--dcm2niix", default="dcm2niix")
    p.add_argument("--jobs", type=int, default=1, help="folders converted in parallel (default 1)")
    p.add_argument("--dcm-ext", default=".dcm", help="DICOM extension(s), comma separated (default .dcm)")
    p.add_argument("--overwrite", action="store_true", help="replace folders that already exist in outdir, or"
                                                              " files that already exist in --rename")
    p.add_argument("--wipe", action="store_true", help="empty indir after organizing (off by default)")
    a = p.parse_args()
    ext = tuple(e.strip().lower() for e in a.dcm_ext.split(","))
    steps = ["unzip", "convert", "organize", "index"] + (["rename"] if a.rename is not None else []) if a.step == "all" else [a.step]
    for s in steps:
        if s in ("unzip", "convert", "organize") and not (a.indir and os.path.isdir(a.indir)):
            sys.exit("ERROR: --indir must be an existing folder")
        if s in ("organize", "index") and not a.outdir:
            sys.exit("ERROR: --outdir is required")
        if s == "rename" and not a.outdir:
            sys.exit("ERROR: --outdir is required for the 'rename' step")
    for s in steps:
        if s == "unzip":
            unzip(a.indir)
        elif s == "convert":
            if convert(a.indir, a.dcm2niix, a.jobs, ext):
                sys.exit("ERROR: some conversions failed; fix them before organizing")
        elif s == "organize":
            os.makedirs(a.outdir, exist_ok=True)
            organize(a.indir, a.outdir, a.overwrite, a.wipe)
        elif s == "index":
            build_index(a.outdir, a.out)
        elif s == "rename":
            rename_dir = a.rename if a.rename is not None else default_rename
            os.makedirs(rename_dir, exist_ok=True)
            rename_for_pipeline(a.outdir, rename_dir, a.overwrite)


if __name__ == "__main__":
    main()
