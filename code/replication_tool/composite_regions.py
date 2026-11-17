#!/usr/bin/env python3
"""
composite_regions.py -- shared helpers to compute composite ROIs
(meta_temporal, mtl_no_hippocampus, basolateral_temporal, temporoparietal,
ctx_desikan) from a LEADS rois_*.csv definition file. Used by both
the FDG-vs-LEADS and Tau-vs-A4 comparison scripts and by the subject
evaluation tool, so the composite definitions stay in exactly one place.

A composite ROI is defined by a list of FreeSurfer numeric label IDs
(both hemispheres, e.g. meta_temporal = Amygdala + entorhinal + fusiform +
inferiortemporal + middletemporal + parahippocampal, L+R each). The
composite value is the VOLUME-WEIGHTED mean across all those labels --
never a plain average -- so a small structure never counts as much as a
large one.
"""

import csv
from collections import defaultdict


def read_composites(fsroi_list_path):
    """Reads a rois_*.csv (roi_name,roi_labels). Returns
    {composite_name: [label_id, ...]} -- ONLY for rows with more than
    one ';'-separated label id (the true composites; single-region rows
    like 'ctx_lh_bankssts,1001' are skipped, those are handled by the
    per-region bilateral logic elsewhere)."""
    composites = {}
    with open(fsroi_list_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        reader.fieldnames = [(fn or "").strip() for fn in reader.fieldnames]
        for row in reader:
            name = row["roi_name"].strip()
            ids = [x.strip() for x in row["roi_labels"].split(";") if x.strip()]
            if len(ids) > 1:
                composites[name] = [int(x) for x in ids]
    return composites


def load_lut(lut_path):
    """Reads a FreeSurferColorLUT.txt. Returns {label_id: StructName}."""
    lut = {}
    with open(lut_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            try:
                label_id = int(parts[0])
            except ValueError:
                continue
            lut[label_id] = parts[1]
    return lut


def composite_from_segstats(seg_dict, label_ids, lut, name_resolver=None):
    """seg_dict = {StructName: {"mean":, "nvoxels":, ...}} (load_segstats()
    output). label_ids = list of numeric FreeSurfer label ids for this
    composite. lut = {label_id: StructName} (FreeSurferColorLUT.txt).
    name_resolver(struct_name) -> optional function to adapt LUT naming
    convention (dashes) to what seg_dict actually uses, when they differ
    (e.g. LUT says 'ctx-lh-entorhinal', seg_dict key style may match or
    need adjusting) -- if None, the LUT name is used as-is.

    Returns (composite_mean_raw, total_nvoxels, missing_labels) --
    composite_mean_raw is NOT yet divided by any reference region; the
    caller does that division (so this function stays reference-agnostic
    and works the same for Tau/cerebellum or FDG/pons)."""
    total_weighted = 0.0
    total_nvox = 0
    missing = []
    for label_id in label_ids:
        struct_name = lut.get(label_id)
        if struct_name is None:
            missing.append(label_id)
            continue
        if name_resolver:
            struct_name = name_resolver(struct_name, seg_dict) or struct_name
        entry = seg_dict.get(struct_name)
        if entry is None:
            missing.append(label_id)
            continue
        total_weighted += entry["mean"] * entry["nvoxels"]
        total_nvox += entry["nvoxels"]
    if total_nvox == 0:
        return float("nan"), 0, missing
    return total_weighted / total_nvox, total_nvox, missing


# -- mapping label_id -> (bilateral bi_* base name) for the A4 TAUSUVR path --
# The TAUSUVR bi_* columns are keyed by base name (no ctx_lh_/ctx_rh_/Left_/
# Right_ prefix, e.g. bi_entorhinal, bi_Amygdala). To combine a composite
# from bi_* + Volume_mm3_* we need, for each label id, which bi_ base name
# and which per-hemisphere Volume_mm3_ column it maps to.

def _strip_hemi_prefix(struct_name):
    """'ctx-lh-entorhinal' -> ('entorhinal','lh'); 'Left-Amygdala' ->
    ('Amygdala','lh'); 'ctx-rh-X' -> ('X','rh'); 'Right-X' -> ('X','rh').
    Tolerates both dash (standard FreeSurferColorLUT.txt convention) and
    underscore (LEADS' rois_*.csv convention) separators."""
    if struct_name is None:
        return None, None
    s = struct_name
    for prefix, hemi in (("ctx-lh-", "lh"), ("ctx_lh_", "lh"),
                         ("ctx-rh-", "rh"), ("ctx_rh_", "rh"),
                         ("Left-", "lh"), ("Left_", "lh"),
                         ("Right-", "rh"), ("Right_", "rh")):
        if s.startswith(prefix):
            return s[len(prefix):], hemi
    return None, None


def composite_from_bi_row(row, label_ids, lut):
    """row = a single dict from TAUSUVR CSV (DictReader row), already
    containing 'bi_<name>' (SUVR, bilateral) and 'Volume_mm3_ctx_lh_<name>'
    / 'Volume_mm3_ctx_rh_<name>' / 'Volume_mm3_Left_<name>' /
    'Volume_mm3_Right_<name>' columns. label_ids = the composite's list
    of FreeSurfer numeric ids (both hemispheres).

    Because bi_<name> is ALREADY the volume-weighted L+R combination
    (bi_X = (mean_lh*vol_lh + mean_rh*vol_rh)/(vol_lh+vol_rh)), summing
    bi_X weighted by (vol_lh_X+vol_rh_X) across all named regions in the
    composite gives EXACTLY the same result as combining all individual
    per-hemisphere labels directly -- no need to touch the raw Mean_*
    columns or re-derive the reference normalization.

    Returns (composite_suvr, total_volume, missing_names) -- missing_names
    lists any bi_/Volume_mm3_ columns that were expected but absent/NA."""
    # group label ids by base name (deduplicate lh/rh into one base name)
    base_names = set()
    for label_id in label_ids:
        struct_name = lut.get(label_id)
        if struct_name is None:
            continue
        base, hemi = _strip_hemi_prefix(struct_name)
        if base:
            base_names.add(base)

    total_weighted = 0.0
    total_vol = 0.0
    missing = []
    for base in sorted(base_names):
        bi_col = f"bi_{base}"
        vol_lh_col_ctx = f"Volume_mm3_ctx_lh_{base}"
        vol_rh_col_ctx = f"Volume_mm3_ctx_rh_{base}"
        vol_lh_col_sub = f"Volume_mm3_Left_{base}"
        vol_rh_col_sub = f"Volume_mm3_Right_{base}"

        bi_val = _num(row.get(bi_col))
        vol_lh = _num(row.get(vol_lh_col_ctx)) or _num(row.get(vol_lh_col_sub))
        vol_rh = _num(row.get(vol_rh_col_ctx)) or _num(row.get(vol_rh_col_sub))

        if bi_val is None or vol_lh is None or vol_rh is None:
            missing.append(base)
            continue
        vol_total = vol_lh + vol_rh
        total_weighted += bi_val * vol_total
        total_vol += vol_total

    if total_vol == 0:
        return float("nan"), 0.0, missing
    return total_weighted / total_vol, total_vol, missing


def _num(raw):
    if raw in ("", None, "NA"):
        return None
    try:
        return float(raw)
    except ValueError:
        return None
