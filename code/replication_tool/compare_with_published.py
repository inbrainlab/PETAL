#!/usr/bin/env python3
"""
compare_with_published.py -- compare YOUR values with the values published in this repository
(data/). The reference data (A4 / LEADS) are neither distributed nor used: the comparison is
against the values of this work.

--table format (CSV):
  centiloid : subject_id + suvr_<region> columns with the SAME names as data/centiloid_avid.csv
              (optional: ctx_suvr, centiloid_pipeline). If ctx_suvr is missing and the six regions
              are present, it is computed as their simple mean.
  tau / fdg : subject, composite_region and a value column (--value_col).
              evaluate_subject.py writes this file as values_<type>.csv (value column: "value").

Definitions (x = published value, y = yours; difference = y - x):
  bias = mean(y-x) | sd = standard deviation of (y-x) | mae = mean|y-x| | rmse
  mape = mean(|y-x|/|x|)*100 | mape_sd = standard deviation of that percentage error
  slope, intercept, r2 = regression of y on x | icc = ICC(2,1) (two-way random effects,
  absolute agreement, single measurement; Shrout & Fleiss 1979).
The paper's figures (this work vs the reference) are shown alongside as context only.
Nothing is declared "replicated" or "not replicated": there is no threshold.

Examples:
  python3 compare_with_published.py --package /path/to/repo --type centiloid --table my_values.csv
  python3 compare_with_published.py --package /path/to/repo --type tau --table my_tau.csv --value_col my_suvr
"""
import argparse
import csv
import math
import os

import numpy as np
from scipy import stats

from interpretation_note import print_note

COLS = ["n", "bias", "sd", "mae", "rmse", "mape", "mape_sd", "slope", "intercept", "r2", "icc"]
SIX_VOIS = ["suvr_lanterior_cingulate_2", "suvr_llposterior_cingulate_2", "suvr_lnew_parietal",
            "suvr_lprecuneus_gm", "suvr_new_temporal_2", "suvr_xlaal_frontal_med_orb"]


def icc_2_1(data):
    """Shrout & Fleiss ICC(2,1). data: matrix of n subjects x k raters."""
    d = np.asarray(data, float)
    n, k = d.shape
    gm = d.mean()
    msr = k * ((d.mean(axis=1) - gm) ** 2).sum() / (n - 1)
    msc = n * ((d.mean(axis=0) - gm) ** 2).sum() / (k - 1)
    sse = ((d - d.mean(axis=1, keepdims=True) - d.mean(axis=0, keepdims=True) + gm) ** 2).sum()
    mse = sse / ((n - 1) * (k - 1))
    return (msr - mse) / (msr + (k - 1) * mse + k * (msc - mse) / n)


def agreement_metrics(x, y, ddof=1):
    x, y = np.asarray(x, float), np.asarray(y, float)
    d = y - x
    nan = float("nan")
    ape = np.abs(d) / np.abs(x) * 100 if np.all(np.abs(x) > 1e-12) else np.full(len(x), nan)
    sl, ic, r, _, _ = stats.linregress(x, y)
    return {"n": len(x), "bias": d.mean(), "sd": d.std(ddof=ddof), "mae": np.abs(d).mean(),
            "rmse": math.sqrt((d ** 2).mean()), "mape": ape.mean(), "mape_sd": ape.std(ddof=ddof),
            "slope": sl, "intercept": ic, "r2": r ** 2, "icc": icc_2_1(np.column_stack([x, y]))}


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def num(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def paired(pub, mine):
    ids = [s for s in pub if s in mine and pub[s] is not None and mine[s] is not None]
    return [pub[s] for s in ids], [mine[s] for s in ids]


def print_table(rows, paper, paper_key):
    print(f"{'unit':32s} {'n':>4s} {'bias':>9s} {'mae':>8s} {'MAPE%':>7s} {'slope':>7s} {'r2':>6s} {'ICC':>6s} | "
          f"{'paper MAPE%':>11s} {'paper ICC':>9s}")
    for unit, m in rows:
        p = paper.get(paper_key(unit))
        pm_val = num(p.get("mape", p.get("mape_mean"))) if p else None
        pm = f"{pm_val:11.3f}" if pm_val is not None else f"{'-':>11s}"
        pi = f"{num(p.get('icc')):9.4f}" if p and num(p.get("icc")) is not None else f"{'-':>9s}"
        print(f"{unit[:32]:32s} {m['n']:4d} {m['bias']:9.4f} {m['mae']:8.4f} {m['mape']:7.3f} "
              f"{m['slope']:7.3f} {m['r2']:6.3f} {m['icc']:6.4f} | {pm} {pi}")


def compare(a):
    data_dir = os.path.join(a.package, "data")
    if a.type == "centiloid":
        pub = {r["subject_id"]: r for r in read_csv(os.path.join(data_dir, "centiloid_avid.csv")) if r["status"] == "ok"}
        mine = {r["subject_id"]: r for r in read_csv(a.table)}
        paper_path = os.path.join(data_dir, "centiloid_voi_agreement.csv")
        paper = {r["voi"]: r for r in read_csv(paper_path)} if os.path.isfile(paper_path) else {}
        cols = next(iter(mine.values())).keys()
        units = [c for c in SIX_VOIS + ["ctx_suvr", "centiloid_pipeline"] if c in cols]
        compute_ctx = "ctx_suvr" not in cols and all(c in cols for c in SIX_VOIS)
        print(f"Published (status=ok): {len(pub)} | your table: {len(mine)} | in common: {len(set(pub) & set(mine))}")
        if compute_ctx:
            for s, r in mine.items():
                v = [num(r[c]) for c in SIX_VOIS]
                r["ctx_suvr"] = str(np.mean(v)) if all(x is not None for x in v) else ""
            units.insert(len(SIX_VOIS), "ctx_suvr")
            print("ctx_suvr computed as the simple mean of the 6 regions")
        rows = []
        for u in units:
            x, y = paired({s: num(r[u]) for s, r in pub.items()}, {s: num(r[u]) for s, r in mine.items()})
            if len(x) >= 3:
                rows.append((u, agreement_metrics(x, y, a.ddof)))
            else:
                print(f"  {u}: fewer than 3 paired subjects, skipped")
        key = lambda u: "Composite_Summary" if u == "ctx_suvr" else u.replace("suvr_", "", 1)
        print_table(rows, paper, key)
    else:
        filename, pub_col = ("tau_values.csv", "suvr_ours") if a.type == "tau" else ("fdg_values.csv", "ours")
        pub = {}
        for r in read_csv(os.path.join(data_dir, filename)):
            pub.setdefault(r["composite_region"], {})[r["subject"]] = num(r[pub_col])
        mine = {}
        for r in read_csv(a.table):
            mine.setdefault(r["composite_region"], {})[r["subject"]] = num(r[a.value_col])
        paper_path = os.path.join(data_dir, f"{a.type}_composites.csv")
        paper = {r["composite_region"]: r for r in read_csv(paper_path)} if os.path.isfile(paper_path) else {}
        rows = []
        for reg in pub:
            if reg not in mine:
                print(f"  {reg}: not in your table")
                continue
            x, y = paired(pub[reg], mine[reg])
            if len(x) >= 3:
                rows.append((reg, agreement_metrics(x, y, a.ddof)))
        print_table(rows, paper, lambda u: u)
    if a.output:
        with open(a.output, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["unit"] + COLS)
            for u, m in rows:
                w.writerow([u] + [m[c] for c in COLS])
        print(f"\nSaved: {a.output}")
    if rows:
        print_note(a.type)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--package", default=".", help="repository folder (contains data/)")
    p.add_argument("--type", choices=["centiloid", "tau", "fdg"])
    p.add_argument("--table", help="CSV with your values")
    p.add_argument("--value_col", default="value", help="tau/fdg: name of the value column in --table")
    p.add_argument("--output", help="write the metrics to this CSV")
    p.add_argument("--ddof", type=int, default=1, help="degrees of freedom for SD (1 = sample SD)")
    a = p.parse_args()
    if not a.type or not a.table:
        p.error("--type and --table are required")
    compare(a)


if __name__ == "__main__":
    main()
