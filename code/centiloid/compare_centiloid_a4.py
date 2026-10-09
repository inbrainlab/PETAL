#!/usr/bin/env python3
"""
compare_centiloid_a4.py -- compare the Centiloid values of our pipeline
against the A4 reference (Florbetapir, 6-region Avid VOIs), using the
same statistical criteria as the Tau/FDG comparisons: MAPE as the primary
metric, NRMSE (population range) as secondary, and ICC(2,1) per subject
versus A4 (here the "region" is the aggregate Composite_Summary level;
there is no regional breakdown as in Tau/FDG).

Note on the Centiloid calculation: this script ignores any
'centiloid_pipeline' column in the pipeline CSV and recomputes Centiloid
from 'ctx_suvr' (the raw composite SUVR, which does not depend on any
calibration equation) with the Eq 2A-type calibration that corresponds to
the 6 Avid VOIs (Joshi 2015; Navitsky 2018), in the form used by A4 (see
CL_SLOPE_AVID / CL_INTERCEPT_AVID). Applying the Klunk Eq 2B
(175.18 * SUVr - 182.24), which belongs to the Klunk VOIs, to SUVR values
computed with the Avid VOIs would introduce a systematic offset.

Usage:
    python3 compare_centiloid_a4.py \
        --own centiloid_results.csv \
        --a4  A4_PETSUVR_PRV2_26Jan2026.csv \
        --csv_out centiloid_comparison.csv
"""

import argparse
import csv
import math

import numpy as np

# Calibration used by A4 for the Avid VOIs. It differs very slightly from
# the published Navitsky 2018 Eq 2A (183.0 / -177.0), which yields a small
# systematic offset (about -0.18 CL) relative to A4's own Centiloid values.
CL_SLOPE_AVID = 183.07
CL_INTERCEPT_AVID = -177.26


def recompute_centiloid_avid(suvr):
    return CL_SLOPE_AVID * suvr + CL_INTERCEPT_AVID


def read_own(path):
    """Return {subject_id: ctx_suvr} for rows with status=ok only."""
    out = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("status") != "ok":
                continue
            try:
                out[row["subject_id"]] = float(row["ctx_suvr"])
            except (ValueError, KeyError):
                continue
    return out


def read_a4(path):
    """Return {BID: (suvr_cer, centiloid)} for brain_region=Composite_Summary only."""
    out = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("brain_region") != "Composite_Summary":
                continue
            try:
                out[row["BID"]] = (float(row["suvr_cer"]), float(row["centiloid"]))
            except (ValueError, KeyError):
                continue
    return out


# ─────────────────────────── metrics ───────────────────────────────────────

def mape_stats(pairs):
    if not pairs:
        return float("nan"), float("nan"), 0
    arr = np.array(pairs, dtype=float)
    ref, ours = arr[:, 0], arr[:, 1]
    errs = np.abs(ours - ref) / (np.abs(ref) + 1e-9) * 100
    mean = float(np.mean(errs))
    sd = float(np.std(errs, ddof=1)) if len(errs) > 1 else float("nan")
    return mean, sd, len(pairs)


def nrmse_stats(pairs):
    """Normalised by the population range of the REFERENCE (A4) over the
    subjects actually compared (the denominator is a property of the
    reference, not of our values)."""
    if not pairs:
        return float("nan"), float("nan"), 0
    arr = np.array(pairs, dtype=float)
    ref, ours = arr[:, 0], arr[:, 1]
    rng = ref.max() - ref.min()
    if rng <= 0:
        return float("nan"), float("nan"), 0
    errs = (ours - ref) / rng * 100
    mean = float(np.mean(errs))
    sd = float(np.std(errs, ddof=1)) if len(errs) > 1 else float("nan")
    return mean, sd, len(pairs)


def icc_2_1(pairs):
    """ICC(2,1): two-way random effects, absolute agreement, single rater
    (Shrout & Fleiss, 1979)."""
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


def klunk_linear_regression(pairs):
    """pairs = [(a4_cl, our_cl), ...]. Linear regression
    our_cl = slope * a4_cl + intercept (our Centiloid as a function of the
    A4 one, the same convention as the GAAIN validation).
    Returns (slope, intercept, r2, verdict) where verdict holds the three
    Klunk 2015 criteria: slope in [0.98, 1.02], intercept in [-2, +2] CL,
    R^2 > 0.98."""
    arr = np.array(pairs, dtype=float)
    x, y = arr[:, 0], arr[:, 1]  # x = A4 (reference), y = ours
    n = len(x)
    if n < 2:
        return float("nan"), float("nan"), float("nan"), {}

    x_mean, y_mean = x.mean(), y.mean()
    ss_xx = np.sum((x - x_mean) ** 2)
    ss_xy = np.sum((x - x_mean) * (y - y_mean))
    if ss_xx == 0:
        return float("nan"), float("nan"), float("nan"), {}
    slope = ss_xy / ss_xx
    intercept = y_mean - slope * x_mean

    y_pred = slope * x + intercept
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - y_mean) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    verdict = {
        "slope_ok": 0.98 <= slope <= 1.02,
        "intercept_ok": -2.0 <= intercept <= 2.0,
        "r2_ok": r2 > 0.98,
    }
    verdict["passes_all_3"] = all(verdict.values())
    return slope, intercept, r2, verdict


def print_klunk_verdict(pairs, n):
    slope, intercept, r2, verdict = klunk_linear_regression(pairs)
    print(f"── Linear regression (our Centiloid = slope × A4 + intercept), n={n} ──")
    print(f"   slope     = {slope:.4f}   {'✓' if verdict.get('slope_ok') else '✗'} (criterion: 0.98–1.02)")
    print(f"   intercept = {intercept:+.2f} CL {'✓' if verdict.get('intercept_ok') else '✗'} (criterion: ±2 CL)")
    print(f"   R²        = {r2:.4f}   {'✓' if verdict.get('r2_ok') else '✗'} (criterion: >0.98)")
    if verdict.get("passes_all_3"):
        print("   → PASSES all 3 Klunk 2015 criteria.")
    else:
        print("   → does NOT pass all 3 Klunk 2015 criteria.")
    print()


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--own", required=True, help="centiloid_results.csv (our pipeline)")
    p.add_argument("--a4", required=True, help="A4_PETSUVR_PRV2_*.csv (reference)")
    p.add_argument("--csv_out", default="centiloid_comparison.csv")
    args = p.parse_args()

    own = read_own(args.own)
    a4 = read_a4(args.a4)
    print(f"{len(own)} own subjects with status=ok")
    print(f"{len(a4)} A4 subjects with Composite_Summary")

    common = sorted(set(own) & set(a4))
    print(f"{len(common)} subjects on both sides\n")
    if not common:
        raise SystemExit("No subjects in common -- check the subject_id/BID format.")

    rows = []
    suvr_pairs = []        # (a4_suvr, our_suvr)
    centiloid_pairs = []   # (a4_cl, our_recomputed_cl)
    for sid in common:
        suvr_ours = own[sid]
        suvr_a4, cl_a4 = a4[sid]
        cl_ours = recompute_centiloid_avid(suvr_ours)
        suvr_pairs.append((suvr_a4, suvr_ours))
        centiloid_pairs.append((cl_a4, cl_ours))
        rows.append({
            "subject_id": sid,
            "suvr_a4": suvr_a4, "suvr_ours": suvr_ours,
            "centiloid_a4": cl_a4, "centiloid_ours_recomputed": cl_ours,
            "centiloid_diff": cl_ours - cl_a4,
        })

    with open(args.csv_out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"Per-subject detail CSV: {args.csv_out}\n")

    for label, pairs in (("Composite SUVR", suvr_pairs),
                         ("Centiloid (recomputed with Eq 2A)", centiloid_pairs)):
        mape_m, mape_sd, n = mape_stats(pairs)
        nrmse_m, nrmse_sd, _ = nrmse_stats(pairs)
        icc = icc_2_1(pairs)
        arr = np.array(pairs, dtype=float)
        diffs = arr[:, 1] - arr[:, 0]
        bias = float(np.mean(diffs))
        sd_diff = float(np.std(diffs, ddof=1)) if len(diffs) > 1 else float("nan")
        mae = float(np.mean(np.abs(diffs)))
        rmse = float(np.sqrt(np.mean(diffs ** 2)))
        print(f"── {label} (n={n}) ──")
        print(f"   Native scale: bias={bias:+.2f}  SD={sd_diff:.2f}  MAE={mae:.2f}  RMSE={rmse:.2f}")
        print(f"   MAPE:  {mape_m:.2f}% ± {mape_sd:.2f}% (SD)  [caution: distorted if the reference crosses zero]")
        print(f"   NRMSE: {nrmse_m:+.2f}% ± {nrmse_sd:.2f}% (SD, A4 population range)")
        print(f"   ICC(2,1): {icc:.3f}")
        print()

    print("=" * 70)
    print_klunk_verdict(centiloid_pairs, len(centiloid_pairs))
    print("=" * 70)


if __name__ == "__main__":
    main()
