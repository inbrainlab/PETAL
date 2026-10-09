#!/usr/bin/env python3
"""
cohort_per_region_plot.py -- whole-cohort figure built from the raw
pairs dump written by nrmse_cohort.py (--csv: columns
series,subject,region,a4_ref,ours).

The individual MAPE of every (subject, region) pair is computed and shown
as a horizontal BOXPLOT per region (median, interquartile range, whiskers,
outliers), one panel for no-PVC and one for PVC. A boxplot is preferred
over mean +- SD because MAPE is a non-negative, long-tailed metric: a
mean +- SD summary can imply impossible negative values (whiskers
crossing 0), whereas the boxplot makes no symmetry assumption and shows
the real distribution across subjects.

The number of subjects (n) is computed from the data and shown in the
titles.

Usage:
    python3 cohort_per_region_plot.py \
        --csv_raw cohort_nrmse_pairs.csv \
        --top_n 15 \
        --out cohort_per_region.png
"""

import argparse
import csv
import math
from collections import defaultdict

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

COLOR_MAPE_NP = "#534AB7"
COLOR_MAPE_PV = "#D4537E"


def _to_float(raw):
    if raw in ("", None):
        return float("nan")
    try:
        v = float(raw)
        return v if math.isfinite(v) else float("nan")
    except ValueError:
        return float("nan")


def read_raw_pairs(path):
    """Read the --csv of nrmse_cohort.py (series,subject,region,a4_ref,ours).
    Return ({series: {region: [individual_mape, ...]}}, {series: set(subjects)}):
    one MAPE per (subject, region), not aggregated."""
    mape_by_series_region = defaultdict(lambda: defaultdict(list))
    subjects_by_series = defaultdict(set)
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            a4 = _to_float(row["a4_ref"])
            ours = _to_float(row["ours"])
            if math.isnan(a4) or math.isnan(ours):
                continue
            mape_val = abs(ours - a4) / (abs(a4) + 1e-9) * 100
            mape_by_series_region[row["series"]][row["region"]].append(mape_val)
            subjects_by_series[row["series"]].add(row["subject"])
    return mape_by_series_region, subjects_by_series


def draw_panel(ax, mape_by_region, regions, color, title):
    data = [mape_by_region[r] for r in regions]
    ax.boxplot(data, vert=False, positions=np.arange(len(regions)),
               widths=0.6, patch_artist=True, showfliers=True,
               flierprops=dict(marker="o", markersize=2, alpha=0.4,
                                markerfacecolor=color, markeredgecolor="none"),
               medianprops=dict(color="#222222", linewidth=1.5),
               boxprops=dict(facecolor=color, alpha=0.75))
    ax.set_yticks(np.arange(len(regions)))
    ax.set_yticklabels(regions, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Per-subject MAPE (%) -- median, IQR, whiskers")
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.axvline(0, color="#888", lw=0.8)
    ax.grid(axis="x", alpha=0.3)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--csv_raw", required=True,
                   help="raw pairs dump (--csv of nrmse_cohort.py)")
    p.add_argument("--top_n", type=int, default=15,
                   help="number of regions shown per panel (default: 15)")
    p.add_argument("--exclude", nargs="+", default=["White_Matter", "Cerebellum_Cortex"],
                   help="substrings of region names to exclude (default: White_Matter, "
                        "Cerebellum_Cortex -- the latter is the reference region used "
                        "to normalise SUVR, not a result region)")
    p.add_argument("--out", default="cohort_per_region.png")
    args = p.parse_args()

    mape_raw, subjects = read_raw_pairs(args.csv_raw)

    def excluded(region):
        return any(pat.lower() in region.lower() for pat in args.exclude)

    mape_np = {r: v for r, v in mape_raw.get("no-PVC", {}).items() if not excluded(r)}
    mape_pv = {r: v for r, v in mape_raw.get("PVC", {}).items() if not excluded(r)}
    if not mape_np and not mape_pv:
        raise SystemExit(f"'{args.csv_raw}' has no valid 'no-PVC'/'PVC' rows.")

    top_n = args.top_n
    n_np = len(subjects.get("no-PVC", ()))
    n_pv = len(subjects.get("PVC", ()))
    n_all = len(subjects.get("no-PVC", set()) | subjects.get("PVC", set()))

    # Top-N regions by DESCENDING MEDIAN (more robust than the mean for
    # choosing which regions to show; consistent with the boxplot).
    regions_np = sorted(mape_np, key=lambda r: -np.median(mape_np[r]))[:top_n]
    regions_pv = sorted(mape_pv, key=lambda r: -np.median(mape_pv[r]))[:top_n]

    height = 0.42 * top_n + 2.2
    fig, (ax_np, ax_pv) = plt.subplots(1, 2, figsize=(5.3 * 2, height))

    draw_panel(ax_np, mape_np, regions_np, COLOR_MAPE_NP, f"no-PVC (n={n_np})")
    draw_panel(ax_pv, mape_pv, regions_pv, COLOR_MAPE_PV, f"PVC (n={n_pv})")

    fig.suptitle(f"Full cohort (n={n_all}) — pipeline vs A4 — "
                 "per-subject MAPE (boxplot)",
                 fontsize=12, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(args.out, dpi=150, bbox_inches="tight", facecolor="white")
    print(f"Plot saved: {args.out}")


if __name__ == "__main__":
    main()
