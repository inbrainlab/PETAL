#!/usr/bin/env python3
"""
density_meta_temporal_regions.py -- KDE density plot of SUVR values for
the 6 regions that compose meta_temporal (Jack et al. 2017) PLUS the
meta_temporal composite itself, comparing A4/LEADS (solid line) against
our pipeline (dashed line). One curve per region/composite, colored,
with MAPE annotated in the legend.

This is a density plot of the SUVR VALUES themselves (distribution
shape), not a Bland-Altman error plot -- different purpose, no hexbin,
no agreement limits.

Reads the --csv_raw output of compare_tau_composite_a4.py (columns:
subject, composite_region, suvr_a4, suvr_ours) or the --csv_raw_composite
output of compare_fdg_leads.py (columns: subject, composite_region,
leads_ref, ours) -- column names are auto-detected.

Usage:
    python3 density_meta_temporal_regions.py \
        --csv_in cohort_tau_composite_values.csv \
        --out density_meta_temporal_tau.png \
        --title "SUVR Density -- Tau: A4 vs This Work"
"""

import argparse
import csv
import math

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import gaussian_kde

# Display names (6 regions + the composite, in plotting order)
DISPLAY_NAMES = {
    "[region] Amygdala": "Amygdala",
    "[region] entorhinal": "Entorhinal",
    "[region] fusiform": "Fusiform",
    "[region] inferiortemporal": "Inferior temporal",
    "[region] middletemporal": "Middle temporal",
    "[region] parahippocampal": "Parahippocampal",
    "meta_temporal": "Meta-temporal (composite)",
}
ORDER = ["[region] Amygdala", "[region] entorhinal", "[region] fusiform",
         "[region] inferiortemporal", "[region] middletemporal",
         "[region] parahippocampal", "meta_temporal"]
COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#000000"]


def _to_float(raw):
    if raw in ("", None):
        return float("nan")
    try:
        v = float(raw)
        return v if math.isfinite(v) else float("nan")
    except ValueError:
        return float("nan")


def detect_columns(fieldnames):
    """Auto-detect the region / reference / ours columns, supporting both
    input formats (Tau: suvr_a4/suvr_ours; FDG: leads_ref/ours)."""
    region_col = "composite_region" if "composite_region" in fieldnames else "region"
    ref_candidates = ["suvr_a4", "leads_ref", "a4_ref"]
    ours_candidates = ["suvr_ours", "ours"]
    ref_col = next((c for c in ref_candidates if c in fieldnames), None)
    ours_col = next((c for c in ours_candidates if c in fieldnames), None)
    if ref_col is None or ours_col is None:
        raise SystemExit(f"Could not detect the reference/ours columns in {fieldnames}")
    return region_col, ref_col, ours_col


def read_data(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        region_col, ref_col, ours_col = detect_columns(reader.fieldnames)
        data = {name: {"ref": [], "ours": []} for name in ORDER}
        for row in reader:
            name = row.get(region_col)
            if name not in data:
                continue
            ref = _to_float(row.get(ref_col))
            ours = _to_float(row.get(ours_col))
            if math.isnan(ref) or math.isnan(ours):
                continue
            data[name]["ref"].append(ref)
            data[name]["ours"].append(ours)
    return data


def mape(ref, ours):
    ref, ours = np.array(ref), np.array(ours)
    errs = np.abs(ours - ref) / (np.abs(ref) + 1e-9) * 100
    return float(np.mean(errs)), float(np.std(errs, ddof=1)) if len(errs) > 1 else float("nan")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--csv_in", required=True,
                   help="--csv_raw of compare_tau_composite_a4.py or "
                        "--csv_raw_composite of compare_fdg_leads.py")
    p.add_argument("--out", default="density_meta_temporal.png")
    p.add_argument("--title", default="SUVR Density -- This Work vs Reference",
                   help="base title. With --show_n, 'n=<N>' computed from the data "
                        "is appended automatically.")
    p.add_argument("--ref_label", required=True,
                   help="name of the reference for the legend (e.g. 'A4' for Tau, "
                        "'LEADS' for FDG) -- required; no default is assumed so the "
                        "wrong name is never shown by accident.")
    p.add_argument("--pvc_status", default=None, choices=["PVC", "no-PVC", None],
                   help="for Tau: whether the data are with or without partial-volume "
                        "correction -- appended to the title. Not applicable to FDG "
                        "(omit).")
    p.add_argument("--show_n", action="store_true",
                   help="append '(n=<number of plotted subjects>)' to the title. Off by "
                        "default: if the n of this figure differs from the cohort "
                        "size reported elsewhere (e.g. because of composite-specific "
                        "exclusions), it is better to leave it out of the title and "
                        "explain it in the caption.")
    args = p.parse_args()

    data = read_data(args.csv_in)

    final_title = args.title
    if args.show_n:
        # n = number of valid subjects in meta_temporal (the series every
        # subject should have, being the main composite) -- always computed
        # from the data.
        n_subjects = len(data.get("meta_temporal", {}).get("ref", []))
        final_title += f" (n={n_subjects})"
    if args.pvc_status:
        final_title += f" -- {args.pvc_status}"

    missing = [n for n in ORDER if len(data[n]["ref"]) == 0]
    if missing:
        print(f"Warning: no data for {[DISPLAY_NAMES[n] for n in missing]} -- omitted from the plot")

    fig, ax = plt.subplots(1, 1, figsize=(11, 8))

    all_xs = []
    for n in ORDER:
        all_xs.extend(data[n]["ref"])
        all_xs.extend(data[n]["ours"])
    if not all_xs:
        raise SystemExit("No valid data in the CSV -- check --csv_in.")
    x_min, x_max = min(all_xs), max(all_xs)
    pad = (x_max - x_min) * 0.05
    x_grid = np.linspace(x_min - pad, x_max + pad, 500)

    for name, color in zip(ORDER, COLORS):
        ref = data[name]["ref"]
        ours = data[name]["ours"]
        if len(ref) < 2:
            continue

        mape_m, mape_sd = mape(ref, ours)
        label_base = DISPLAY_NAMES[name]
        mape_txt = f"MAPE {mape_m:.2f} ± {mape_sd:.2f}%" if not math.isnan(mape_sd) else f"MAPE {mape_m:.2f}%"

        kde_ref = gaussian_kde(ref)
        kde_ours = gaussian_kde(ours)
        y_ref = kde_ref(x_grid)
        y_ours = kde_ours(x_grid)

        lw = 3 if name == "meta_temporal" else 2
        ax.plot(x_grid, y_ref, color=color, lw=lw, ls="-",
                 label=f"{label_base}\n{mape_txt}")
        ax.fill_between(x_grid, y_ref, alpha=0.12, color=color)
        ax.plot(x_grid, y_ours, color=color, lw=lw, ls="--")

    # legend entries for the line style (solid/dashed)
    ax.plot([], [], color="#555555", lw=2, ls="-", label=f"{args.ref_label} Reference (solid line)")
    ax.plot([], [], color="#555555", lw=2, ls="--", label="This Work (Pipeline) (dashed line)")

    ax.set_xlabel("SUVR", fontsize=11)
    ax.set_ylabel("Density", fontsize=11)
    ax.tick_params(axis="both", labelsize=10)
    ax.set_title(final_title, fontsize=14, fontweight="bold")
    ax.legend(loc="upper right", fontsize=10, framealpha=0.95)
    ax.grid(alpha=0.3)
    ax.set_ylim(bottom=0)

    fig.tight_layout()
    fig.savefig(args.out, dpi=150, bbox_inches="tight", facecolor="white")
    print(f"Plot saved: {args.out}")


if __name__ == "__main__":
    main()
