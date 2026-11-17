#!/usr/bin/env python3
"""
make_roi_lists.py -- generate this repository's ROI lists (data/rois_fdg.csv and
data/rois_ftp.csv) from their primary sources, so they are reproducible rather than
carried over from somewhere else. Re-run it after changing FreeSurferColorLUT.txt and
the two files are rebuilt identically.

The lists have two kinds of rows, and each comes from a documented source:

1. Single-region rows (`roi_name,label_id`). These are the structures FreeSurfer's own
   segmentation produces, with the label ids FreeSurfer assigns them. The ids and the
   names are read straight out of FreeSurferColorLUT.txt, which ships inside FreeSurfer
   itself -- nothing here is chosen by us:
     - Cortex: the Desikan-Killiany parcellation (aparc), label ids 1001-1035 (left) and
       2001-2035 (right). 1004/2004 (`ctx-?h-corpuscallosum`) is excluded because
       FreeSurfer does not report it; it is a retired label kept in the LUT for
       backwards compatibility. That leaves the 34 regions per hemisphere of the atlas.
       Desikan RS et al., NeuroImage 2006;31(3):968-80.
     - Subcortical and midline: the structures reported in aseg.stats (ASEG_IDS below).
       Fischl B et al., Neuron 2002;33(3):341-55.

2. Composite rows (`roi_name,id;id;...`). Only one composite is used by this repository:
   `meta_temporal`, the tau PET temporal meta-ROI of Jack CR Jr et al., Alzheimer's &
   Dementia 2017 -- amygdala, entorhinal cortex, fusiform, parahippocampal, inferior
   temporal and middle temporal gyri, bilaterally. Its membership is also declared in
   code/replication_tool/evaluate_subject.py (META_TEMPORAL_REGIONS) and the two files
   are checked against each other by this script.

Tau and FDG use the same regions: `evaluate_subject.py` evaluates both tracers on
`meta_temporal` and its six constituent regions, which is what data/tau_values.csv and
data/fdg_values.csv contain. What differs between the tracers is the reference region
(cerebellar cortex for Tau, pons for FDG) and partial-volume correction, neither of
which lives in these files. The two outputs are therefore identical in content; both
are written so each tracer keeps its own named input.

Names are emitted with '_' instead of the LUT's '-'. evaluate_subject.resolve_name()
accepts either form, plus the retired '_Proper' suffix, so the lists work with
segmentations from FreeSurfer 6 and 7 alike.

Usage:
    python3 code/replication_tool/make_roi_lists.py \
        --lut pet_pipeline/FreeSurferColorLUT.txt --outdir data
"""

import argparse
import csv
import os
import sys

# Subcortical and midline structures reported in aseg.stats, by FreeSurfer label id.
# Left/right pairs first, then the unpaired midline structures.
ASEG_IDS = [
    2, 4, 5, 7, 8, 10, 11, 12, 13, 17, 18, 26, 28, 31,          # left hemisphere
    41, 43, 44, 46, 47, 49, 50, 51, 52, 53, 54, 58, 60, 63,     # right hemisphere
    14, 15, 16, 24, 77, 85,                                      # ventricles, brainstem, CSF, etc.
    251, 252, 253, 254, 255,                                     # corpus callosum segments
]

# Desikan-Killiany cortical labels: 1001-1035 / 2001-2035 without the retired
# corpuscallosum entry (1004/2004).
CORTICAL_IDS = ([i for i in range(1001, 1036) if i != 1004] +
                [i for i in range(2001, 2036) if i != 2004])

# meta_temporal -- Jack CR Jr et al. 2017 tau PET temporal meta-ROI.
# {region: [left_label, right_label]}, kept in this shape so it can be compared
# directly against META_TEMPORAL_REGIONS in evaluate_subject.py.
META_TEMPORAL_REGIONS = {
    "Amygdala":         [18, 54],
    "entorhinal":       [1006, 2006],
    "fusiform":         [1007, 2007],
    "inferiortemporal": [1009, 2009],
    "middletemporal":   [1015, 2015],
    "parahippocampal":  [1016, 2016],
}


def load_lut(path):
    """Read FreeSurferColorLUT.txt -> {label_id: StructName}. Same parsing as
    composite_regions.load_lut(), so both agree on what the LUT says."""
    lut = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            try:
                label_id = int(parts[0])
            except ValueError:
                continue
            lut[label_id] = parts[1]
    return lut


def build_rows(lut):
    """Return the rows of the ROI list, in label-id order, composite last."""
    missing = [i for i in ASEG_IDS + CORTICAL_IDS if i not in lut]
    if missing:
        sys.exit(f"ERROR: these label ids are not in the LUT: {missing}")

    rows = [{"roi_name": lut[i].replace("-", "_"), "roi_labels": str(i)}
            for i in sorted(ASEG_IDS + CORTICAL_IDS)]

    meta = sorted(i for pair in META_TEMPORAL_REGIONS.values() for i in pair)
    rows.append({"roi_name": "meta_temporal", "roi_labels": ";".join(str(i) for i in meta)})
    return rows


def check_against_evaluate_subject(repo_root):
    """META_TEMPORAL_REGIONS must match the copy in evaluate_subject.py, which is what
    actually computes the per-region values. Fail loudly if the two ever drift apart."""
    path = os.path.join(repo_root, "code", "replication_tool", "evaluate_subject.py")
    if not os.path.exists(path):
        return "skipped (evaluate_subject.py not found)"
    ns = {}
    src = open(path).read()
    start = src.index("META_TEMPORAL_REGIONS = {")
    end = src.index("}", start) + 1
    exec(src[start:end], ns)
    theirs = {k: sorted(v) for k, v in ns["META_TEMPORAL_REGIONS"].items()}
    ours = {k: sorted(v) for k, v in META_TEMPORAL_REGIONS.items()}
    if theirs != ours:
        sys.exit(f"ERROR: meta_temporal disagrees with evaluate_subject.py\n"
                 f"  here: {ours}\n  there: {theirs}")
    return "matches evaluate_subject.py"


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--lut", required=True, help="path to FreeSurferColorLUT.txt")
    p.add_argument("--outdir", default="data", help="where to write the lists (default: data)")
    a = p.parse_args()

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    print(f"meta_temporal: {check_against_evaluate_subject(repo_root)}")

    lut = load_lut(a.lut)
    rows = build_rows(lut)
    os.makedirs(a.outdir, exist_ok=True)

    for name in ("rois_fdg.csv", "rois_ftp.csv"):
        out = os.path.join(a.outdir, name)
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["roi_name", "roi_labels"])
            w.writeheader()
            w.writerows(rows)
        print(f"wrote {out}  ({len(rows)} rows)")


if __name__ == "__main__":
    main()
