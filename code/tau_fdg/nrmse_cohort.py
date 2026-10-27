#!/usr/bin/env python3
"""
nrmse_cohort.py
Validate tau SUVR (no-PVC / PVC) against A4 over ALL subjects found in an
output directory. MAPE is the PRIMARY metric (it orders the per-subject and
per-region CSVs and titles the Bland-Altman panels); NRMSE is a SECONDARY
metric, computed and reported next to MAPE but never used for ordering or
highlighting.

  - MAPE  = mean(|ours - a4| / |a4|) * 100, per subject / region / pooled.
  - NRMSE = sqrt(mean(((ours - a4) / range_A4_of_that_region)^2)) * 100.
    The A4 range is taken PER REGION (pooled over subjects only, never across
    regions with different scales) so that small regions are not
    flattened by large structures.
  - Both use A4 as the reference (never our own values) in the denominator.

Tau has several regions and a PVC / no-PVC split, so each metric yields TWO
numbers: one no-PVC and one PVC.

The reading / pairing logic is reused from compare_suvr_4way.py, so the
(ours, A4) pairs are EXACTLY the ones validated by the MAPE of the 4-way
comparison.

The A4 reference tables are NOT distributed with this repository; obtain
them from the A4 study.

Usage:
  python3 nrmse_cohort.py \
      --output_dir /path/to/output \
      --nopvc_a4   /path/to/A4/TAUSUVR_26Jan2026.csv \
      --pvc_a4     /path/to/A4/TAUSUVR_PETSURFER_26Jan2026.csv

Optional:
  --nopvc_name output.csv                               (default)
  --pvc_name   gtmpvc_T1space_mask.output/gtm.stats.dat (default)
  --subjects   <ID1> <ID2> ...   (if omitted, all subjects found are used)
  --csv        cohort_nrmse_pairs.csv    (dump every pair used, for auditing)
"""

import argparse
import os
import glob
import numpy as np

# The comparison module imports matplotlib.pyplot; selecting a headless
# backend BEFORE importing it avoids failures on machines without a display.
import matplotlib
matplotlib.use("Agg")
import matplotlib.gridspec as gridspec
import matplotlib.ticker as mtick

try:
    from adjustText import adjust_text
    _HAS_ADJUSTTEXT = True
except ImportError:
    _HAS_ADJUSTTEXT = False

# reuse the reading/pairing logic of the comparison script (same directory)
from compare_suvr_4way import (
    load_segstats, load_gtm, load_a4_row,
    normalize_nopvc, compute_bilateral_suvr, compute_bilateral_suvr_gtm,
    BILATERAL_REGIONS,
    STRUCT_TO_A4_MEAN, STRUCT_TO_A4_PVC, STRUCT_TO_A4_VOL, STRUCT_TO_A4_NVOX,
    VOL_THRESHOLD, NVOX_THRESHOLD,
)

# ── NUMBER OF LABELLED POINTS ───────────────────────────────────────────────
# Number of worst points (above and below) that get a text label in the
# Bland-Altman plots.
N_EXTREME_LABELS = 4
# ────────────────────────────────────────────────────────────────────────────

def pairs_for_subject(subject_id, nopvc_ours, pvc_ours, nopvc_a4_path, pvc_a4_path):
    """Return (nopvc_pairs, pvc_pairs, extras). nopvc_pairs / pvc_pairs are
    lists of (region, a4, ours) SUVR tuples; the region name is kept so the
    pairs can later be grouped PER REGION (besides per subject / globally)
    to find which regions disagree most systematically with A4. 'extras'
    holds the already loaded raw data (seg_raw, seg_norm, gtm, a4_nopvc,
    a4_pvc) so other_pairs_for_subject() can reuse it without re-reading
    the files. Same region-by-region pairing as the 4-way comparison."""
    seg_raw  = load_segstats(nopvc_ours)
    seg_norm = normalize_nopvc(seg_raw)
    gtm      = load_gtm(pvc_ours)
    a4_nopvc = load_a4_row(nopvc_a4_path, subject_id)
    a4_pvc   = load_a4_row(pvc_a4_path,   subject_id)

    our_np, a4_np = compute_bilateral_suvr(seg_norm, seg_raw, a4_nopvc)
    our_pv, a4_pv = compute_bilateral_suvr_gtm(gtm, a4_pvc)

    nopvc_pairs, pvc_pairs = [], []
    for r in BILATERAL_REGIONS:
        if r in our_np and r in a4_np:
            a, o = a4_np[r], our_np[r]
            if np.isfinite(a) and np.isfinite(o):
                nopvc_pairs.append((r, a, o))
        if r in our_pv and r in a4_pv:
            a, o = a4_pv[r], our_pv[r]
            if np.isfinite(a) and np.isfinite(o):
                pvc_pairs.append((r, a, o))
    extras = (seg_raw, seg_norm, gtm, a4_nopvc, a4_pvc)
    return nopvc_pairs, pvc_pairs, extras


def other_pairs_for_subject(seg_raw, seg_norm, gtm, a4_nopvc, a4_pvc):
    """Extract (struct, a4, ours) pairs for the other comparisons of the
    4-way script that are NOT SUVR: mean intensity (no-PVC and PVC),
    volume (mm3) and NVoxels. Same filtering as compare_suvr_4way.py
    (a4 > 0, ours > 0, and the volume / NVoxels threshold that discards
    obvious scale outliers). Nothing is printed; results only go to CSV."""
    mean_pairs, pvc_mean_pairs, vol_pairs, nvox_pairs = [], [], [], []

    for struct, a4_col in STRUCT_TO_A4_MEAN.items():
        if struct in seg_norm and a4_col in a4_nopvc.index:
            try:
                a4_val, our_val = float(a4_nopvc[a4_col]), seg_norm[struct]
                if a4_val > 0 and our_val > 0:
                    mean_pairs.append((struct, a4_val, our_val))
            except (ValueError, TypeError):
                pass

    for struct, pvc_col in STRUCT_TO_A4_PVC.items():
        if struct in gtm and pvc_col in a4_pvc.index:
            try:
                a4_val, our_val = float(a4_pvc[pvc_col]), gtm[struct]["mean"]
                if a4_val > 0 and our_val > 0:
                    pvc_mean_pairs.append((struct, a4_val, our_val))
            except (ValueError, TypeError):
                pass

    for struct, a4_col in STRUCT_TO_A4_VOL.items():
        if struct in seg_raw and a4_col in a4_nopvc.index:
            try:
                a4_val, our_val = float(a4_nopvc[a4_col]), seg_raw[struct]["volume"]
                if a4_val > 0 and our_val > 0 and a4_val < VOL_THRESHOLD:
                    vol_pairs.append((struct, a4_val, our_val))
            except (ValueError, TypeError):
                pass

    for struct, a4_col in STRUCT_TO_A4_NVOX.items():
        if struct in gtm and a4_col in a4_pvc.index:
            try:
                a4_val, our_val = float(a4_pvc[a4_col]), gtm[struct]["nvoxels"]
                if a4_val > 0 and our_val > 0 and a4_val < NVOX_THRESHOLD:
                    nvox_pairs.append((struct, a4_val, our_val))
            except (ValueError, TypeError):
                pass

    return mean_pairs, pvc_mean_pairs, vol_pairs, nvox_pairs


def nrmse(pairs, rng_override=None):
    """pairs = list of (a4_ref, ours). NRMSE normalised by range."""
    if not pairs:
        return float("nan"), 0
    arr = np.array(pairs, dtype=float)
    a4, ours = arr[:, 0], arr[:, 1]
    rmse = np.sqrt(np.mean((a4 - ours) ** 2))
    rng = rng_override if rng_override is not None else (a4.max() - a4.min())
    val = (rmse / rng * 100) if rng > 0 else float("nan")
    return val, len(pairs)


def mape(pairs):
    """pairs = list of (a4_ref, ours). MAPE = mean(|ours - a4| / |a4|) * 100."""
    if not pairs:
        return float("nan"), 0
    arr = np.array(pairs, dtype=float)
    a4, ours = arr[:, 0], arr[:, 1]
    val = np.mean(np.abs(ours - a4) / (np.abs(a4) + 1e-9) * 100)
    return val, len(pairs)


def mape_stats(pairs):
    if not pairs:
        return float("nan"), float("nan"), 0
    arr = np.array(pairs, dtype=float)
    a4, ours = arr[:, 0], arr[:, 1]
    errs = np.abs(ours - a4) / (np.abs(a4) + 1e-9) * 100
    mean_val = float(np.mean(errs))
    sd = float(np.std(errs, ddof=1)) if len(errs) > 1 else float("nan")
    return mean_val, sd, len(pairs)


def nrmse_stats(pairs, rng):
    if not pairs or rng is None or rng <= 0:
        return float("nan"), float("nan"), 0
    arr = np.array(pairs, dtype=float)
    a4, ours = arr[:, 0], arr[:, 1]
    errs = (ours - a4) / rng * 100
    mean_val = float(np.mean(errs))
    sd = float(np.std(errs, ddof=1)) if len(errs) > 1 else float("nan")
    return mean_val, sd, len(pairs)


def icc_2_1(pairs):
    if len(pairs) < 2:
        return float("nan")
    arr = np.array(pairs, dtype=float)  # columns: [a4, ours]
    n, k = arr.shape  # k=2 (A4, ours)
    grand_mean = arr.mean()
    row_means = arr.mean(axis=1)
    col_means = arr.mean(axis=0)

    SST = np.sum((arr - grand_mean) ** 2)
    SSR = k * np.sum((row_means - grand_mean) ** 2)
    SSC = n * np.sum((col_means - grand_mean) ** 2)
    SSE = SST - SSR - SSC

    df_r, df_c, df_e = n - 1, k - 1, (n - 1) * (k - 1)
    if df_r <= 0 or df_e <= 0:
        return float("nan")
    MSR, MSC, MSE = SSR / df_r, SSC / df_c, SSE / df_e

    denom = MSR + (k - 1) * MSE + k * (MSC - MSE) / n
    if denom == 0:
        return float("nan")
    return float((MSR - MSE) / denom)


def compute_range_per_region(pairs_with_region):
    from collections import defaultdict
    a4_values_per_region = defaultdict(list)
    for p in pairs_with_region:
        if len(p) == 4:
            _, region, a4, _ = p
        else:
            region, a4, _ = p
        if np.isfinite(a4):
            a4_values_per_region[region].append(a4)
    return {r: (max(vs) - min(vs)) for r, vs in a4_values_per_region.items() if vs}


def nrmse_per_region(pairs_with_region, rng_dict):
    normalized = []
    for p in pairs_with_region:
        if len(p) == 4:
            _, region, a4, ours = p
        else:
            region, a4, ours = p
        rng = rng_dict.get(region)
        if rng is not None and rng > 0 and np.isfinite(a4) and np.isfinite(ours):
            normalized.append(((ours - a4) / rng) ** 2)
    if not normalized:
        return float("nan"), 0
    val = float(np.sqrt(np.mean(normalized)) * 100)
    return val, len(normalized)


def bland_altman(pairs):
    if len(pairs) < 2:
        return float("nan"), float("nan"), float("nan")
    arr = np.array(pairs, dtype=float)
    a4, ours = arr[:, 0], arr[:, 1]
    diff = ours - a4
    bias = np.mean(diff)
    sd = np.std(diff, ddof=1)
    return bias, bias - 1.96 * sd, bias + 1.96 * sd


def main():
    # Same PETPIPELINE_BASE convention as run_public_pipeline.sh/evaluate_subject.py.
    _repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    petpipeline_base = os.environ.get("PETPIPELINE_BASE") or os.path.join(_repo_root, "pet_pipeline")
    default_output_dir = os.path.join(petpipeline_base, "output")

    p = argparse.ArgumentParser()
    p.add_argument("--output_dir", default=default_output_dir,
                   help=f"directory containing one sub-directory per subject (default: {default_output_dir})")
    p.add_argument("--nopvc_a4",   required=True, help="TAUSUVR_26Jan2026.csv")
    p.add_argument("--pvc_a4",     required=True, help="TAUSUVR_PETSURFER_26Jan2026.csv")
    p.add_argument("--nopvc_name", default="output.csv")
    p.add_argument("--pvc_name",   default="gtmpvc_T1space_mask.output/gtm.stats.dat")
    p.add_argument("--subjects",   nargs="*", default=None,
                   help="subject list; if omitted, every subject with both files is used")
    p.add_argument("--csv",        default=None, help="optional: dump the raw pairs used")
    p.add_argument("--csv_subjects", default="cohort_per_subject.csv",
                   help="CSV with MAPE/NRMSE per subject, sorted from worst to best")
    p.add_argument("--csv_regions", default="cohort_per_region.csv",
                   help="CSV with MAPE/NRMSE per anatomical region, sorted from worst to best")
    args = p.parse_args()

    outdir = os.path.expanduser(args.output_dir)

    if args.subjects:
        candidates = args.subjects
    else:
        candidates = sorted(
            os.path.basename(os.path.dirname(pp))
            for pp in glob.glob(os.path.join(outdir, "*", args.nopvc_name))
        )

    all_nopvc, all_pvc = [], []
    all_mean, all_pvc_mean, all_vol, all_nvox = [], [], [], []
    used, skipped = [], []
    subj_raw_pairs = {}

    print(f"Looking for subjects in {outdir} ...")
    for subj in candidates:
        nopvc_ours = os.path.join(outdir, subj, args.nopvc_name)
        pvc_ours   = os.path.join(outdir, subj, args.pvc_name)
        if not (os.path.isfile(nopvc_ours) and os.path.isfile(pvc_ours)):
            skipped.append((subj, "missing output.csv or gtm.stats.dat"))
            continue
        try:
            np_pairs, pv_pairs, extras = pairs_for_subject(
                subj, nopvc_ours, pvc_ours, args.nopvc_a4, args.pvc_a4)
            mean_p, pvc_mean_p, vol_p, nvox_p = other_pairs_for_subject(*extras)
        except Exception as e:
            skipped.append((subj, f"error: {e}"))
            continue
        if not np_pairs and not pv_pairs:
            skipped.append((subj, "no valid pairs"))
            continue

        # Keep the full tuple (subject, region, a4, ours)
        all_nopvc.extend((subj, r, a, o) for (r, a, o) in np_pairs)
        all_pvc.extend((subj, r, a, o) for (r, a, o) in pv_pairs)

        all_mean.extend((subj, s, a, o) for (s, a, o) in mean_p)
        all_pvc_mean.extend((subj, s, a, o) for (s, a, o) in pvc_mean_p)
        all_vol.extend((subj, s, a, o) for (s, a, o) in vol_p)
        all_nvox.extend((subj, s, a, o) for (s, a, o) in nvox_p)
        used.append((subj, len(np_pairs), len(pv_pairs)))

        np_pairs_flat_s = [(r, a, o) for (r, a, o) in np_pairs]
        pv_pairs_flat_s = [(r, a, o) for (r, a, o) in pv_pairs]
        subj_raw_pairs[subj] = (np_pairs_flat_s, pv_pairs_flat_s)
        mape_np_s, _ = mape([(a, o) for (_, a, o) in np_pairs_flat_s])
        mape_pv_s, _ = mape([(a, o) for (_, a, o) in pv_pairs_flat_s])
        print(f"  [ok] {subj}: {len(np_pairs)} no-PVC (MAPE {mape_np_s:.1f}%) · "
              f"{len(pv_pairs)} PVC (MAPE {mape_pv_s:.1f}%)")

    for subj, why in skipped:
        print(f"  [skip] {subj}: {why}")

    # ── global NRMSE + global Bland-Altman ────────────────────────────────────
    np_pairs = all_nopvc
    pv_pairs = all_pvc
    np_pairs_flat = [(a, o) for (_, _, a, o) in np_pairs]
    pv_pairs_flat = [(a, o) for (_, _, a, o) in pv_pairs]

    mape_np, _ = mape(np_pairs_flat)
    mape_pv, _ = mape(pv_pairs_flat)
    bias_np, lo_np, hi_np = bland_altman(np_pairs_flat)
    bias_pv, lo_pv, hi_pv = bland_altman(pv_pairs_flat)

    rng_per_region_np = compute_range_per_region(np_pairs)
    rng_per_region_pv = compute_range_per_region(pv_pairs)

    nrmse_np, n_np = nrmse_per_region(np_pairs, rng_per_region_np)
    nrmse_pv, n_pv = nrmse_per_region(pv_pairs, rng_per_region_pv)

    per_subject = []
    for subj, (np_pairs_s, pv_pairs_s) in subj_raw_pairs.items():
        mape_np_s, _  = mape([(a, o) for (_, a, o) in np_pairs_s])
        mape_pv_s, _  = mape([(a, o) for (_, a, o) in pv_pairs_s])
        nrmse_np_s, _ = nrmse_per_region(np_pairs_s, rng_per_region_np)
        nrmse_pv_s, _ = nrmse_per_region(pv_pairs_s, rng_per_region_pv)
        per_subject.append({
            "subject": subj,
            "n_nopvc": len(np_pairs_s), "mape_nopvc": mape_np_s, "nrmse_nopvc": nrmse_np_s,
            "n_pvc":   len(pv_pairs_s), "mape_pvc":   mape_pv_s, "nrmse_pvc":   nrmse_pv_s,
        })

    n_subj = len(used)
    print("\n── Global cohort (range over A4 reference; BA diff = ours - A4) ──────────────────")
    print(f"{'Series':<26} {'Nsubj':>5} {'Npairs':>7} {'MAPE':>8} {'NRMSE':>8} {'bias':>9} {'LoA_lo':>9} {'LoA_hi':>9}")
    print("-" * 89)
    print(f"{'SUVR no-PVC: ours vs A4':<26} {n_subj:>5} {n_np:>7} {mape_np:>7.2f}% {nrmse_np:>7.2f}% "
          f"{bias_np:>+9.4f} {lo_np:>+9.4f} {hi_np:>+9.4f}")
    print(f"{'SUVR PVC: ours vs A4':<26} {n_subj:>5} {n_pv:>7} {mape_pv:>7.2f}% {nrmse_pv:>7.2f}% "
          f"{bias_pv:>+9.4f} {lo_pv:>+9.4f} {hi_pv:>+9.4f}")
    print("-" * 89)

    # ── cohort-wide Bland-Altman plot (2 panels) ───────────────────────
    if len(np_pairs) >= 2 and len(pv_pairs) >= 2:
        import matplotlib.pyplot as plt

        palette = (list(plt.get_cmap("tab20").colors)
                  + list(plt.get_cmap("tab20b").colors)
                  + list(plt.get_cmap("tab20c").colors))
        region_color_map = {r: palette[i % len(palette)] for i, r in enumerate(BILATERAL_REGIONS)}

        def _panel(ax_main, pairs, title_base):
            subjs_pt = [p[0] for p in pairs]
            regions_pt = [p[1] for p in pairs]
            arr = np.array([(p[2], p[3]) for p in pairs], dtype=float)
            a4, ours = arr[:, 0], arr[:, 1]
            diff = ours - a4
            mean = (ours + a4) / 2.0
            bias = np.mean(diff)
            sd = np.std(diff, ddof=1)
            n_total = len(diff)

            errs_mape = np.abs(ours - a4) / (np.abs(a4) + 1e-9) * 100
            mape_val = float(np.mean(errs_mape))
            mape_sd = float(np.std(errs_mape, ddof=1)) if len(errs_mape) > 1 else float("nan")

            hb = ax_main.hexbin(mean, diff, gridsize=40, cmap="Oranges", mincnt=1,
                                norm=matplotlib.colors.LogNorm())

            ax_main.axhline(bias, color="#333333", lw=1.5, label=f"bias = {bias:+.4f}")
            ax_main.axhline(bias + 1.96 * sd, color="#B03030", lw=1.0, ls="--",
                             label=f"+1.96 SD = {bias + 1.96 * sd:+.4f}")
            ax_main.axhline(bias - 1.96 * sd, color="#B03030", lw=1.0, ls="--",
                             label=f"-1.96 SD = {bias - 1.96 * sd:+.4f}")
            ax_main.axhline(0.0, color="#999999", lw=0.8, ls=":")
            ax_main.set_xlabel("Mean (A4 + ours) / 2", fontsize=11)
            ax_main.set_ylabel("Difference (ours - A4)", fontsize=11)
            ax_main.tick_params(axis="both", labelsize=10)
            ax_main.set_title(f"{title_base} — MAPE = {mape_val:.2f}% ± {mape_sd:.2f}%",
                               fontsize=11)

            above_mask = diff > (bias + 1.96 * sd)
            below_mask = diff < (bias - 1.96 * sd)
            pct_above = 100.0 * np.sum(above_mask) / n_total
            pct_below = 100.0 * np.sum(below_mask)  / n_total
            pct_within = 100.0 - pct_above - pct_below

            trans_blend = matplotlib.transforms.blended_transform_factory(
                ax_main.transAxes, ax_main.transData)

            ax_main.text(
                0.03, bias, f"{pct_within:.1f}%",
                transform=trans_blend, fontsize=15, fontweight="bold",
                va="center", ha="left", color="#222222",
                bbox=dict(boxstyle="round,pad=0.35", facecolor="white",
                          edgecolor="#999999", alpha=0.85),
            )
            ax_main.text(
                0.03, bias + 1.96 * sd, f"{pct_above:.1f}% above",
                transform=trans_blend, fontsize=10, va="bottom", ha="left",
                color="#B03030",
            )
            ax_main.text(
                0.03, bias - 1.96 * sd, f"{pct_below:.1f}% below",
                transform=trans_blend, fontsize=10, va="top", ha="left",
                color="#B03030",
            )

            outlier_mask = above_mask | below_mask
            region_handles_local = {}
            colored_points = []

            if outlier_mask.sum() > 0:
                regions_outlier = np.array(regions_pt)[outlier_mask]
                subjs_outlier = np.array(subjs_pt)[outlier_mask]
                mean_outlier = mean[outlier_mask]
                diff_outlier = diff[outlier_mask]

                for reg in sorted(set(regions_outlier)):
                    sel = regions_outlier == reg
                    h = ax_main.scatter(
                        mean_outlier[sel], diff_outlier[sel],
                        s=28, color=region_color_map[reg], edgecolors="black",
                        linewidths=0.5, label=reg, zorder=5,
                    )
                    region_handles_local[reg] = h

                for m_pt, d_pt, reg_pt, subj_pt in zip(mean_outlier, diff_outlier, regions_outlier, subjs_outlier):
                    colored_points.append((m_pt, d_pt, reg_pt, subj_pt))

            # Label the most extreme points
            above_pts = sorted([p for p in colored_points if p[1] > 0], key=lambda p: -p[1])[:N_EXTREME_LABELS]
            below_pts  = sorted([p for p in colored_points if p[1] < 0], key=lambda p: p[1])[:N_EXTREME_LABELS]
            labelled_points = above_pts + below_pts

            if _HAS_ADJUSTTEXT and labelled_points:
                texts = []
                xs_pts = [p[0] for p in labelled_points]
                ys_pts = [p[1] for p in labelled_points]
                for m_pt, d_pt, reg_pt, subj_pt in labelled_points:
                    a4_pt = m_pt - d_pt / 2.0
                    pct_pt = abs(d_pt) / abs(a4_pt) * 100 if a4_pt else float("nan")
                    t = ax_main.text(
                        m_pt, d_pt, f"{subj_pt}\n{reg_pt} ({pct_pt:.1f}%)",
                        fontsize=10, va="center", ha="left", color="#222222",
                        bbox=dict(boxstyle="round,pad=0.15", facecolor="white",
                                  edgecolor="#999999", alpha=0.85, lw=0.4),
                    )
                    texts.append(t)
                adjust_text(
                    texts, x=xs_pts, y=ys_pts, ax=ax_main,
                    arrowprops=dict(arrowstyle="-", color="#666666", lw=0.6, shrinkA=0, shrinkB=2),
                    expand=(1.3, 1.6),
                )
            else:
                for grupo, signo in ((above_pts, 1), (below_pts, -1)):
                    for i, (m_pt, d_pt, reg_pt, subj_pt) in enumerate(grupo):
                        a4_pt = m_pt - d_pt / 2.0
                        pct_pt = abs(d_pt) / abs(a4_pt) * 100 if a4_pt else float("nan")
                        offset_y = signo * (16 + i * 28)
                        offset_x = 10 if i % 2 == 0 else -70
                        ha_lbl = "left" if i % 2 == 0 else "right"
                        ax_main.annotate(
                            f"{subj_pt}\n{reg_pt} ({pct_pt:.1f}%)",
                            xy=(m_pt, d_pt), xytext=(offset_x, offset_y),
                            textcoords="offset points", fontsize=10,
                            va="center", ha=ha_lbl, color="#222222",
                            bbox=dict(boxstyle="round,pad=0.15", facecolor="white",
                                      edgecolor="#999999", alpha=0.85, lw=0.4),
                            arrowprops=dict(arrowstyle="-", color="#666666", lw=0.6, shrinkA=0, shrinkB=2),
                        )

            y_lo, y_hi = ax_main.get_ylim()
            y_pad = 0.20 * (y_hi - y_lo)
            ax_main.set_ylim(y_lo - y_pad, y_hi + y_pad)

            handles_bias = [
                plt.Line2D([0], [0], color="#333333", lw=1.5, label=f"bias = {bias:+.4f}"),
                plt.Line2D([0], [0], color="#B03030", lw=1.0, ls="--",
                           label=f"+1.96 SD = {bias + 1.96 * sd:+.4f}"),
                plt.Line2D([0], [0], color="#B03030", lw=1.0, ls="--",
                           label=f"-1.96 SD = {bias - 1.96 * sd:+.4f}"),
            ]
            ax_main.legend(handles=handles_bias, fontsize=10, loc="upper left")

            print(f"  {title_base}: {pct_within:.1f}% within LoA · "
                  f"{pct_above:.1f}% above · {pct_below:.1f}% below (n={n_total})")

            return hb, region_handles_local

        fig = plt.figure(figsize=(15, 8.5))
        gs_outer = gridspec.GridSpec(1, 3, figure=fig, width_ratios=[1, 1, 0.03], wspace=0.15, top=0.90, bottom=0.30)
        ax_np = fig.add_subplot(gs_outer[0])
        ax_pv = fig.add_subplot(gs_outer[1])
        cax = fig.add_subplot(gs_outer[2])

        hb_np, handles_np = _panel(ax_np, np_pairs, "Bland-Altman SUVR no-PVC — cohort")
        hb_pv, handles_pv = _panel(ax_pv, pv_pairs, "Bland-Altman SUVR PVC — cohort")

        # Common colour limits (1 is the minimum for log-scaled counts)
        vmax_global = max(hb_np.get_array().max(), hb_pv.get_array().max())
        hb_np.set_clim(vmin=1, vmax=vmax_global)
        hb_pv.set_clim(vmin=1, vmax=vmax_global)

        # -- Colour bar: log scale, labels in % --
        # 100% corresponds to the densest hexbin cell (vmax_global), not to
        # the total N of the panel: no single cell holds a large fraction of
        # all pairs, so normalising by the total N would never get close to
        # 100% at the darkest end.
        cb = fig.colorbar(hb_pv, cax=cax)
        cb.ax.yaxis.set_minor_locator(mtick.NullLocator()) # remove minor ticks
        cb.ax.tick_params(axis='y', length=0, labelsize=10) # remove major tick marks

        def fmt_log_perc(x, pos):
            perc = (x / vmax_global) * 100
            if perc < 0.1: return f"{perc:.3f}%"
            elif perc < 1: return f"{perc:.2f}%"
            else: return f"{perc:.1f}%"

        cb.ax.yaxis.set_major_formatter(mtick.FuncFormatter(fmt_log_perc))
        cb.set_label("Density (% of the densest cell)", fontsize=10)
        # Force the 100% tick (densest cell) to always appear, wherever the
        # automatic LogLocator ticks fall.
        existing_ticks = [t for t in cb.get_ticks() if 1 <= t <= vmax_global]
        cb.set_ticks(sorted(set(existing_ticks) | {vmax_global}))

        region_handles = {**handles_np, **handles_pv}
        if region_handles:
            regions_sorted = sorted(region_handles.keys())
            fig.legend(
                [region_handles[r] for r in regions_sorted], regions_sorted,
                loc="lower center", ncol=8, fontsize=10, title="Region (outliers, shared by both panels)",
                title_fontsize=10, framealpha=0.95, bbox_to_anchor=(0.5, 0.0),
            )

        ba_out = os.path.join(outdir, "cohort_bland_altman.png")
        fig.savefig(ba_out, dpi=180, bbox_inches="tight")
        print(f"\nCohort Bland-Altman plot: {ba_out}")

    # ── per-subject CSV, sorted worst to best (PVC MAPE, descending) ─────
    if args.csv_subjects and per_subject:
        import csv
        per_subject_sorted = sorted(
            per_subject,
            key=lambda r: (r["mape_pvc"] if r["mape_pvc"] == r["mape_pvc"] else -1),
            reverse=True,
        )
        with open(args.csv_subjects, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=[
                "subject", "n_nopvc", "mape_nopvc", "nrmse_nopvc",
                "n_pvc", "mape_pvc", "nrmse_pvc",
            ])
            w.writeheader()
            for row in per_subject_sorted:
                w.writerow(row)
        print(f"\nPer-subject CSV (worst to best, by PVC MAPE): {args.csv_subjects}")

        # Bland-Altman for the 5 worst subjects
        per_subject_sorted_nopvc = sorted(
            per_subject,
            key=lambda r: (r["mape_nopvc"] if r["mape_nopvc"] == r["mape_nopvc"] else -1),
            reverse=True,
        )
        worst5_nopvc_ids = [row["subject"] for row in per_subject_sorted_nopvc[:5]]
        worst5_nopvc_mape = {row["subject"]: row["mape_nopvc"] for row in per_subject_sorted_nopvc[:5]}
        worst5_pvc_ids = [row["subject"] for row in per_subject_sorted[:5]]
        worst5_pvc_mape = {row["subject"]: row["mape_pvc"] for row in per_subject_sorted[:5]}

        if len(np_pairs) >= 2 and len(pv_pairs) >= 2:
            palette5 = list(plt.get_cmap("tab10").colors)[:5]

            def _panel_worst(ax_main, all_subject_pairs, title_base, worst_ids, mape_dict):
                subj_color_map = dict(zip(worst_ids, palette5))

                subjs_pt = [p[0] for p in all_subject_pairs]
                regions_pt_local = [p[1] for p in all_subject_pairs]
                arr = np.array([(p[2], p[3]) for p in all_subject_pairs], dtype=float)
                a4, ours = arr[:, 0], arr[:, 1]
                diff = ours - a4
                mean = (ours + a4) / 2.0
                bias = np.mean(diff)
                sd = np.std(diff, ddof=1)
                n_total = len(diff)

                errs_mape = np.abs(ours - a4) / (np.abs(a4) + 1e-9) * 100
                mape_val = float(np.mean(errs_mape))
                mape_sd = float(np.std(errs_mape, ddof=1)) if len(errs_mape) > 1 else float("nan")

                hb = ax_main.hexbin(mean, diff, gridsize=40, cmap="Oranges", mincnt=1,
                                    norm=matplotlib.colors.LogNorm())

                ax_main.axhline(bias, color="#333333", lw=1.5)
                ax_main.axhline(bias + 1.96 * sd, color="#B03030", lw=1.0, ls="--")
                ax_main.axhline(bias - 1.96 * sd, color="#B03030", lw=1.0, ls="--")
                ax_main.axhline(0.0, color="#999999", lw=0.8, ls=":")
                ax_main.set_xlabel("Mean (A4 + ours) / 2", fontsize=11)
                ax_main.set_ylabel("Difference (ours - A4)", fontsize=11)
                ax_main.tick_params(axis="both", labelsize=10)
                ax_main.set_title(f"{title_base} — MAPE = {mape_val:.2f}% ± {mape_sd:.2f}%",
                                   fontsize=11)

                above_mask = diff > (bias + 1.96 * sd)
                below_mask = diff < (bias - 1.96 * sd)
                pct_above = 100.0 * np.sum(above_mask) / n_total
                pct_below = 100.0 * np.sum(below_mask)  / n_total
                pct_within = 100.0 - pct_above - pct_below

                trans_blend = matplotlib.transforms.blended_transform_factory(
                    ax_main.transAxes, ax_main.transData)
                ax_main.text(
                    0.03, bias, f"{pct_within:.1f}%",
                    transform=trans_blend, fontsize=15, fontweight="bold",
                    va="center", ha="left", color="#222222",
                    bbox=dict(boxstyle="round,pad=0.35", facecolor="white",
                              edgecolor="#999999", alpha=0.85),
                )
                ax_main.text(
                    0.03, bias + 1.96 * sd, f"{pct_above:.1f}% above",
                    transform=trans_blend, fontsize=10, va="bottom", ha="left",
                    color="#B03030",
                )
                ax_main.text(
                    0.03, bias - 1.96 * sd, f"{pct_below:.1f}% below",
                    transform=trans_blend, fontsize=10, va="top", ha="left",
                    color="#B03030",
                )

                outlier_mask = above_mask | below_mask
                subjs_arr = np.array(subjs_pt)
                regions_arr_local = np.array(regions_pt_local)
                local_handles = {}
                colored_points = []
                for subj_id in worst_ids:
                    sel = (subjs_arr == subj_id) & outlier_mask
                    if sel.sum() > 0:
                        h = ax_main.scatter(
                            mean[sel], diff[sel], s=30, color=subj_color_map[subj_id],
                            edgecolors="black", linewidths=0.5, label=subj_id, zorder=5,
                        )
                        local_handles[subj_id] = h
                        for m_pt, d_pt, reg_pt in zip(mean[sel], diff[sel], regions_arr_local[sel]):
                            colored_points.append((m_pt, d_pt, reg_pt, subj_id))

                # Label the most extreme points
                above_pts = sorted([p for p in colored_points if p[1] > 0], key=lambda p: -p[1])[:N_EXTREME_LABELS]
                below_pts  = sorted([p for p in colored_points if p[1] < 0], key=lambda p: p[1])[:N_EXTREME_LABELS]
                labelled_points = above_pts + below_pts

                if _HAS_ADJUSTTEXT and labelled_points:
                    texts = []
                    xs_pts = [p[0] for p in labelled_points]
                    ys_pts = [p[1] for p in labelled_points]
                    for m_pt, d_pt, reg_pt, subj_pt in labelled_points:
                        a4_pt = m_pt - d_pt / 2.0
                        pct_pt = abs(d_pt) / abs(a4_pt) * 100 if a4_pt else float("nan")
                        t = ax_main.text(
                            m_pt, d_pt, f"{subj_pt}\n{reg_pt} ({pct_pt:.1f}%)",
                            fontsize=10, va="center", ha="left", color="#222222",
                            bbox=dict(boxstyle="round,pad=0.15", facecolor="white",
                                      edgecolor="#999999", alpha=0.85, lw=0.4),
                        )
                        texts.append(t)
                    adjust_text(
                        texts, x=xs_pts, y=ys_pts, ax=ax_main,
                        arrowprops=dict(arrowstyle="-", color="#666666", lw=0.6, shrinkA=0, shrinkB=2),
                        expand=(1.3, 1.6),
                    )
                else:
                    for grupo, signo in ((above_pts, 1), (below_pts, -1)):
                        for i, (m_pt, d_pt, reg_pt, subj_pt) in enumerate(grupo):
                            a4_pt = m_pt - d_pt / 2.0
                            pct_pt = abs(d_pt) / abs(a4_pt) * 100 if a4_pt else float("nan")
                            offset_y = signo * (16 + i * 28)
                            offset_x = 10 if i % 2 == 0 else -70
                            ha_lbl = "left" if i % 2 == 0 else "right"
                            ax_main.annotate(
                                f"{subj_pt}\n{reg_pt} ({pct_pt:.1f}%)",
                                xy=(m_pt, d_pt), xytext=(offset_x, offset_y),
                                textcoords="offset points", fontsize=10,
                                va="center", ha=ha_lbl, color="#222222",
                                bbox=dict(boxstyle="round,pad=0.15", facecolor="white",
                                          edgecolor="#999999", alpha=0.85, lw=0.4),
                                arrowprops=dict(arrowstyle="-", color="#666666", lw=0.6, shrinkA=0, shrinkB=2),
                            )

                y_lo, y_hi = ax_main.get_ylim()
                y_pad = 0.20 * (y_hi - y_lo)
                ax_main.set_ylim(y_lo - y_pad, y_hi + y_pad)

                if local_handles:
                    ax_main.legend(
                        [local_handles[s] for s in worst_ids if s in local_handles],
                        [f"{s} ({mape_dict[s]:.2f}%)" for s in worst_ids if s in local_handles],
                        loc="lower left", bbox_to_anchor=(0.0, 1.07), ncol=3,
                        fontsize=10, title="5 worst (MAPE)", title_fontsize=10,
                        framealpha=0.95, borderaxespad=0,
                    )
                return hb

            fig2 = plt.figure(figsize=(15, 9.2))
            gs2 = gridspec.GridSpec(1, 3, figure=fig2, width_ratios=[1, 1, 0.03], wspace=0.15, top=0.66)
            ax2_np = fig2.add_subplot(gs2[0])
            ax2_pv = fig2.add_subplot(gs2[1])
            cax2 = fig2.add_subplot(gs2[2])

            hb2_np = _panel_worst(ax2_np, all_nopvc, "Bland-Altman SUVR no-PVC — 5 worst subjects", worst5_nopvc_ids, worst5_nopvc_mape)
            hb2_pv = _panel_worst(ax2_pv, all_pvc, "Bland-Altman SUVR PVC — 5 worst subjects", worst5_pvc_ids, worst5_pvc_mape)

            vmax2_global = max(hb2_np.get_array().max(), hb2_pv.get_array().max())
            hb2_np.set_clim(vmin=1, vmax=vmax2_global)
            hb2_pv.set_clim(vmin=1, vmax=vmax2_global)

            # -- Colour bar: log scale, labels in % --
            # 100% = densest cell (vmax2_global), same criterion as the
            # full-cohort figure above.
            cb2 = fig2.colorbar(hb2_pv, cax=cax2)
            cb2.ax.yaxis.set_minor_locator(mtick.NullLocator())
            cb2.ax.tick_params(axis='y', length=0, labelsize=10)

            def fmt_log_perc2(x, pos):
                perc = (x / vmax2_global) * 100
                if perc < 0.1: return f"{perc:.3f}%"
                elif perc < 1: return f"{perc:.2f}%"
                else: return f"{perc:.1f}%"

            cb2.ax.yaxis.set_major_formatter(mtick.FuncFormatter(fmt_log_perc2))
            cb2.set_label("Density (% of the densest cell)", fontsize=10)
            existing_ticks2 = [t for t in cb2.get_ticks() if 1 <= t <= vmax2_global]
            cb2.set_ticks(sorted(set(existing_ticks2) | {vmax2_global}))

            ba_out2 = os.path.join(outdir, "cohort_bland_altman_worst_subjects.png")
            fig2.savefig(ba_out2, dpi=180, bbox_inches="tight")
            print(f"\nBland-Altman plot with the 5 worst subjects of each panel: {ba_out2}")

    # ── per-REGION CSV: which segmentations disagree most ──────────────────────
    from collections import defaultdict
    region_pairs_np = defaultdict(list)
    region_pairs_pv = defaultdict(list)
    for _, r, a, o in all_nopvc:
        region_pairs_np[r].append((a, o))
    for _, r, a, o in all_pvc:
        region_pairs_pv[r].append((a, o))

    per_region = []
    all_regions = set(region_pairs_np) | set(region_pairs_pv)
    for r in all_regions:
        np_r = region_pairs_np.get(r, [])
        pv_r = region_pairs_pv.get(r, [])
        rng_np_r = rng_per_region_np.get(r)
        rng_pv_r = rng_per_region_pv.get(r)

        mape_np_r, _  = mape(np_r)
        mape_pv_r, _  = mape(pv_r)
        nrmse_np_r, _ = nrmse(np_r, rng_override=rng_np_r)
        nrmse_pv_r, _ = nrmse(pv_r, rng_override=rng_pv_r)

        mape_np_mean, mape_np_sd, _ = mape_stats(np_r)
        mape_pv_mean, mape_pv_sd, _ = mape_stats(pv_r)
        nrmse_np_mean, nrmse_np_sd, _ = nrmse_stats(np_r, rng_np_r)
        nrmse_pv_mean, nrmse_pv_sd, _ = nrmse_stats(pv_r, rng_pv_r)

        icc_np_r = icc_2_1(np_r)
        icc_pv_r = icc_2_1(pv_r)

        per_region.append({
            "region": r,
            "n_nopvc": len(np_r), "mape_nopvc": mape_np_r, "nrmse_nopvc": nrmse_np_r,
            "mape_nopvc_mean": mape_np_mean, "mape_nopvc_sd": mape_np_sd,
            "nrmse_nopvc_mean": nrmse_np_mean, "nrmse_nopvc_sd": nrmse_np_sd,
            "icc_nopvc": icc_np_r,
            "n_pvc":   len(pv_r), "mape_pvc":   mape_pv_r, "nrmse_pvc":   nrmse_pv_r,
            "mape_pvc_mean": mape_pv_mean, "mape_pvc_sd": mape_pv_sd,
            "nrmse_pvc_mean": nrmse_pv_mean, "nrmse_pvc_sd": nrmse_pv_sd,
            "icc_pvc": icc_pv_r,
        })

    per_region_sorted = sorted(
        per_region,
        key=lambda r: (r["mape_pvc"] if r["mape_pvc"] == r["mape_pvc"] else -1),
        reverse=True,
    )

    if args.csv_regions and per_region_sorted:
        import csv
        with open(args.csv_regions, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=[
                "region", "n_nopvc", "mape_nopvc", "nrmse_nopvc",
                "mape_nopvc_mean", "mape_nopvc_sd",
                "nrmse_nopvc_mean", "nrmse_nopvc_sd", "icc_nopvc",
                "n_pvc", "mape_pvc", "nrmse_pvc",
                "mape_pvc_mean", "mape_pvc_sd",
                "nrmse_pvc_mean", "nrmse_pvc_sd", "icc_pvc",
            ])
            w.writeheader()
            for row in per_region_sorted:
                w.writerow(row)

    # ── extra density plots for SUVR (no-PVC and PVC) ──────────────────────────
    if len(np_pairs) > 0 and len(pv_pairs) > 0:
        import matplotlib.pyplot as plt
        fig_dens, (ax_d1, ax_d2) = plt.subplots(1, 2, figsize=(14, 6))

        def _plot_density(ax, pairs, title):
            arr = np.array([(p[2], p[3]) for p in pairs], dtype=float)
            a4 = arr[:, 0]
            ours = arr[:, 1]
            ax.hist(a4, bins=50, alpha=0.5, density=True, label="A4 Reference", color="#888888")
            ax.hist(ours, bins=50, alpha=0.5, density=True, label="Ours (Pipeline)", color="#2ca02c")

            ax.set_title(title, fontsize=12, fontweight="bold")
            ax.set_xlabel("SUVR", fontsize=11)
            ax.set_ylabel("Density", fontsize=11)
            ax.grid(alpha=0.3)
            ax.legend()

        _plot_density(ax_d1, all_nopvc, "SUVR no-PVC density")
        _plot_density(ax_d2, all_pvc, "SUVR PVC density")

        dens_out = os.path.join(outdir, "cohort_suvr_density.png")
        fig_dens.tight_layout()
        fig_dens.savefig(dens_out, dpi=180, facecolor="white")
        print(f"\nExtra SUVR density plot saved: {dens_out}")


    # ── remaining 4-way metrics (mean, volume, NVoxels) ────────────────────────
    def _global_stats(pairs_raw):
        pairs = [(a, o) for (_, _, a, o) in pairs_raw]
        m, n = mape(pairs)
        r, _ = nrmse(pairs)
        b, lo, hi = bland_altman(pairs)
        return {"n": n, "mape": m, "nrmse": r, "bias": b, "loa_lo": lo, "loa_hi": hi}

    other_metrics = {
        "mean_nopvc": _global_stats(all_mean),
        "mean_pvc":   _global_stats(all_pvc_mean),
        "volume":     _global_stats(all_vol),
        "nvoxels":    _global_stats(all_nvox),
    }
    csv_other = os.path.join(outdir, "cohort_other_metrics.csv")
    with open(csv_other, "w", newline="") as f:
        import csv as _csv
        w = _csv.DictWriter(f, fieldnames=[
            "metric", "n", "mape", "nrmse", "bias", "loa_lo", "loa_hi"])
        w.writeheader()
        for name, stats in other_metrics.items():
            w.writerow({"metric": name, **stats})

    # ── optional dump of the raw pairs (for auditing) ──────────────────────────
    if args.csv:
        import csv
        with open(args.csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["series", "subject", "region", "a4_ref", "ours"])
            for subj, r, a, o in all_nopvc:
                w.writerow(["no-PVC", subj, r, a, o])
            for subj, r, a, o in all_pvc:
                w.writerow(["PVC", subj, r, a, o])


if __name__ == "__main__":
    main()