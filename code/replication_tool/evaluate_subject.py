#!/usr/bin/env python3
"""
evaluate_subject.py -- process the OUTPUT of your pipeline for one or more subjects and, if a
subject is among the published values of this repository (data/), compare it with THOSE values
(the ones from this work). If the subject is not published, only your own values are returned,
without any comparison.

No A4 or LEADS data are read or needed: the only reference is data/ of this repository. For a
published subject the comparison is "your value vs the published value of this work"; there is no
pass/fail threshold.

A single subject compares against a single published value per region. It tells you whether your
installation resembles ours; it does not estimate agreement. Cohort-level agreement (and agreement
with the reference) is reported in the paper and in data/*_composites.csv. For 3 or more subjects
also use compare_with_published.py (this tool writes values_<type>.csv in the format it reads).

Besides the composites, for Tau and FDG it writes values_<type>_bilateral.csv with the SUVR of every
bilateral region (left + right hemisphere, divided by the reference region):
  Tau (no PVC)  44 regions (BILATERAL_TAU), weighted by volume (mm3); reference = whole cerebellar cortex.
  Tau (PVC)     same 44 regions from mri_gtmpvc (gtm.stats.dat), weighted by number of voxels;
                written to values_tau_bilateral_pvc.csv when gtm.stats.dat exists.
  FDG (no PVC)  regions of the FDG ROI list (--fsroi-list data/fsroi_list_FDG.csv), weighted by
                volume (mm3); reference = pons.
A region is reported only when both hemispheres are present in your segmentation. Published bilateral
values are in data/tau_bilateral_published.csv, data/tau_bilateral_pvc_published.csv and
data/fdg_bilateral_published.csv (same columns); merge on (subject, region) to compare them.

Inputs by type:
  tau        <base>/<subject>/output.csv  (mri_segstats; normalised by the whole cerebellar cortex)
             + --fsroi-list fsroi_list_FTP.csv + --lut FreeSurferColorLUT.txt
  fdg        <base>/<subject>/output_fdg.csv and output_brainstem_fdg.csv (reference: pons)
             + --fsroi-list data/fsroi_list_FDG.csv + --lut FreeSurferColorLUT.txt
  centiloid  CSV written by centiloid_pipeline_tracers.py (--results)

Examples:
  python3 evaluate_subject.py --type tau --package /path/to/repo --fastsurfer-base /path/to/output \\
      --subject S001 --fsroi-list fsroi_list_FTP.csv --lut FreeSurferColorLUT.txt
  python3 evaluate_subject.py --type fdg --package /path/to/repo --fastsurfer-base /path/to/output --all \\
      --fsroi-list /path/to/repo/data/fsroi_list_FDG.csv --lut FreeSurferColorLUT.txt
  python3 evaluate_subject.py --type centiloid --package /path/to/repo --results centiloid_results.csv --all
"""
import argparse
import csv
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from composite_regions import read_composites, load_lut, composite_from_segstats  # noqa: E402
from interpretation_note import print_note  # noqa: E402

# Regions that accompany meta_temporal (Jack et al. 2017): the same ones used in the paper.
META_TEMPORAL_REGIONS = {
    "Amygdala": [18, 54], "entorhinal": [1006, 2006], "fusiform": [1007, 2007],
    "inferiortemporal": [1009, 2009], "middletemporal": [1015, 2015],
    "parahippocampal": [1016, 2016],
}

# Bilateral Tau regions: (left, right) FreeSurfer structure names.
BILATERAL_TAU = {
    "bi_Hippocampus": ("Left-Hippocampus", "Right-Hippocampus"),
    "bi_Amygdala": ("Left-Amygdala", "Right-Amygdala"),
    "bi_Caudate": ("Left-Caudate", "Right-Caudate"),
    "bi_Putamen": ("Left-Putamen", "Right-Putamen"),
    "bi_Thalamus": ("Left-Thalamus", "Right-Thalamus"),
    "bi_Accumbens_area": ("Left-Accumbens-area", "Right-Accumbens-area"),
    "bi_VentralDC": ("Left-VentralDC", "Right-VentralDC"),
    "bi_Cerebellum_Cortex": ("Left-Cerebellum-Cortex", "Right-Cerebellum-Cortex"),
    "bi_Cerebellum_White_Matter": ("Left-Cerebellum-White-Matter", "Right-Cerebellum-White-Matter"),
    "bi_Cerebral_White_Matter": ("Left-Cerebral-White-Matter", "Right-Cerebral-White-Matter"),
    "bi_entorhinal": ("ctx-lh-entorhinal", "ctx-rh-entorhinal"),
    "bi_parahippocampal": ("ctx-lh-parahippocampal", "ctx-rh-parahippocampal"),
    "bi_fusiform": ("ctx-lh-fusiform", "ctx-rh-fusiform"),
    "bi_inferiortemporal": ("ctx-lh-inferiortemporal", "ctx-rh-inferiortemporal"),
    "bi_middletemporal": ("ctx-lh-middletemporal", "ctx-rh-middletemporal"),
    "bi_superiortemporal": ("ctx-lh-superiortemporal", "ctx-rh-superiortemporal"),
    "bi_inferiorparietal": ("ctx-lh-inferiorparietal", "ctx-rh-inferiorparietal"),
    "bi_superiorparietal": ("ctx-lh-superiorparietal", "ctx-rh-superiorparietal"),
    "bi_supramarginal": ("ctx-lh-supramarginal", "ctx-rh-supramarginal"),
    "bi_precuneus": ("ctx-lh-precuneus", "ctx-rh-precuneus"),
    "bi_isthmuscingulate": ("ctx-lh-isthmuscingulate", "ctx-rh-isthmuscingulate"),
    "bi_posteriorcingulate": ("ctx-lh-posteriorcingulate", "ctx-rh-posteriorcingulate"),
    "bi_caudalanteriorcingulate": ("ctx-lh-caudalanteriorcingulate", "ctx-rh-caudalanteriorcingulate"),
    "bi_rostralanteriorcingulate": ("ctx-lh-rostralanteriorcingulate", "ctx-rh-rostralanteriorcingulate"),
    "bi_lateraloccipital": ("ctx-lh-lateraloccipital", "ctx-rh-lateraloccipital"),
    "bi_lingual": ("ctx-lh-lingual", "ctx-rh-lingual"),
    "bi_cuneus": ("ctx-lh-cuneus", "ctx-rh-cuneus"),
    "bi_pericalcarine": ("ctx-lh-pericalcarine", "ctx-rh-pericalcarine"),
    "bi_insula": ("ctx-lh-insula", "ctx-rh-insula"),
    "bi_superiorfrontal": ("ctx-lh-superiorfrontal", "ctx-rh-superiorfrontal"),
    "bi_rostralmiddlefrontal": ("ctx-lh-rostralmiddlefrontal", "ctx-rh-rostralmiddlefrontal"),
    "bi_caudalmiddlefrontal": ("ctx-lh-caudalmiddlefrontal", "ctx-rh-caudalmiddlefrontal"),
    "bi_lateralorbitofrontal": ("ctx-lh-lateralorbitofrontal", "ctx-rh-lateralorbitofrontal"),
    "bi_medialorbitofrontal": ("ctx-lh-medialorbitofrontal", "ctx-rh-medialorbitofrontal"),
    "bi_parsopercularis": ("ctx-lh-parsopercularis", "ctx-rh-parsopercularis"),
    "bi_parstriangularis": ("ctx-lh-parstriangularis", "ctx-rh-parstriangularis"),
    "bi_parsorbitalis": ("ctx-lh-parsorbitalis", "ctx-rh-parsorbitalis"),
    "bi_precentral": ("ctx-lh-precentral", "ctx-rh-precentral"),
    "bi_postcentral": ("ctx-lh-postcentral", "ctx-rh-postcentral"),
    "bi_paracentral": ("ctx-lh-paracentral", "ctx-rh-paracentral"),
    "bi_bankssts": ("ctx-lh-bankssts", "ctx-rh-bankssts"),
    "bi_transversetemporal": ("ctx-lh-transversetemporal", "ctx-rh-transversetemporal"),
    "bi_temporalpole": ("ctx-lh-temporalpole", "ctx-rh-temporalpole"),
    "bi_frontalpole": ("ctx-lh-frontalpole", "ctx-rh-frontalpole"),
}

# The six Avid VOI SUVR columns of the Centiloid pipeline output.
SIX_VOIS = ["suvr_lanterior_cingulate_2", "suvr_llposterior_cingulate_2", "suvr_lnew_parietal",
            "suvr_lprecuneus_gm", "suvr_new_temporal_2", "suvr_xlaal_frontal_med_orb"]


# ---------------------------------------------------------------- utilities
def num(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_segstats(path):
    """Parse an mri_segstats table: Index SegId NVoxels Volume_mm3 StructName Mean StdDev Min Max Range."""
    d = {}
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            p = line.split()
            if len(p) < 10:
                continue
            try:
                d[p[4]] = {"mean": float(p[5]), "nvoxels": int(p[2]), "volume": float(p[3])}
            except ValueError:
                continue
    return d


def cerebellum_mean(seg):
    """Voxel-weighted mean of the left and right cerebellar cortex."""
    lh = seg.get("ctx-lh-Cerebellum-Cortex") or seg.get("Left-Cerebellum-Cortex")
    rh = seg.get("ctx-rh-Cerebellum-Cortex") or seg.get("Right-Cerebellum-Cortex")
    if lh is None or rh is None:
        return None
    v = lh["nvoxels"] + rh["nvoxels"]
    return (lh["mean"] * lh["nvoxels"] + rh["mean"] * rh["nvoxels"]) / v if v else None


def resolve_name(lut_name, seg):
    """The LUT uses hyphens; some tables use '_' or the '_Proper' suffix."""
    cands = [lut_name, lut_name.replace("_", "-")]
    if lut_name.endswith("_Proper"):
        cands.append(lut_name[:-len("_Proper")].replace("_", "-"))
    return next((c for c in cands if c in seg), None)


# ------------------------------------------------- composite values (your own)
def tau_fdg_regions(seg, ref_mean, composites, lut, resolver=None):
    """Return ({region: value}, {region: reason_if_not_computed})."""
    vals, reasons = {}, {}
    allr = dict(composites)
    allr.update({f"[region] {k}": v for k, v in META_TEMPORAL_REGIONS.items()})
    for name, labels in allr.items():
        mean, nvox, missing = composite_from_segstats(seg, labels, lut, name_resolver=resolver)
        if missing:
            reasons[name] = f"labels {sorted(missing)} are missing in your segmentation (partial averages are not computed)"
        elif not nvox or mean is None or (isinstance(mean, float) and math.isnan(mean)):
            reasons[name] = "no voxels"
        else:
            vals[name] = mean / ref_mean
    return vals, reasons


def load_seg(a, subject):
    """Return (seg, ref_mean, error). Reference = whole cerebellar cortex (Tau) or pons (FDG)."""
    base = os.path.join(a.fastsurfer_base, subject)
    if a.type == "tau":
        path = os.path.join(base, a.seg_filename)
        if not os.path.isfile(path):
            return None, None, f"{path} does not exist"
        seg = load_segstats(path)
        ref = cerebellum_mean(seg)
        if not ref:
            return None, None, "whole cerebellar cortex not found in your segmentation"
        return seg, ref, None
    path, path_bs = os.path.join(base, "output_fdg.csv"), os.path.join(base, "output_brainstem_fdg.csv")
    for r in (path, path_bs):
        if not os.path.isfile(r):
            return None, None, f"{r} does not exist"
    pons = load_segstats(path_bs).get("Pons")
    if not pons or pons["mean"] <= 0:
        return None, None, "row 'Pons' not found in output_brainstem_fdg.csv"
    return load_segstats(path), pons["mean"], None


def own_values(a, subject, composites, lut):
    seg, ref, err = load_seg(a, subject)
    if err:
        return None, {"*": err}
    return tau_fdg_regions(seg, ref, composites, lut, resolver=resolve_name if a.type == "fdg" else None)


# ------------------------------------------------------ bilateral regions
HEMI_PREFIXES = (("ctx-lh-", "lh"), ("ctx_lh_", "lh"), ("ctx-rh-", "rh"), ("ctx_rh_", "rh"),
                 ("Left-", "lh"), ("Left_", "lh"), ("Right-", "rh"), ("Right_", "rh"))


def pairs_from_roi_list(fsroi_list, seg):
    """FDG: left/right pairs of the ROI list (ctx_lh_X/ctx_rh_X and Left_X/Right_X) resolved in your segmentation.
    Return ({region: (lh_name, rh_name)}, [unresolved regions])."""
    names = [r["roi_name"].strip() for r in read_csv(fsroi_list)]
    pairs, unresolved = {}, []
    for n in names:
        for pl, pr in (("ctx_lh_", "ctx_rh_"), ("Left_", "Right_")):
            if n.startswith(pl) and pr + n[len(pl):] in names:
                base = n[len(pl):]
                lh, rh = resolve_name(n, seg), resolve_name(pr + base, seg)
                if lh and rh:
                    pairs[base] = (lh, rh)
                else:
                    unresolved.append(base)
    return pairs, unresolved


def _short_list(items, n=8):
    return f"{sorted(items)[:n]}{' ...' if len(items) > n else ''}"


def own_bilaterals(a, subject):
    """Bilateral SUVR = mean of both hemispheres / reference.
    Tau (no PVC): BILATERAL_TAU list, volume-weighted (mm3), reference = whole cerebellar cortex.
    FDG (no PVC): regions of the FDG ROI list, volume-weighted (mm3), reference = pons.
    A region is returned only if BOTH hemispheres are present. Return (rows, note)."""
    seg, ref, err = load_seg(a, subject)
    if err:
        return [], err
    note = None
    if a.type == "tau":
        pairs, weight = BILATERAL_TAU, "volume"
        missing = [r for r, (lh, rh) in pairs.items() if lh not in seg or rh not in seg]
        pairs = {r: p for r, p in pairs.items() if r not in missing}
        if missing:
            note = f"{len(missing)} listed regions are incomplete in your segmentation: {_short_list(missing)}"
    else:
        pairs, missing = pairs_from_roi_list(a.fsroi_list, seg)
        weight = "volume"
        if missing:
            note = f"{len(missing)} listed regions are not in your segmentation: {_short_list(missing)}"
    rows = []
    for region, (lh, rh) in pairs.items():
        x, y = seg[lh], seg[rh]
        w = x[weight] + y[weight]
        if w == 0:
            continue
        rows.append({"subject": subject, "region": region,
                     "suvr": (x["mean"] * x[weight] + y["mean"] * y[weight]) / w / ref,
                     "nvoxels": x["nvoxels"] + y["nvoxels"], "volume_mm3": x["volume"] + y["volume"]})
    return rows, note


def load_gtm(path):
    """Parse gtm.stats.dat from mri_gtmpvc: name = column 3, NVoxels = column 5, mean = column 7
    (already in SUVR units because the pipeline runs mri_gtmpvc with --rescale)."""
    d = {}
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            p = line.split()
            if len(p) >= 7:
                try:
                    d[p[2]] = {"nvoxels": float(p[4]), "mean": float(p[6])}
                except ValueError:
                    continue
    return d


def own_bilaterals_pvc(a, subject):
    """Tau WITH PVC (mri_gtmpvc): voxel-weighted bilateral SUVR, same BILATERAL_TAU list.
    A region is returned only if BOTH hemispheres are present. Return (rows, note)."""
    path = os.path.join(a.fastsurfer_base, subject, "gtmpvc_T1space_mask.output", "gtm.stats.dat")
    if not os.path.isfile(path):
        return [], f"{path} does not exist"
    gtm = load_gtm(path)
    rows, missing = [], []
    for region, (lh, rh) in BILATERAL_TAU.items():
        x, y = gtm.get(lh), gtm.get(rh)
        if not x or not y:
            missing.append(region)
            continue
        w = x["nvoxels"] + y["nvoxels"]
        if w == 0:
            continue
        rows.append({"subject": subject, "region": region,
                     "suvr": (x["mean"] * x["nvoxels"] + y["mean"] * y["nvoxels"]) / w,
                     "nvoxels": w, "volume_mm3": ""})
    note = f"{len(missing)} regions are incomplete in gtm.stats.dat: {_short_list(missing)}" if missing else None
    return rows, note


# ------------------------------------------------------------------ published values
def load_published(package, data_type):
    data_dir = os.path.join(package, "data")
    if data_type == "centiloid":
        path = os.path.join(data_dir, "centiloid_avid.csv")
        if not os.path.isfile(path):
            sys.exit(f"ERROR: {path} not found")
        return {r["subject_id"]: r for r in read_csv(path) if r.get("status", "ok") == "ok"}
    filename, col = ("tau_values.csv", "suvr_ours") if data_type == "tau" else ("fdg_values.csv", "ours")
    path = os.path.join(data_dir, filename)
    if not os.path.isfile(path):
        sys.exit(f"ERROR: {path} not found")
    pub = {}
    for r in read_csv(path):
        pub.setdefault(r["subject"], {})[r["composite_region"]] = num(r[col])
    return pub


def paper_context(package, data_type):
    """MAPE / ICC from the paper per unit (this work vs the reference); context only."""
    data_dir = os.path.join(package, "data")
    path = os.path.join(data_dir, "centiloid_voi_agreement.csv" if data_type == "centiloid" else f"{data_type}_composites.csv")
    if not os.path.isfile(path):
        return {}
    key = "voi" if data_type == "centiloid" else "composite_region"
    return {r[key]: r for r in read_csv(path)}


def paper_mape(ctx, unit):
    r = ctx.get("Composite_Summary" if unit == "ctx_suvr" else unit.replace("suvr_", "", 1)
                if unit.startswith("suvr_") else unit)
    return num(r.get("mape", r.get("mape_mean"))) if r else None


# ------------------------------------------------------------------ comparison
def compare_subject(subject, own, pub, ctx):
    rows = []
    for u, y in own.items():
        x = pub.get(u)
        if x is None or y is None:
            continue
        d = y - x
        rows.append({"unit": u, "yours": y, "published": x, "diff": d,
                     "diff_pct": d / abs(x) * 100 if abs(x) > 1e-12 else float("nan"),
                     "paper_mape": paper_mape(ctx, u)})
    return rows


def print_comparison(subject, rows):
    print(f"\n{subject}: your value vs the published value of this work")
    print(f"  {'unit':34s} {'yours':>9s} {'published':>10s} {'diff':>9s} {'diff %':>8s} | {'paper MAPE %':>12s}")
    for f in rows:
        pm = f"{f['paper_mape']:12.3f}" if f["paper_mape"] is not None else f"{'-':>12s}"
        print(f"  {f['unit'][:34]:34s} {f['yours']:9.4f} {f['published']:10.4f} {f['diff']:+9.4f} "
              f"{f['diff_pct']:+8.2f} | {pm}")
    # centiloid_pipeline (CL scale, can be close to 0) is excluded from the percentage average
    pcts = [abs(f["diff_pct"]) for f in rows
            if f["diff_pct"] == f["diff_pct"] and f["unit"] != "centiloid_pipeline"]
    if pcts:
        print(f"  Mean |diff %| for this subject: {sum(pcts) / len(pcts):.2f} % over {len(pcts)} units "
              f"(no threshold; the paper column is context only: cohort agreement with the reference)")


def _write_rows(path, fieldnames, rows, extrasaction="raise"):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction=extrasaction)
        w.writeheader()
        w.writerows(rows)


COMPARISON_COLUMNS = ["unit", "yours", "published", "diff", "diff_pct", "paper_mape"]
BILATERAL_COLUMNS = ["subject", "region", "suvr", "nvoxels", "volume_mm3"]


def main():
    # Same PETPIPELINE_BASE convention as run_public_pipeline.sh (default ~/Downloads/pet_pipeline):
    # SUBJECTS_DIR there is PETPIPELINE_BASE/output, PUBLIC_PACKAGE defaults to this repo's own root,
    # FS_LUT to ~/freesurfer/FreeSurferColorLUT.txt -- mirrored here so none of these need typing out
    # by hand on every call.
    petpipeline_base = os.environ.get("PETPIPELINE_BASE") or os.path.expanduser("~/Downloads/pet_pipeline")
    default_package = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    default_fastsurfer_base = os.path.join(petpipeline_base, "output")
    default_lut = os.path.expanduser("~/freesurfer/FreeSurferColorLUT.txt")
    default_output = os.path.join(petpipeline_base, "subject_evaluation")

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--type", required=True, choices=["tau", "fdg", "centiloid"])
    p.add_argument("--package", default=default_package, help="repository folder (contains data/); "
                   "defaults to this repo's own root")
    p.add_argument("--subject", action="append", default=[], help="subject ID; repeat for several")
    p.add_argument("--all", action="store_true", help="every subject that has output")
    p.add_argument("--fastsurfer-base", default=default_fastsurfer_base,
                   help="tau/fdg: folder containing <subject>/output*.csv "
                        f"(default: {default_fastsurfer_base}, i.e. PETPIPELINE_BASE/output)")
    p.add_argument("--seg-filename", default="output.csv", help="tau: name of the segstats table")
    p.add_argument("--fsroi-list", help="tau/fdg: ROI list (fsroi_list_FTP.csv for Tau, default "
                   "<package>/fsroi_list_FTP.csv; data/fsroi_list_FDG.csv for FDG, default "
                   "<package>/data/fsroi_list_FDG.csv)")
    p.add_argument("--lut", default=default_lut,
                   help=f"FreeSurferColorLUT.txt (default: {default_lut})")
    p.add_argument("--results", help="centiloid: CSV written by centiloid_pipeline_tracers.py")
    p.add_argument("--output", default=default_output,
                   help=f"output folder (default: {default_output}, i.e. PETPIPELINE_BASE/subject_evaluation)")
    a = p.parse_args()
    if not a.subject and not a.all:
        p.error("give --subject ID (repeatable) or --all")
    if not a.fsroi_list:
        a.fsroi_list = (os.path.join(a.package, "data", "fsroi_list_FDG.csv") if a.type == "fdg"
                        else os.path.join(a.package, "fsroi_list_FTP.csv"))

    pub = load_published(a.package, a.type)
    ctx = paper_context(a.package, a.type)
    os.makedirs(a.output, exist_ok=True)
    compared, not_compared, failed, values_out = [], [], [], []
    pvc_written = False

    if a.type == "centiloid":
        if not a.results:
            p.error("centiloid requires --results")
        mine = {r["subject_id"]: r for r in read_csv(a.results)}
        ids = sorted(mine) if a.all else a.subject
        for s in ids:
            r = mine.get(s)
            if r is None or r.get("status", "ok") != "ok":
                failed.append((s, "not in your CSV" if r is None else f"status={r.get('status')}: {r.get('error', '')}"))
                continue
            own = {c: num(r[c]) for c in SIX_VOIS + ["ctx_suvr", "centiloid_pipeline"] if c in r}
            values_out.append(r)
            if s in pub:
                rows = compare_subject(s, own, {c: num(v) for c, v in pub[s].items()}, ctx)
                compared.append(s)
                print_comparison(s, rows)
                _write_rows(os.path.join(a.output, f"{s}_centiloid_comparison.csv"), COMPARISON_COLUMNS, rows)
            else:
                not_compared.append(s)
                print(f"\n{s}: not among the published values -> only your output is returned, nothing is compared.")
        if values_out:
            _write_rows(os.path.join(a.output, "values_centiloid.csv"), list(values_out[0].keys()), values_out,
                        extrasaction="ignore")
    else:
        if not (a.fastsurfer_base and a.fsroi_list and a.lut):
            p.error("tau/fdg require --fastsurfer-base, --fsroi-list and --lut")
        allc = read_composites(a.fsroi_list)
        if "meta_temporal" not in allc:
            sys.exit(f"ERROR: 'meta_temporal' is not in {a.fsroi_list}")
        composites = {"meta_temporal": allc["meta_temporal"]}
        lut = load_lut(a.lut)
        seg_name = a.seg_filename if a.type == "tau" else "output_fdg.csv"
        base = os.path.expanduser(a.fastsurfer_base)
        a.fastsurfer_base = base
        ids = (sorted(s for s in os.listdir(base) if os.path.isfile(os.path.join(base, s, seg_name)))
               if a.all else a.subject)
        bilat_out, bilat_pvc = [], []
        for s in ids:
            own, reasons = own_values(a, s, composites, lut)
            if own is None:
                failed.append((s, reasons["*"]))
                continue
            for u, m in reasons.items():
                print(f"  {s}: {u} not computed: {m}")
            for u, v in own.items():
                values_out.append({"subject": s, "composite_region": u, "value": v})
            rows_b, note_b = own_bilaterals(a, s)
            bilat_out.extend(rows_b)
            if note_b:
                print(f"  {s}: {note_b}")
            if a.type == "tau":
                rows_p, note_p = own_bilaterals_pvc(a, s)
                bilat_pvc.extend(rows_p)
                if note_p and rows_p:
                    print(f"  {s} (PVC): {note_p}")
            if s in pub:
                rows = compare_subject(s, own, pub[s], ctx)
                compared.append(s)
                print_comparison(s, rows)
                _write_rows(os.path.join(a.output, f"{s}_{a.type}_comparison.csv"), COMPARISON_COLUMNS, rows)
            else:
                not_compared.append(s)
                print(f"\n{s}: not among the published values -> only your output is returned, nothing is compared.")
        _write_rows(os.path.join(a.output, f"values_{a.type}.csv"), ["subject", "composite_region", "value"], values_out)
        if bilat_out:
            path_b = os.path.join(a.output, f"values_{a.type}_bilateral.csv")
            _write_rows(path_b, BILATERAL_COLUMNS, bilat_out)
            print(f"\nSUVR of {len(bilat_out)} bilateral rows (all subjects): {path_b}")
        if bilat_pvc:
            path_p = os.path.join(a.output, "values_tau_bilateral_pvc.csv")
            _write_rows(path_p, BILATERAL_COLUMNS, bilat_pvc)
            pvc_written = True
            print(f"Bilateral SUVR WITH PVC ({len(bilat_pvc)} rows): {path_p}")

    print(f"\nSummary: {len(compared)} compared with the published values | {len(not_compared)} not compared "
          f"(not published) | {len(failed)} without usable output")
    for s, why in failed:
        print(f"  {s}: {why}")
    print(f"Files in {a.output}/ (values_{a.type}.csv holds your values in the format read by compare_with_published.py"
          f"{'; use --value_col value' if a.type != 'centiloid' else ''})")
    if compared or a.type == "tau":
        print_note(a.type, pvc_written=pvc_written)


if __name__ == "__main__":
    main()
