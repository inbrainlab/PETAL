#!/usr/bin/env python3
"""
compare_bilateral.py -- compare YOUR bilateral regional SUVR with the published bilateral values.

Input (yours): values_tau_bilateral.csv, values_tau_bilateral_pvc.csv or values_fdg_bilateral.csv, written by
evaluate_subject.py (columns subject, region, suvr, nvoxels, volume_mm3).
Published: data/tau_bilateral_published.csv, data/tau_bilateral_pvc_published.csv or
data/fdg_bilateral_published.csv (same columns). Rows are matched on (subject, region).

Output: a table with yours, published, diff and diff % per (subject, region); a summary per region
(N, mean diff %, MAPE) and, for a single subject, the regions with the largest differences.

Examples:
  python3 compare_bilateral.py --mine values_tau_bilateral.csv --published data/tau_bilateral_published.csv
  python3 compare_bilateral.py --mine values_tau_bilateral_pvc.csv --published data/tau_bilateral_pvc_published.csv \
      --pvc --output bilateral_comparison.csv
"""
import argparse
import sys

import pandas as pd

from interpretation_note import print_note


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mine", required=True, help="your bilateral CSV (from evaluate_subject.py)")
    p.add_argument("--published", required=True, help="published bilateral CSV in data/")
    p.add_argument("--type", choices=["tau", "fdg"], default="tau", help="selects the interpretation note")
    p.add_argument("--pvc", action="store_true", help="the files are PVC-corrected (adds the PVC warning)")
    p.add_argument("--top", type=int, default=10, help="regions listed with the largest differences")
    p.add_argument("--output", help="write the per-row comparison to this CSV")
    a = p.parse_args()

    mine = pd.read_csv(a.mine, usecols=["subject", "region", "suvr"]).rename(columns={"suvr": "yours"})
    pub = pd.read_csv(a.published, usecols=["subject", "region", "suvr"]).rename(columns={"suvr": "published"})
    if pub["subject"].astype(str).str.match(r"^(ADNI|A4):\d+:[0-9a-f]{4}$").any():
        sys.exit("ERROR: the published table holds participant codes, not IDs. Restore them first with "
                 "code/replication_tool/resolve_subjects.py (see README) and use the table from the output folder.")
    m = mine.merge(pub, on=["subject", "region"], how="inner")
    if m.empty:
        sys.exit("No (subject, region) pairs in common: check that your subject is in the published file "
                 "and that you compare the same kind of table (Tau without PVC, Tau with PVC or FDG).")
    m["diff"] = m["yours"] - m["published"]
    m["diff_pct"] = m["diff"] / m["published"].abs() * 100
    print(f"Pairs compared: {len(m)} | subjects: {m['subject'].nunique()} | regions: {m['region'].nunique()} "
          f"| not matched in yours: {len(mine) - len(m)}")

    if m["subject"].nunique() == 1:
        s = m["subject"].iloc[0]
        print(f"\n{s}: mean |diff %| = {m['diff_pct'].abs().mean():.3f} % over {len(m)} regions "
              f"(max {m['diff_pct'].abs().max():.3f} %)")
        top = m.reindex(m["diff_pct"].abs().sort_values(ascending=False).index).head(a.top)
        print(f"\nRegions with the largest differences:")
        print(f"  {'region':36s} {'yours':>9s} {'published':>10s} {'diff':>9s} {'diff %':>8s}")
        for _, r in top.iterrows():
            print(f"  {r['region'][:36]:36s} {r['yours']:9.4f} {r['published']:10.4f} {r['diff']:+9.4f} "
                  f"{r['diff_pct']:+8.2f}")
    else:
        g = m.groupby("region").agg(n=("diff_pct", "size"), mean_diff_pct=("diff_pct", "mean"),
                                    mape=("diff_pct", lambda x: x.abs().mean())).sort_values("mape", ascending=False)
        print(f"\nOverall MAPE: {m['diff_pct'].abs().mean():.3f} %")
        print(f"\nRegions with the largest MAPE:")
        print(f"  {'region':36s} {'n':>4s} {'mean diff %':>12s} {'MAPE %':>8s}")
        for reg, r in g.head(a.top).iterrows():
            print(f"  {reg[:36]:36s} {int(r['n']):4d} {r['mean_diff_pct']:+12.3f} {r['mape']:8.3f}")

    if a.output:
        m.to_csv(a.output, index=False)
        print(f"\nSaved: {a.output}")
    print_note(a.type, pvc_written=a.pvc)


if __name__ == "__main__":
    main()
