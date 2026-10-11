#!/usr/bin/env python3
"""
dicom_to_nifti.py -- DICOM -> NIfTI conversion and organisation for downloaded ADNI / LEADS-style scans, in plain Python.

It reproduces the "setup" stage that the LEADS pipeline (https://github.com/dschonhaut/leads_processing,
GPL-3.0) runs before processing, without MATLAB. The code is a new implementation of the same steps; the
dcm2niix call is identical (`dcm2niix -d 9 -o <dir> <dir>`, default output names).

Layout (the folder names `newdata` and `raw` are only suggestions):
    <base>/newdata/<ADNI|LEADS|...>/<subject>/<series>/<date>/<image id>/*.dcm   (or *.zip files)
    <base>/raw/<subject>/<series>/<date>/<image id>/*.nii (+ .json)

Steps (run one by one or all together):
    python3 dicom_to_nifti.py unzip    --newdata DIR
    python3 dicom_to_nifti.py convert  --newdata DIR [--dcm2niix PATH] [--jobs N]
    python3 dicom_to_nifti.py organize --newdata DIR --raw DIR [--overwrite] [--wipe]
    python3 dicom_to_nifti.py index    --raw DIR --out scans_index.csv
    python3 dicom_to_nifti.py all      --newdata DIR --raw DIR --out scans_index.csv

`index` writes one row per NIfTI in raw: subject, scan_type (tracer or MRI-T1), scan_date, image_id, pet_res_mm.
Scan type comes from file and folder names (table SCAN_TYPES below; change it for your data).
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
def unzip(newdata):
    zips = sorted(f for f in os.listdir(newdata) if f.lower().endswith(".zip"))
    print(f"unzip: {len(zips)} zip file(s) in {newdata}")
    for z in zips:
        p = os.path.join(newdata, z)
        try:
            with zipfile.ZipFile(p) as zf:
                zf.extractall(newdata)
            print(f"  extracted {z}")
        except zipfile.BadZipFile:
            print(f"  ERROR: {z} is not a valid zip file")


# ------------------------------------------------------------------ convert
def _has(files, exts):
    return any(f.lower().endswith(exts) for f in files)


def dirs_to_convert(newdata, dcm_ext=(".dcm",)):
    """Folders with DICOM files and no NIfTI inside them."""
    out = []
    for root, _, files in os.walk(newdata):
        if _has(files, dcm_ext) and not _has(files, (".nii", ".nii.gz")):
            out.append(root)
    return sorted(out)


def convert(newdata, dcm2niix="dcm2niix", jobs=1, dcm_ext=(".dcm",)):
    if shutil.which(dcm2niix) is None and not os.path.isfile(dcm2niix):
        sys.exit(f"ERROR: dcm2niix not found ({dcm2niix}). Install it or pass --dcm2niix PATH")
    dirs = dirs_to_convert(newdata, dcm_ext)
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
def organize(newdata, raw, overwrite=False, wipe=False):
    niis = []
    for root, _, files in os.walk(newdata):
        if _has(files, (".nii", ".nii.gz")):
            niis.append(root)
    print(f"organize: {len(niis)} folder(s) with NIfTI in {newdata}")
    moved = 0
    for src in sorted(niis):
        if not os.path.isdir(src):          # already moved with a parent folder
            continue
        rel = os.path.relpath(src, newdata).split(os.sep)
        if rel[0].upper() in TOP_LEVEL_TO_STRIP and len(rel) > 1:
            rel = rel[1:]
        dst = os.path.join(raw, *rel)
        if os.path.exists(dst):
            if not overwrite:
                print(f"  skip (exists): {dst}")
                continue
            shutil.rmtree(dst)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
        moved += 1
    print(f"organize: {moved} folder(s) moved to {raw}")
    if wipe:
        for name in os.listdir(newdata):
            p = os.path.join(newdata, name)
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
        print(f"organize: {newdata} emptied")


# ------------------------------------------------------------------ index
def scan_type_of(name_or_path):
    s = name_or_path.lower()
    vals = {v for k, v in SCAN_TYPES.items() if k in s}
    if any(k in s for k in FDG_SERIES):
        vals.add("FDG")
    return vals


def classify(nii_path, raw):
    base = os.path.basename(nii_path)
    vals = scan_type_of(base)
    if not vals:
        vals = scan_type_of(os.path.dirname(os.path.relpath(nii_path, raw)))
    if len(vals) == 1:
        return next(iter(vals))
    return MULTIPLE if vals else UNKNOWN


def scan_date_of(nii_path, raw):
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
    for part in os.path.relpath(os.path.dirname(nii_path), raw).split(os.sep):
        if test(part):
            return test(part)
    return ""


def image_id_of(nii_path, raw):
    for part in os.path.basename(nii_path).split("_") + os.path.relpath(nii_path, raw).split(os.sep):
        if re.match(r"^I\d+$", part):
            return part
    return ""


def pet_res_of(nii_path, raw):
    m = re.search(r"uniform_?(\d)mm_?res", nii_path.lower().replace(",", "_"))
    return int(m.group(1)) if m else ""


def build_index(raw, out):
    rows = []
    for root, _, files in os.walk(raw):
        for f in files:
            if f.endswith(".nii"):
                p = os.path.join(root, f)
                rel = os.path.relpath(p, raw).split(os.sep)
                rows.append({"subject": rel[0], "scan_type": classify(p, raw), "scan_date": scan_date_of(p, raw),
                             "image_id": image_id_of(p, raw), "pet_res_mm": pet_res_of(p, raw),
                             "nifti": os.path.relpath(p, raw)})
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


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=["unzip", "convert", "organize", "index", "all"])
    p.add_argument("--newdata")
    p.add_argument("--raw")
    p.add_argument("--out", default="scans_index.csv")
    p.add_argument("--dcm2niix", default="dcm2niix")
    p.add_argument("--jobs", type=int, default=1, help="folders converted in parallel (default 1)")
    p.add_argument("--dcm-ext", default=".dcm", help="DICOM extension(s), comma separated (default .dcm)")
    p.add_argument("--overwrite", action="store_true", help="replace folders that already exist in raw")
    p.add_argument("--wipe", action="store_true", help="empty newdata after organizing (off by default)")
    a = p.parse_args()
    ext = tuple(e.strip().lower() for e in a.dcm_ext.split(","))
    steps = ["unzip", "convert", "organize", "index"] if a.step == "all" else [a.step]
    for s in steps:
        if s in ("unzip", "convert", "organize") and not (a.newdata and os.path.isdir(a.newdata)):
            sys.exit("ERROR: --newdata must be an existing folder")
        if s in ("organize", "index") and not a.raw:
            sys.exit("ERROR: --raw is required")
    for s in steps:
        if s == "unzip":
            unzip(a.newdata)
        elif s == "convert":
            if convert(a.newdata, a.dcm2niix, a.jobs, ext):
                sys.exit("ERROR: some conversions failed; fix them before organizing")
        elif s == "organize":
            os.makedirs(a.raw, exist_ok=True)
            organize(a.newdata, a.raw, a.overwrite, a.wipe)
        elif s == "index":
            build_index(a.raw, a.out)


if __name__ == "__main__":
    main()
