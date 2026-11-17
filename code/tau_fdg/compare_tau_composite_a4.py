#!/usr/bin/env python3
"""
compare_tau_composite_a4.py -- compares COMPOSITE Tau ROIs (here: meta_temporal
and its six component regions) between our own pipeline and A4, over the full
cohort.

Neither side has a ready-made composite column: the A4 TAUSUVR file only has
individual per-hemisphere Mean_*/Volume_mm3_* columns and already-bilateral
bi_* columns, and our own segstats output is per-region too. So BOTH
composites are computed with the exact same definition (rois_ftp.csv,
from LEADS), which avoids any VOI-definition mismatch between the two sides.

  - A4 side: composite_from_bi_row() -- combines A4's own bi_<name> SUVR
    values (already cerebellum-normalized) weighted by each region's total
    volume (Volume_mm3_ctx_lh_<name> + Volume_mm3_ctx_rh_<name>, or the
    Left_/Right_ subcortical equivalents). No raw Mean_* values are touched,
    so A4's own normalization is preserved exactly.

  - Our side: composite_from_segstats() -- combines our own segstats output
    (per-hemisphere Mean + NVoxels) using the FreeSurfer LUT to map each
    composite's numeric label ids to StructNames, then divides by our own
    whole-cerebellum mean (bilateral, volume-weighted, computed from the same
    segstats file -- NOT taken from A4).

Usage:
    python3 compare_tau_composite_a4.py \
        --fastsurfer-base /path/to/fastsurfer/output \
        --tausuvr /path/to/A4/TAUSUVR.csv \
        --fsroi-list /path/to/leads_processing/config/rois_ftp.csv \
        --lut $FREESURFER_HOME/FreeSurferColorLUT.txt \
        --csv_out cohort_tau_composite.csv
"""

import argparse
import csv
import math
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "replication_tool"))
from composite_regions import read_composites, load_lut, composite_from_segstats, composite_from_bi_row

# The 6 regions that make up meta_temporal (Jack et al. 2017), each with its
# 2 labels (left, right). They are reported separately in addition to the
# composite, so the parts and the whole can be seen together.
META_TEMPORAL_REGIONS = {
    "Amygdala":         [18, 54],
    "entorhinal":       [1006, 2006],
    "fusiform":         [1007, 2007],
    "inferiortemporal": [1009, 2009],
    "middletemporal":   [1015, 2015],
    "parahippocampal":  [1016, 2016],
}


def load_segstats(path):
    """Standard mri_segstats parser (Index SegId NVoxels Volume_mm3
    StructName Mean StdDev Min Max Range)."""
    d = {}
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            parts = line.split()
            if len(parts) < 10:
                continue
            try:
                nvox = int(parts[2])
                vol = float(parts[3])
                struct = parts[4]
                mean = float(parts[5])
            except (ValueError, IndexError):
                continue
            d[struct] = {"mean": mean, "nvoxels": nvox, "volume": vol}
    return d


def get_our_cerebellum_mean(seg_dict):
    """Whole cerebellum (cortex), bilateral, volume-weighted, from our own
    segstats output -- the reference region for Tau SUVR."""
    lh = seg_dict.get("ctx-lh-Cerebellum-Cortex") or seg_dict.get("Left-Cerebellum-Cortex")
    rh = seg_dict.get("ctx-rh-Cerebellum-Cortex") or seg_dict.get("Right-Cerebellum-Cortex")
    if lh is None:
        lh = seg_dict.get("Left-Cerebellum-Cortex")
    if rh is None:
        rh = seg_dict.get("Right-Cerebellum-Cortex")
    if lh is None or rh is None:
        return None
    total_v = lh["nvoxels"] + rh["nvoxels"]
    if total_v == 0:
        return None
    return (lh["mean"] * lh["nvoxels"] + rh["mean"] * rh["nvoxels"]) / total_v


def read_tausuvr(path):
    """Returns {ID: row_dict} from A4's TAUSUVR CSV."""
    out = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            out[row["ID"]] = row
    return out


# ─────────────────────────────── metrics ───────────────────────────────────

def mape_stats(pairs):
    """pairs = [(reference, ours), ...]. Returns (mean MAPE %, SD, n)."""
    if not pairs:
        return float("nan"), float("nan"), 0
    arr = np.array(pairs, dtype=float)
    ref, ours = arr[:, 0], arr[:, 1]
    errs = np.abs(ours - ref) / (np.abs(ref) + 1e-9) * 100
    mean = float(np.mean(errs))
    sd = float(np.std(errs, ddof=1)) if len(errs) > 1 else float("nan")
    return mean, sd, len(pairs)


def icc_2_1(pairs):
    """ICC(2,1): two-way random effects, absolute agreement, single rater
    (Shrout & Fleiss, 1979). pairs = [(method_1, method_2), ...]."""
    if len(pairs) < 2:
        return float("nan")
    arr = np.array(pairs, dtype=float)
    n, k = arr.shape
    grand_mean = arr.mean()
    subject_means = arr.mean(axis=1)
    method_means = arr.mean(axis=0)
    SST = np.sum((arr - grand_mean) ** 2)
    SSR = k * np.sum((subject_means - grand_mean) ** 2)
    SSC = n * np.sum((method_means - grand_mean) ** 2)
    SSE = SST - SSR - SSC
    df_r, df_c, df_e = n - 1, k - 1, (n - 1) * (k - 1)
    if df_r <= 0 or df_e <= 0:
        return float("nan")
    MSR, MSC, MSE = SSR / df_r, SSC / df_c, SSE / df_e
    denom = MSR + (k - 1) * MSE + k * (MSC - MSE) / n
    if denom == 0:
        return float("nan")
    return float((MSR - MSE) / denom)


def main():
    # Same PETPIPELINE_BASE convention as run_public_pipeline.sh/evaluate_subject.py.
    _repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    petpipeline_base = os.environ.get("PETPIPELINE_BASE") or os.path.join(_repo_root, "pet_pipeline")
    default_fastsurfer_base = os.path.join(petpipeline_base, "output")
    default_fsroi_list = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data", "rois_ftp.csv")
    default_lut = os.path.expanduser("~/freesurfer/FreeSurferColorLUT.txt")

    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fastsurfer-base", default=default_fastsurfer_base,
                   help=f"folder with <subject>/<seg-filename> (our Tau segstats); default: {default_fastsurfer_base}")
    p.add_argument("--tausuvr", required=True, help="A4 TAUSUVR_*.csv")
    p.add_argument("--fsroi-list", default=default_fsroi_list,
                   help=f"rois_ftp.csv (default: {default_fsroi_list}; not shipped, place it there)")
    p.add_argument("--lut", default=default_lut,
                   help=f"FreeSurferColorLUT.txt (default: {default_lut})")
    p.add_argument("--seg-filename", default="output.csv",
                   help="filename of our segstats output inside each subject folder (default: output.csv)")
    p.add_argument("--csv_out", default="cohort_tau_composite.csv")
    p.add_argument("--csv_raw", default=None,
                   help="if given, dump the actual composite SUVR (not the error) per subject: "
                        "subject,composite_region,suvr_a4,suvr_ours")
    args = p.parse_args()

    all_composites = read_composites(args.fsroi_list)
    # Only meta_temporal has direct support in the literature (Jack et al.
    # 2017; same 12 labels as in LEADS: 18,54,1006,1007,1009,1015,1016,2006,
    # 2007,2009,2015,2016). The other composites defined in the LEADS file
    # (mtl_no_hippocampus, basolateral_temporal, temporoparietal,
    # ctx_desikan) are LEADS-specific variants and are not analysed here.
    if "meta_temporal" not in all_composites:
        raise SystemExit(f"'meta_temporal' is not in {args.fsroi_list} -- check the file.")
    composites = {"meta_temporal": all_composites["meta_temporal"]}
    lut = load_lut(args.lut)
    print(f"{len(composites)} composite region resolved from {args.fsroi_list}: {sorted(composites)}")
    print(f"   (of the {len(all_composites)} composites in the file, only "
          f"meta_temporal is used -- direct support in Jack et al. 2017)")

    a4_rows = read_tausuvr(args.tausuvr)
    print(f"{len(a4_rows)} subjects in {args.tausuvr}")

    subjects = sorted(
        s for s in os.listdir(args.fastsurfer_base)
        if os.path.isfile(os.path.join(args.fastsurfer_base, s, args.seg_filename))
    )
    print(f"{len(subjects)} subjects with {args.seg_filename} in {args.fastsurfer_base}\n")

    all_pairs = []  # (subject, composite_name, a4_val, our_val)
    subjects_skipped = []
    missing_labels_by_composite = {}

    for subj in subjects:
        if subj not in a4_rows:
            subjects_skipped.append((subj, "not in A4 TAUSUVR"))
            continue
        seg_path = os.path.join(args.fastsurfer_base, subj, args.seg_filename)
        seg_dict = load_segstats(seg_path)
        cereb_mean = get_our_cerebellum_mean(seg_dict)
        if cereb_mean is None or cereb_mean == 0:
            subjects_skipped.append((subj, "no whole-cerebellum reference found in our segstats"))
            continue

        a4_row = a4_rows[subj]
        for comp_name, label_ids in composites.items():
            a4_val, a4_vol, a4_missing = composite_from_bi_row(a4_row, label_ids, lut)
            our_mean_raw, our_nvox, our_missing = composite_from_segstats(seg_dict, label_ids, lut)

            if a4_missing:
                missing_labels_by_composite.setdefault(("A4", comp_name), set()).update(a4_missing)
                continue
            if our_missing:
                missing_labels_by_composite.setdefault(("ours", comp_name), set()).update(our_missing)
                continue
            if a4_vol == 0 or our_nvox == 0 or math.isnan(a4_val) or math.isnan(our_mean_raw):
                continue

            our_val = our_mean_raw / cereb_mean
            all_pairs.append((subj, comp_name, a4_val, our_val))

        # -- the 6 regions that make up meta_temporal, individually --
        for region_name, label_ids in META_TEMPORAL_REGIONS.items():
            a4_val, a4_vol, a4_missing = composite_from_bi_row(a4_row, label_ids, lut)
            our_mean_raw, our_nvox, our_missing = composite_from_segstats(seg_dict, label_ids, lut)

            if a4_missing:
                missing_labels_by_composite.setdefault(("A4", f"[region] {region_name}"), set()).update(a4_missing)
                continue
            if our_missing:
                missing_labels_by_composite.setdefault(("ours", f"[region] {region_name}"), set()).update(our_missing)
                continue
            if a4_vol == 0 or our_nvox == 0 or math.isnan(a4_val) or math.isnan(our_mean_raw):
                continue

            our_val = our_mean_raw / cereb_mean
            all_pairs.append((subj, f"[region] {region_name}", a4_val, our_val))

    print(f"{len(subjects) - len(subjects_skipped)} subjects usable, "
          f"{len(subjects_skipped)} skipped")
    if subjects_skipped:
        for s, why in subjects_skipped[:10]:
            print(f"   {s}: {why}")
        if len(subjects_skipped) > 10:
            print(f"   ... and {len(subjects_skipped) - 10} more")
    if missing_labels_by_composite:
        print("\nWARNING: composites with missing sub-region labels for some subjects "
              "(that subject was excluded for that composite, never partially averaged):")
        for (side, comp_name), labels in missing_labels_by_composite.items():
            print(f"   [{side}] {comp_name}: labels {sorted(labels)}")

    if not all_pairs:
        raise SystemExit("No valid pairs found -- check paths/column names above.")

    print(f"\n{len(all_pairs)} (subject, composite) pairs total\n")

    by_composite = defaultdict(list)
    for _, comp_name, a4_val, our_val in all_pairs:
        by_composite[comp_name].append((a4_val, our_val))

    rows_out = []
    for comp_name, pairs in by_composite.items():
        mape_m, mape_sd, n = mape_stats(pairs)
        icc = icc_2_1(pairs)
        rows_out.append({"composite_region": comp_name, "n": n,
                          "mape_mean": mape_m, "mape_sd": mape_sd, "icc": icc})
    rows_out.sort(key=lambda r: -(r["mape_mean"] if r["mape_mean"] == r["mape_mean"] else -1))

    with open(args.csv_out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["composite_region", "n", "mape_mean", "mape_sd", "icc"])
        w.writeheader()
        w.writerows(rows_out)
    print(f"CSV: {args.csv_out}")

    if args.csv_raw:
        with open(args.csv_raw, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["subject", "composite_region", "suvr_a4", "suvr_ours"])
            w.writerows(all_pairs)
        print(f"Per-subject composite SUVR (values, not the error): {args.csv_raw}")

    # One block per region: actual value (mean ± SD) AND error (MAPE/ICC)
    print("\nComposite SUVR per region -- actual value and error, together:")
    for row in rows_out:
        comp_name = row["composite_region"]
        arr = np.array(by_composite[comp_name], dtype=float)
        a4_vals, our_vals = arr[:, 0], arr[:, 1]
        print(f"    {comp_name} (n={row['n']}):")
        print(f"        A4:    {np.mean(a4_vals):.4f} ± {np.std(a4_vals, ddof=1):.4f}  (SUVR, mean ± SD)")
        print(f"        Ours:  {np.mean(our_vals):.4f} ± {np.std(our_vals, ddof=1):.4f}  (SUVR, mean ± SD)")
        print(f"        Error: MAPE {row['mape_mean']:.2f}% ± {row['mape_sd']:.2f}% (SD)  ·  ICC={row['icc']:.3f}")


if __name__ == "__main__":
    main()
