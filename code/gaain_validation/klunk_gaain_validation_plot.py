#!/usr/bin/env python3
"""
klunk_gaain_validation_plot.py -- scatter plot of the Klunk-VOI pipeline
Centiloid versus the published GAAIN Centiloid values (Centiloid Project
validation), with a linear regression and the three Klunk 2015 criteria
(slope 0.98-1.02, intercept within +-2 CL, R^2 > 0.98).

Reads:
  - centiloid_results_klunk.csv: our own pipeline output
    (subject_id, centiloid_pipeline, status).
  - Avid_Centiloid_standard_method.xlsx: GAAIN reference (PatientID,
    Cohort, published Florbetapir Centiloid in column 'Florbetapir '
    under the 'Centiloid' header group).

Usage:
    python3 klunk_gaain_validation_plot.py \
        --centiloid_results centiloid_results_klunk.csv \
        --gaain_xlsx Avid_Centiloid_standard_method.xlsx \
        --out klunk_gaain_validation.png
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
import csv
import math

import numpy as np
import openpyxl
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

COHORT_COLORS = {
    "YHC": "#3498db",
    "AD": "#e74c3c",
    "NC": "#2ecc71",
    "MCI": "#f39c12",
    "Clinical AD": "#9b59b6",
    "Possible AD": "#1abc9c",
    "At risk elderly subject": "#7f8c8d",
}


def _to_float(raw):
    if raw in ("", None):
        return float("nan")
    try:
        v = float(raw)
        return v if math.isfinite(v) else float("nan")
    except ValueError:
        return float("nan")


def read_own(path):
    """{subject_id (str): centiloid_pipeline}, status=ok only."""
    out = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("status") != "ok":
                continue
            cl = _to_float(row.get("centiloid_pipeline"))
            if not math.isnan(cl):
                out[row["subject_id"].strip()] = cl
    return out


def read_gaain(path):
    """{subject_id (str): (cohort, published_centiloid_florbetapir)}."""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(min_row=3, values_only=True))
    out = {}
    for r in rows:
        if r[0] is None:
            continue
        sid = str(int(r[0])) if isinstance(r[0], (int, float)) else str(r[0]).strip()
        cohort = (r[2] or "").strip()
        cl_published = r[8]
        if cl_published is None:
            continue
        out[sid] = (cohort, float(cl_published))
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--centiloid_results", required=True)
    p.add_argument("--gaain_xlsx", required=True)
    p.add_argument("--out", default="klunk_gaain_validation.png")
    args = p.parse_args()

    own = read_own(args.centiloid_results)
    gaain = read_gaain(args.gaain_xlsx)
    common = sorted(set(own) & set(gaain))
    print(f"{len(own)} own subjects (status=ok)")
    print(f"{len(gaain)} subjects in the GAAIN reference file")
    print(f"{len(common)} subjects in common\n")
    if not common:
        raise SystemExit("No subjects in common -- check subject_id formatting.")

    published = np.array([gaain[s][1] for s in common])
    ours = np.array([own[s] for s in common])
    cohorts = [gaain[s][0] for s in common]

    # -- linear regression: ours = slope*published + intercept ------------
    x, y = published, ours
    x_mean, y_mean = x.mean(), y.mean()
    ss_xx = np.sum((x - x_mean) ** 2)
    slope = float(np.sum((x - x_mean) * (y - y_mean)) / ss_xx)
    intercept = float(y_mean - slope * x_mean)
    y_pred = slope * x + intercept
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - y_mean) ** 2)
    r2 = float(1 - ss_res / ss_tot) if ss_tot > 0 else float("nan")

    slope_ok = 0.98 <= slope <= 1.02
    intercept_ok = -2.0 <= intercept <= 2.0
    r2_ok = r2 > 0.98

    print(f"Slope: {slope:.4f}  {'OK' if slope_ok else 'FAIL'}")
    print(f"Intercept: {intercept:+.4f}  {'OK' if intercept_ok else 'FAIL'}")
    print(f"R2: {r2:.4f}  {'OK' if r2_ok else 'FAIL'}")
    print(f"n valid: {len(common)}/{len(gaain)}")

    fig, ax = plt.subplots(1, 1, figsize=(8, 8))

    for cohort in sorted(set(cohorts)):
        idx = [i for i, c in enumerate(cohorts) if c == cohort]
        color = COHORT_COLORS.get(cohort, "#333333")
        ax.scatter(published[idx], ours[idx], s=55, alpha=0.85, color=color,
                   edgecolors="none", label=cohort)

    lims = [min(published.min(), ours.min()) - 5, max(published.max(), ours.max()) + 5]
    ax.plot(lims, lims, ls="--", color="#999999", lw=1.3, label="Identity")

    x_line = np.array(lims)
    y_line = slope * x_line + intercept
    ax.plot(x_line, y_line, color="#c2185b", lw=2.2,
             label=f"y={slope:.3f}x+{intercept:.2f}  R²={r2:.4f}")

    ax.set_xlim(lims)
    ax.set_ylim(lims)
    ax.set_xlabel("Published Centiloid", fontsize=11)
    ax.set_ylabel("Centiloid - our pipeline", fontsize=11)
    ax.tick_params(axis="both", labelsize=10)
    ax.set_title("Centiloid Project Validation", fontsize=13, fontweight="bold")
    ax.grid(alpha=0.3)
    ax.legend(loc="lower right", fontsize=10, framealpha=0.9)
    ax.set_aspect("equal", adjustable="box")

    stats_text = (
        f"Slope:      {slope:.4f}   {'OK' if slope_ok else 'FAIL'}\n"
        f"Intercept:  {intercept:+.4f}  {'OK' if intercept_ok else 'FAIL'}\n"
        f"R2:         {r2:.4f}   {'OK' if r2_ok else 'FAIL'}\n"
        f"n valid: {len(common)}/{len(gaain)}"
    )
    ax.text(0.02, 0.98, stats_text, transform=ax.transAxes, fontsize=10,
             va="top", ha="left", family="monospace",
             bbox=dict(boxstyle="round", facecolor="white", alpha=0.9, edgecolor="#ccc"))

    fig.tight_layout()
    fig.savefig(args.out, dpi=150, bbox_inches="tight", facecolor="white")
    print(f"\nPlot saved: {args.out}")


if __name__ == "__main__":
    main()
