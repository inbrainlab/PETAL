#!/usr/bin/env python3
"""
final_avid_a4_plots.py -- comparison plots for the Avid-VOI pipeline
vs A4 (all subjects present in both files), using A4's calibration
equation (Centiloid = 183.07 * SUVr - 177.26) to convert our composite
SUVr to Centiloid.

Two separate figures, with deliberately DIFFERENT metric sets:

  - SUVr composite: includes MAPE (comparable with the FDG and Tau
    comparisons, which use MAPE as their
    primary metric).

  - Centiloid: does NOT include MAPE -- Centiloid crosses zero by
    design (0 = healthy control, ~100 = typical AD level), so dividing
    by a near-zero reference value sends the percentage error to
    meaningless numbers even when the absolute difference is small
    (in practice Centiloid MAPE can reach very large values while
    NRMSE/ICC stay stable). This panel therefore uses ONLY the
    Klunk et al. 2015 metrics (bias, SD, MAE, RMSE, slope, intercept,
    R^2, ICC, verdict on the 3 formal criteria).

Outputs:
  - Two separate PNGs: one for SUVr composite, one for Centiloid.
  - One CSV with the per-subject detail.

Usage:
    python3 final_avid_a4_plots.py \
        --centiloid_results centiloid_results.csv \
        --a4 A4_PETSUVR_PRV2_26Jan2026.csv \
        --out_suvr suvr_avid_A4.png \
        --out_centiloid centiloid_avid_A4.png \
        --csv_out final_data.csv
"""

import argparse
import csv
import math

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# A4's calibration equation. It is NOT exactly the published Navitsky
# 2018 Eq 2A (183.0 / -177.0): A4 used its own, slightly different,
# recalibration on its own cohort.
CL_SLOPE_A4 = 183.07
CL_INTERCEPT_A4 = -177.26


def _to_float(raw):
    if raw in ("", None):
        return float("nan")
    try:
        v = float(raw)
        return v if math.isfinite(v) else float("nan")
    except ValueError:
        return float("nan")


def read_own(path):
    """{subject_id: ctx_suvr}, status=ok only, excluding spurious rows
    (e.g. 'results_klunk', a folder name that can leak in as a fake
    subject in some CSVs)."""
    out = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            sid = row.get("subject_id", "")
            if row.get("status") != "ok" or sid.startswith("results"):
                continue
            suvr = _to_float(row.get("ctx_suvr"))
            if not math.isnan(suvr):
                out[sid] = suvr
    return out


def read_a4(path):
    """{BID: (suvr_cer, centiloid)}, Composite_Summary rows only."""
    out = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("brain_region") != "Composite_Summary":
                continue
            suvr = _to_float(row.get("suvr_cer"))
            cl = _to_float(row.get("centiloid"))
            if not math.isnan(suvr) and not math.isnan(cl):
                out[row["BID"]] = (suvr, cl)
    return out


def compute_metrics(ref, ours, include_mape=False):
    """Returns a dict with bias/SD/MAE/RMSE/slope/intercept/R^2/ICC and
    the Klunk 2015 3-criteria verdict. If include_mape=True, also adds
    MAPE (only meaningful for SUVr, which never crosses zero --
    deliberately left out for Centiloid)."""
    ref = np.asarray(ref, dtype=float)
    ours = np.asarray(ours, dtype=float)
    diff = ours - ref

    bias = float(diff.mean())
    sd = float(diff.std(ddof=1))
    mae = float(np.abs(diff).mean())
    rmse = float(np.sqrt((diff ** 2).mean()))

    x, y = ref, ours
    x_mean, y_mean = x.mean(), y.mean()
    ss_xx = np.sum((x - x_mean) ** 2)
    slope = float(np.sum((x - x_mean) * (y - y_mean)) / ss_xx)
    intercept = float(y_mean - slope * x_mean)
    y_pred = slope * x + intercept
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - y_mean) ** 2)
    r2 = float(1 - ss_res / ss_tot) if ss_tot > 0 else float("nan")

    arr = np.column_stack([ref, ours])
    n, k = arr.shape
    grand_mean = arr.mean()
    subj_means = arr.mean(axis=1)
    method_means = arr.mean(axis=0)
    SST = np.sum((arr - grand_mean) ** 2)
    SSR = k * np.sum((subj_means - grand_mean) ** 2)
    SSC = n * np.sum((method_means - grand_mean) ** 2)
    SSE = SST - SSR - SSC
    df_r, df_e = n - 1, (n - 1) * (k - 1)
    MSR = SSR / df_r
    MSC = SSC / (k - 1)
    MSE = SSE / df_e
    denom = MSR + (k - 1) * MSE + k * (MSC - MSE) / n
    icc = float((MSR - MSE) / denom) if denom != 0 else float("nan")

    verdict = (0.98 <= slope <= 1.02) and (-2.0 <= intercept <= 2.0) and (r2 > 0.98)

    m = {
        "n": n, "bias": bias, "sd": sd, "mae": mae, "rmse": rmse,
        "slope": slope, "intercept": intercept, "r2": r2, "icc": icc,
        "passes_klunk": verdict,
    }
    if include_mape:
        mape = float(np.mean(np.abs(diff) / (np.abs(ref) + 1e-9) * 100))
        mape_sd = float(np.std(np.abs(diff) / (np.abs(ref) + 1e-9) * 100, ddof=1))
        m["mape"] = mape
        m["mape_sd"] = mape_sd
    return m


def panel_scatter(ax, ref, ours, title, unit, color, m, show_mape=False,
                   ylabel_override=None, equation_in_legend=False,
                   subject_label_suffix="", xlabel_override=None):
    ax.scatter(ref, ours, s=28, alpha=0.6, color=color, edgecolors="none",
               label=f"Subjects (n={m['n']}){subject_label_suffix}")

    data_range = max(ref.max(), ours.max()) - min(ref.min(), ours.min())
    pad = data_range * 0.08
    lims = [min(ref.min(), ours.min()) - pad, max(ref.max(), ours.max()) + pad]
    ax.plot(lims, lims, ls="--", color="#898781", lw=1.3, label="Identity (y=x)")

    x_line = np.array(lims)
    y_line = m["slope"] * x_line + m["intercept"]
    if equation_in_legend:
        # regression label carries the full equation + R^2, matching the
        # Klunk-GAAIN validation plot style, instead of a separate stats box
        reg_label = f"y={m['slope']:.3f}x+{m['intercept']:.2f}  R²={m['r2']:.4f}"
    else:
        reg_label = "Regression"
    ax.plot(x_line, y_line, color="#e34948", lw=2, label=reg_label)

    ax.set_xlim(lims)
    ax.set_ylim(lims)
    ax.set_xlabel(xlabel_override if xlabel_override else f"A4 ({unit}, reference)", fontsize=11)
    ax.set_ylabel(ylabel_override if ylabel_override else f"Ours ({unit})", fontsize=11)
    ax.tick_params(axis="both", labelsize=10)
    if title:
        ax.set_title(title, fontsize=12, fontweight="bold")
    ax.grid(alpha=0.3)
    ax.legend(loc="lower right", fontsize=10, framealpha=0.9)
    ax.set_aspect("equal", adjustable="box")

    if not equation_in_legend:
        # stats textbox -- only for panels that don't fold the equation
        # into the legend (i.e. the SUVr panel keeps this)
        if show_mape:
            text = (
                f"bias={m['bias']:+.3f}   SD={m['sd']:.3f}\n"
                f"MAE={m['mae']:.3f}   RMSE={m['rmse']:.3f}\n"
                f"MAPE={m['mape']:.2f}% ± {m['mape_sd']:.2f}%\n"
                f"slope={m['slope']:.3f}   intercept={m['intercept']:+.3f}\n"
                f"R²={m['r2']:.3f}   ICC={m['icc']:.3f}"
            )
        else:
            verdict_txt = "PASSES" if m["passes_klunk"] else "DOES NOT PASS"
            text = (
                f"bias={m['bias']:+.2f}   SD={m['sd']:.2f}\n"
                f"MAE={m['mae']:.2f}   RMSE={m['rmse']:.2f}\n"
                f"slope={m['slope']:.3f}   intercept={m['intercept']:+.2f}\n"
                f"R²={m['r2']:.3f}   ICC={m['icc']:.3f}\n"
                f"Klunk 2015 (3 criteria): {verdict_txt}"
            )
        ax.text(0.02, 0.98, text, transform=ax.transAxes, fontsize=10,
                 va="top", ha="left", family="monospace",
                 bbox=dict(boxstyle="round", facecolor="white", alpha=0.9, edgecolor="#ccc"))


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--centiloid_results", required=True)
    p.add_argument("--a4", required=True)
    p.add_argument("--out_suvr", default="suvr_avid_A4.png")
    p.add_argument("--out_centiloid", default="centiloid_avid_A4.png")
    p.add_argument("--csv_out", default="final_data.csv")
    args = p.parse_args()

    own = read_own(args.centiloid_results)
    a4 = read_a4(args.a4)
    common = sorted(set(own) & set(a4))
    print(f"{len(own)} own subjects (status=ok)")
    print(f"{len(common)} subjects in common with A4\n")
    if not common:
        raise SystemExit("No subjects in common -- check subject_id/BID.")

    suvr_a4 = np.array([a4[s][0] for s in common])
    cl_a4 = np.array([a4[s][1] for s in common])
    suvr_ours = np.array([own[s] for s in common])
    cl_ours = CL_SLOPE_A4 * suvr_ours + CL_INTERCEPT_A4

    with open(args.csv_out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["subject_id", "suvr_a4", "suvr_ours", "centiloid_a4", "centiloid_ours"])
        for i, sid in enumerate(common):
            w.writerow([sid, suvr_a4[i], suvr_ours[i], cl_a4[i], cl_ours[i]])
    print(f"Per-subject CSV: {args.csv_out}\n")

    m_suvr = compute_metrics(suvr_a4, suvr_ours, include_mape=True)
    m_cl = compute_metrics(cl_a4, cl_ours, include_mape=False)

    print(f"-- SUVr composite (n={m_suvr['n']}) --")
    print(f"   bias={m_suvr['bias']:+.3f}  SD={m_suvr['sd']:.3f}  "
          f"MAE={m_suvr['mae']:.3f}  RMSE={m_suvr['rmse']:.3f}")
    print(f"   MAPE={m_suvr['mape']:.2f}% ± {m_suvr['mape_sd']:.2f}% (SD)")
    print(f"   slope={m_suvr['slope']:.4f}  intercept={m_suvr['intercept']:+.3f}  "
          f"R²={m_suvr['r2']:.4f}  ICC={m_suvr['icc']:.3f}\n")

    print(f"-- Centiloid (n={m_cl['n']}) --")
    print(f"   bias={m_cl['bias']:+.3f}  SD={m_cl['sd']:.3f}  "
          f"MAE={m_cl['mae']:.3f}  RMSE={m_cl['rmse']:.3f}")
    print(f"   slope={m_cl['slope']:.4f}  intercept={m_cl['intercept']:+.3f}  "
          f"R²={m_cl['r2']:.4f}  ICC={m_cl['icc']:.3f}")
    print(f"   Klunk 2015 (3 criteria): {'PASSES' if m_cl['passes_klunk'] else 'DOES NOT PASS'}\n")

    n = len(common)

    # -- Figure 1: SUVr composite (standalone) -----------------------------
    fig_suvr, ax_suvr = plt.subplots(1, 1, figsize=(6.5, 6.2))
    panel_scatter(ax_suvr, suvr_a4, suvr_ours, "", "SUVr",
                  "#534AB7", m_suvr, show_mape=True)
    fig_suvr.suptitle(f"Avid pipeline vs A4 — SUVr composite (n={n})",
                       fontsize=13, fontweight="bold")
    fig_suvr.tight_layout(rect=[0, 0, 1, 0.94])
    fig_suvr.savefig(args.out_suvr, dpi=150, bbox_inches="tight", facecolor="white")
    print(f"SUVr plot saved: {args.out_suvr}")

    # -- Figure 2: Centiloid (standalone) -----------------------------------
    fig_cl, ax_cl = plt.subplots(1, 1, figsize=(6.5, 6.2))
    panel_scatter(ax_cl, cl_a4, cl_ours, "", "CL",
                  "#2ecc71", m_cl, show_mape=False,
                  ylabel_override="This Work", equation_in_legend=True,
                  xlabel_override="Published A4")
    fig_cl.suptitle(f"Avid pipeline vs A4 — Centiloid (n={n})",
                     fontsize=13, fontweight="bold")
    fig_cl.tight_layout(rect=[0, 0, 1, 0.94])
    fig_cl.savefig(args.out_centiloid, dpi=150, bbox_inches="tight", facecolor="white")
    print(f"Centiloid plot saved: {args.out_centiloid}")


if __name__ == "__main__":
    main()
