#!/usr/bin/env python3
"""
compare_fdg_leads.py -- compares FDG SUVR (reference region: pons) between
our own pipeline and LEADS (https://github.com/dschonhaut/leads_processing),
over all subjects available on both sides. Same statistical criteria as
nrmse_cohort.py (Tau/A4): MAPE as the main metric, NRMSE (per-region range,
not pooled) as the secondary one, and ICC(2,1) per region.

Key differences with respect to the Tau/A4 comparison:
  - Reference region = PONS (taken from output_brainstem_fdg.csv), not
    cerebellum.
  - LEADS delivers SUVR ALREADY NORMALIZED (mean from
    *_suvr-pons_roi-extractions.csv) -- no further division is needed.
  - OUR output_fdg.csv holds RAW (non-normalized) intensity, so it is
    divided by the Mean of the 'Pons' row of output_brainstem_fdg.csv.
  - There is no PVC step for FDG.
  - Bilateral regions are built FROM the LEADS fsroi_list_FDG.csv (source of
    truth), not hardcoded, to avoid assuming region names that may not match
    the FreeSurfer version in use.

Expected folder structure:
  Ours:   <output_dir>/<subject>/output_fdg.csv
          <output_dir>/<subject>/output_brainstem_fdg.csv
  LEADS:  <leads_base>/<subject>/FDG_*/<algo>_suvr-pons_roi-extractions.csv

Usage:
    python3 compare_fdg_leads.py \
        --output_dir /path/to/fastsurfer/output \
        --leads-base      /path/to/leads/data/processed \
        --fsroi-list      /path/to/leads_processing/config/fsroi_list_FDG.csv \
        --csv_regions cohort_fdg_per_region.csv \
        --csv_raw     cohort_fdg_pairs.csv
"""

import argparse
import csv
import glob
import math
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "replication_tool"))
from composite_regions import read_composites, load_lut, composite_from_segstats, composite_from_bi_row

# The 6 regions that make up meta_temporal (Jack et al. 2017), with their
# L/R labels. They are computed with the SAME direct method as the composite
# (LUT + segstats on our side, direct lookup by name on the LEADS side), not
# with the bilateral name matching, which fails for entorhinal and
# parahippocampal specifically (see the warning about regions that could
# never be resolved).
META_TEMPORAL_REGIONS = {
    "Amygdala":         [18, 54],
    "entorhinal":       [1006, 2006],
    "fusiform":         [1007, 2007],
    "inferiortemporal": [1009, 2009],
    "middletemporal":   [1015, 2015],
    "parahippocampal":  [1016, 2016],
}


# ─────────────────────────────── file parsing ──────────────────────────────

def load_segstats(path):
    """Parses an mri_segstats file (standard format: Index SegId NVoxels
    Volume_mm3 StructName Mean StdDev Min Max Range). Returns
    {StructName: {"mean":.., "nvoxels":.., "volume":..}}."""
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


def get_pons_mean(brainstem_dict):
    row = brainstem_dict.get("Pons")
    return row["mean"] if row else None


def parse_fsroi_list(path):
    """Reads fsroi_list_FDG.csv (roi_name,roi_labels) and builds the set of
    bilateral regions FROM the names used by LEADS -- only rows with a
    single name 'ctx_lh_X'/'Left_X' that has its counterpart
    'ctx_rh_X'/'Right_X' (composite regions such as meta_temporal, which
    have many labels and are not a simple L/R pair, are skipped).
    Returns {bi_name: (leads_lh_name, leads_rh_name)}.

    utf-8-sig tolerates a BOM at the start of the file (Excel/Windows often
    add one), which would otherwise make the first column read as
    '\\ufeffroi_name' instead of 'roi_name' and break the DictReader."""
    names = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        # defensive cleanup: stray whitespace in column names
        reader.fieldnames = [(fn or "").strip() for fn in reader.fieldnames]
        if "roi_name" not in reader.fieldnames:
            raise SystemExit(
                f"ERROR: '{path}' has no 'roi_name' column. "
                f"Columns found: {reader.fieldnames}"
            )
        for row in reader:
            names.append(row["roi_name"].strip())

    bilateral = {}
    seen = set()
    for name in names:
        if name in seen:
            continue
        if name.startswith("ctx_lh_"):
            base = name[len("ctx_lh_"):]
            rh = f"ctx_rh_{base}"
            if rh in names:
                bilateral[base] = (name, rh)
                seen.add(name)
                seen.add(rh)
        elif name.startswith("Left_"):
            base = name[len("Left_"):]
            rh = f"Right_{base}"
            if rh in names:
                bilateral[base] = (name, rh)
                seen.add(name)
                seen.add(rh)
    return bilateral


def our_candidate_names(leads_name):
    """Given a LEADS name (ctx_lh_X / Left_X), generates the candidate names
    that may appear in OUR output_fdg.csv (which uses the standard
    FreeSurferColorLUT convention, with dashes, and sometimes different
    suffixes such as 'Thalamus' vs 'Thalamus-Proper' depending on the
    FreeSurfer version)."""
    candidates = [leads_name.replace("_", "-")]
    if leads_name.endswith("_Proper"):
        candidates.append(leads_name[: -len("_Proper")].replace("_", "-"))
    return candidates


def resolve_in_ours(leads_name, seg_dict):
    for cand in our_candidate_names(leads_name):
        if cand in seg_dict:
            return cand
    return None


def resolve_for_composite(struct_name_lut, seg_dict):
    """name_resolver callback for composite_from_segstats(): the LUT gives
    names in the underscore convention (ctx_lh_X, Left_X); our own
    output_fdg.csv uses dashes (ctx-lh-X, Left-X). Reuses the same
    candidate logic as the bilateral-region resolver above."""
    return resolve_in_ours(struct_name_lut, seg_dict)


def leads_bilateral_suvr(leads_pairs, bilateral):
    """leads_pairs = {roi: (mean, voxel_count)} from a
    *_suvr-pons_roi-extractions.csv (already normalized by LEADS). Returns
    {bi_name: bilateral_suvr}, combining L+R weighted by voxel_count."""
    out = {}
    for bi_name, (lh, rh) in bilateral.items():
        if lh in leads_pairs and rh in leads_pairs:
            m_lh, v_lh = leads_pairs[lh]
            m_rh, v_rh = leads_pairs[rh]
            total_v = v_lh + v_rh
            if total_v > 0:
                out[bi_name] = (m_lh * v_lh + m_rh * v_rh) / total_v
    return out


def our_bilateral_suvr(seg_dict, pons_mean, bilateral):
    """seg_dict = load_segstats(output_fdg.csv). Returns
    {bi_name: bilateral_suvr}, combining L+R weighted by NVoxels and
    dividing by pons_mean (our output is raw intensity)."""
    if not pons_mean or pons_mean <= 0:
        return {}
    out = {}
    for bi_name, (leads_lh, leads_rh) in bilateral.items():
        our_lh = resolve_in_ours(leads_lh, seg_dict)
        our_rh = resolve_in_ours(leads_rh, seg_dict)
        if our_lh and our_rh:
            d_lh, d_rh = seg_dict[our_lh], seg_dict[our_rh]
            total_v = d_lh["nvoxels"] + d_rh["nvoxels"]
            if total_v > 0:
                mean_raw = (d_lh["mean"] * d_lh["nvoxels"] +
                            d_rh["mean"] * d_rh["nvoxels"]) / total_v
                out[bi_name] = mean_raw / pons_mean
    return out


def parse_leads_roi_csv(path):
    """Reads r*_suvr-pons_roi-extractions.csv (columns: image_file,roi_file,
    roi,mean,voxel_count). Returns {roi: (mean, voxel_count)}."""
    out = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        reader.fieldnames = [(fn or "").strip() for fn in reader.fieldnames]
        for row in reader:
            try:
                out[row["roi"]] = (float(row["mean"]), int(float(row["voxel_count"])))
            except (ValueError, KeyError):
                continue
    return out


# ───────────────────── metrics (same criteria as nrmse_cohort.py) ──────────

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


def compute_range_per_region(pairs_with_region):
    values = defaultdict(list)
    for region, ref, _ in pairs_with_region:
        if np.isfinite(ref):
            values[region].append(ref)
    return {r: (max(v) - min(v)) for r, v in values.items() if v}


def nrmse_per_region(pairs_with_region, rng_dict):
    normalized = []
    for region, ref, ours in pairs_with_region:
        rng = rng_dict.get(region)
        if rng and rng > 0 and np.isfinite(ref) and np.isfinite(ours):
            normalized.append(((ours - ref) / rng) ** 2)
    if not normalized:
        return float("nan"), 0
    return float(np.sqrt(np.mean(normalized)) * 100), len(normalized)


def nrmse_stats(pairs, rng):
    if not pairs or rng is None or rng <= 0:
        return float("nan"), float("nan"), 0
    arr = np.array(pairs, dtype=float)
    ref, ours = arr[:, 0], arr[:, 1]
    errs = (ours - ref) / rng * 100
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


# ─────────────────────────────────── main ───────────────────────────────────

def main():
    # Same PETPIPELINE_BASE convention as run_public_pipeline.sh/evaluate_subject.py: defaults to
    # this repo's own pet_pipeline/ folder unless overridden. leads-base has no fixed convention of
    # its own (it's reference data you obtain from LEADS yourself), so it gets a staging folder under
    # the same base.
    _repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    petpipeline_base = os.environ.get("PETPIPELINE_BASE") or os.path.join(_repo_root, "pet_pipeline")
    default_output_dir = os.path.join(petpipeline_base, "output")
    default_leads_base = os.path.join(petpipeline_base, "leads_data")
    default_fsroi_list = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data", "fsroi_list_FDG.csv")

    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--output_dir", default=default_output_dir,
                   help="folder with <subject>/output_fdg.csv and output_brainstem_fdg.csv (our FDG segstats); "
                        f"default: {default_output_dir}")
    p.add_argument("--leads-base", default=default_leads_base,
                   help="folder with the LEADS outputs: <subject>/FDG_*/*_suvr-pons_roi-extractions.csv; "
                        f"default: {default_leads_base}")
    p.add_argument("--fsroi-list", default=default_fsroi_list,
                   help=f"fsroi_list_FDG.csv (default: {default_fsroi_list})")
    p.add_argument("--csv_regions", default="cohort_fdg_per_region.csv")
    p.add_argument("--csv_raw", default=None,
                   help="if given, dump all raw pairs (subject,region,leads_ref,ours)")
    p.add_argument("--exclude-subjects", default=None,
                   help="text file with one subject ID per line -- those subjects are "
                        "excluded from the analysis (useful to separate subgroups)")
    p.add_argument("--lut", default=None,
                   help="path to FreeSurferColorLUT.txt -- if given, in addition to the "
                        "bilateral regions the COMPOSITE regions defined in --fsroi-list "
                        "are computed (only meta_temporal is analysed): ours is built by "
                        "volume-weighting the individual labels of output_fdg.csv; the "
                        "LEADS value comes directly from its roi-extractions.csv and does "
                        "not need to be recomputed.")
    p.add_argument("--csv_composite", default="cohort_fdg_composite.csv",
                   help="output CSV for the composite regions (only if --lut is given)")
    p.add_argument("--csv_raw_composite", default=None,
                   help="if given (together with --lut), dump the actual composite SUVR "
                        "(not the error) per subject: subject,composite_region,leads_ref,ours")
    args = p.parse_args()

    bilateral = parse_fsroi_list(args.fsroi_list)
    print(f"{len(bilateral)} bilateral regions resolved from {args.fsroi_list}")

    all_composites = read_composites(args.fsroi_list) if args.lut else {}
    # Only meta_temporal has direct support in the literature (Jack et al.
    # 2017; same criterion as compare_tau_composite_a4.py). The other
    # composites in the file are not analysed.
    composites = {"meta_temporal": all_composites["meta_temporal"]} if "meta_temporal" in all_composites else {}
    lut = load_lut(args.lut) if args.lut else {}
    if args.lut:
        print(f"{len(composites)} composite regions resolved from {args.fsroi_list}: "
              f"{sorted(composites)}")
        print(f"   (of the {len(all_composites)} composites in the file, only "
              f"meta_temporal is used -- direct support in Jack et al. 2017)")

    excluded_subjects = set()
    if args.exclude_subjects:
        with open(args.exclude_subjects) as f:
            excluded_subjects = {line.strip() for line in f if line.strip()}
        print(f"{len(excluded_subjects)} subjects to exclude, read from {args.exclude_subjects}")

    subjects = sorted(
        s for s in os.listdir(args.output_dir)
        if os.path.isfile(os.path.join(args.output_dir, s, "output_fdg.csv"))
        and s not in excluded_subjects
    )
    print(f"{len(subjects)} subjects with output_fdg.csv in {args.output_dir} "
          f"(after excluding {len(excluded_subjects)})")

    all_pairs = []            # (subject, region, leads_val, our_val)
    all_composite_pairs = []  # (subject, composite_name, leads_val, our_val)
    used_subjects = set()
    skipped_subjects = []
    regions_never_resolved_ours = set()
    composites_with_missing_labels = defaultdict(set)  # {comp_name: {missing label ids}}

    for subj in subjects:
        subj_dir = os.path.join(args.output_dir, subj)
        seg_path = os.path.join(subj_dir, "output_fdg.csv")
        brainstem_path = os.path.join(subj_dir, "output_brainstem_fdg.csv")
        if not os.path.isfile(brainstem_path):
            skipped_subjects.append((subj, "missing output_brainstem_fdg.csv"))
            continue

        leads_glob = glob.glob(os.path.join(
            args.leads_base, subj, "FDG_*", "*_suvr-pons_roi-extractions.csv"))
        if not leads_glob:
            skipped_subjects.append((subj, "no *_suvr-pons_roi-extractions.csv in LEADS"))
            continue
        leads_path = sorted(leads_glob)[0]  # if there is more than one date, take the first

        seg_dict = load_segstats(seg_path)
        brainstem_dict = load_segstats(brainstem_path)
        pons_mean = get_pons_mean(brainstem_dict)
        if pons_mean is None:
            skipped_subjects.append((subj, "no 'Pons' row found in output_brainstem_fdg.csv"))
            continue

        leads_raw_pairs = parse_leads_roi_csv(leads_path)
        leads_bi = leads_bilateral_suvr(leads_raw_pairs, bilateral)
        our_bi = our_bilateral_suvr(seg_dict, pons_mean, bilateral)

        for bi_name in bilateral:
            if bi_name in leads_bi and bi_name in our_bi:
                all_pairs.append((subj, bi_name, leads_bi[bi_name], our_bi[bi_name]))
            elif bi_name not in our_bi:
                regions_never_resolved_ours.add(bi_name)

        # -- composite regions (only if --lut was given) --
        if args.lut:
            for comp_name, label_ids in composites.items():
                leads_val = leads_raw_pairs.get(comp_name)
                if leads_val is None:
                    continue
                leads_suvr = leads_val[0]  # already normalized by LEADS
                our_mean_raw, our_nvox, missing = composite_from_segstats(
                    seg_dict, label_ids, lut)
                if missing:
                    # Incomplete data on our side -- same rule as for the
                    # bilateral regions (if a hemisphere is missing, the
                    # whole region is excluded, never averaged over what is
                    # left): if ANY label of the composite is missing, that
                    # subject is dropped for that composite, rather than
                    # silently averaging over fewer labels than the
                    # composite defines.
                    composites_with_missing_labels[comp_name].update(missing)
                    continue
                if our_nvox == 0 or math.isnan(our_mean_raw):
                    continue
                our_suvr = our_mean_raw / pons_mean
                all_composite_pairs.append((subj, comp_name, leads_suvr, our_suvr))

            # -- the 6 regions that make up meta_temporal, individually,
            # with the SAME direct method (not the bilateral matching, which
            # fails for entorhinal/parahippocampal) --
            for region_name, label_ids in META_TEMPORAL_REGIONS.items():
                # LEADS side: reuse leads_bi (already a reliable L+R
                # combination) -- NOT leads_raw_pairs.get(region_name),
                # which has no combined name for these 6 individual regions
                # (LEADS reports them per hemisphere, like the other
                # bilateral regions; only meta_temporal comes already
                # combined because it is defined that way in
                # fsroi_list_FDG.csv).
                leads_suvr = leads_bi.get(region_name)
                if leads_suvr is None:
                    continue
                our_mean_raw, our_nvox, missing = composite_from_segstats(
                    seg_dict, label_ids, lut)
                if missing or our_nvox == 0 or math.isnan(our_mean_raw):
                    continue
                our_suvr = our_mean_raw / pons_mean
                all_composite_pairs.append((subj, f"[region] {region_name}", leads_suvr, our_suvr))

        used_subjects.add(subj)

    print(f"\n{len(used_subjects)} subjects with valid data on BOTH sides")
    if skipped_subjects:
        print(f"{len(skipped_subjects)} subjects discarded:")
        for s, reason in skipped_subjects[:10]:
            print(f"   {s}: {reason}")
        if len(skipped_subjects) > 10:
            print(f"   ... and {len(skipped_subjects) - 10} more")
    if regions_never_resolved_ours:
        print(f"\nWARNING: regions that could NEVER be resolved in our output_fdg.csv "
              f"(check the names in this version's FreeSurferColorLUT.txt):")
        print(f"   {sorted(regions_never_resolved_ours)}")

    if not all_pairs:
        raise SystemExit("No valid pair found -- check the paths/names above.")

    print(f"\n{len(all_pairs)} (subject, region) pairs in total for the analysis\n")

    # ── global and per-region aggregates ───────────────────────────────────
    pairs_with_region = [(r, ref, ours) for (_, r, ref, ours) in all_pairs]
    range_per_region = compute_range_per_region(pairs_with_region)

    global_mape_mean, global_mape_sd, global_n = mape_stats(
        [(ref, ours) for (_, _, ref, ours) in all_pairs])
    global_nrmse, _ = nrmse_per_region(pairs_with_region, range_per_region)
    print(f"Global MAPE: {global_mape_mean:.2f}% ± {global_mape_sd:.2f}% (SD)  "
          f"|  Global NRMSE: {global_nrmse:.2f}%  |  n={global_n}")

    region_pairs = defaultdict(list)
    for _, r, ref, ours in all_pairs:
        region_pairs[r].append((ref, ours))

    rows_out = []
    for region, pairs in region_pairs.items():
        mape_mean, mape_sd, n = mape_stats(pairs)
        rng_r = range_per_region.get(region)
        nrmse_mean, nrmse_sd, _ = nrmse_stats(pairs, rng_r)
        icc = icc_2_1(pairs)
        rows_out.append({
            "region": region, "n": n,
            "mape_mean": mape_mean, "mape_sd": mape_sd,
            "nrmse_mean": nrmse_mean, "nrmse_sd": nrmse_sd,
            "icc": icc,
        })

    rows_out.sort(key=lambda r: -(r["mape_mean"] if r["mape_mean"] == r["mape_mean"] else -1))

    with open(args.csv_regions, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["region", "n", "mape_mean", "mape_sd",
                                           "nrmse_mean", "nrmse_sd", "icc"])
        w.writeheader()
        w.writerows(rows_out)
    print(f"\nPer-region CSV (worst to best, by MAPE): {args.csv_regions}")
    print("  Top 5 regions with the MOST disagreement:")
    for row in rows_out[:5]:
        print(f"    {row['region']}: MAPE {row['mape_mean']:.2f}% (sd={row['mape_sd']:.2f}) "
              f"· NRMSE {row['nrmse_mean']:.2f}% · ICC={row['icc']:.3f} (n={row['n']})")

    if args.csv_raw:
        with open(args.csv_raw, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["subject", "region", "leads_ref", "ours"])
            w.writerows(all_pairs)
        print(f"\nRaw pairs: {args.csv_raw}")

    # ── composite regions ───────────────────────────────────────────────
    if args.lut:
        if composites_with_missing_labels:
            print(f"\nWARNING: composites with missing labels in some subject (that "
                  f"subject was excluded for that composite, no partial averaging):")
            for comp_name, labels in composites_with_missing_labels.items():
                print(f"   {comp_name}: labels {sorted(labels)}")
        if not all_composite_pairs:
            print("\n(no valid pairs for composite regions -- check --lut)")
        else:
            print(f"\n{len(all_composite_pairs)} composite (subject, region) pairs in total\n")
            comp_pairs = defaultdict(list)
            for _, comp_name, ref, ours in all_composite_pairs:
                comp_pairs[comp_name].append((ref, ours))

            comp_rows = []
            for comp_name, pairs in comp_pairs.items():
                mape_mean, mape_sd, n = mape_stats(pairs)
                icc = icc_2_1(pairs)
                comp_rows.append({
                    "composite_region": comp_name, "n": n,
                    "mape_mean": mape_mean, "mape_sd": mape_sd, "icc": icc,
                })
            comp_rows.sort(key=lambda r: -(r["mape_mean"] if r["mape_mean"] == r["mape_mean"] else -1))

            with open(args.csv_composite, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["composite_region", "n", "mape_mean", "mape_sd", "icc"])
                w.writeheader()
                w.writerows(comp_rows)
            print(f"Composite regions CSV: {args.csv_composite}")

            if args.csv_raw_composite:
                with open(args.csv_raw_composite, "w", newline="") as f:
                    w = csv.writer(f)
                    w.writerow(["subject", "composite_region", "leads_ref", "ours"])
                    w.writerows(all_composite_pairs)
                print(f"Per-subject composite SUVR (values, not the error): {args.csv_raw_composite}")

            # One block per region: actual value (mean ± SD) AND error (MAPE/ICC)
            print("\nComposite SUVR per region -- actual value and error, together:")
            for row in comp_rows:
                comp_name = row["composite_region"]
                arr = np.array(comp_pairs[comp_name], dtype=float)
                leads_vals, our_vals = arr[:, 0], arr[:, 1]
                print(f"    {comp_name} (n={row['n']}):")
                print(f"        LEADS: {np.mean(leads_vals):.4f} ± {np.std(leads_vals, ddof=1):.4f}  (SUVR, mean ± SD)")
                print(f"        Ours:  {np.mean(our_vals):.4f} ± {np.std(our_vals, ddof=1):.4f}  (SUVR, mean ± SD)")
                print(f"        Error: MAPE {row['mape_mean']:.2f}% ± {row['mape_sd']:.2f}% (SD)  ·  ICC={row['icc']:.3f}")


if __name__ == "__main__":
    main()
