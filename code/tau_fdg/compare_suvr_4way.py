#!/usr/bin/env python3
"""
compare_suvr_4way.py
Compare SUVR, mean intensities, volumes and voxel counts of one subject
against the A4 reference values (four comparisons: no-PVC SUVR, PVC SUVR,
mean intensity / volume, PVC voxel counts). MAPE is the primary metric.

The A4 reference tables (TAUSUVR_*.csv, TAUSUVR_PETSURFER_*.csv) are NOT
distributed with this repository; obtain them from the A4 study.

Usage:
  python3 compare_suvr_4way.py \
      --id         <SUBJECT_ID> \
      --nopvc_ours /path/to/<SUBJECT_ID>/output.csv \
      --pvc_ours   /path/to/<SUBJECT_ID>/gtmpvc_T1space_mask.output/gtm.stats.dat \
      --nopvc_a4   /path/to/A4/TAUSUVR_26Jan2026.csv \
      --pvc_a4     /path/to/A4/TAUSUVR_PETSURFER_26Jan2026.csv \
      --out        <SUBJECT_ID>_4way.png
"""

import argparse
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from scipy import stats

# ── SUVR bilateral regions ────────────────────────────────────────────────────
BILATERAL_REGIONS = {
    "bi_Hippocampus":              ("Left-Hippocampus",               "Right-Hippocampus"),
    "bi_Amygdala":                 ("Left-Amygdala",                  "Right-Amygdala"),
    "bi_Caudate":                  ("Left-Caudate",                   "Right-Caudate"),
    "bi_Putamen":                  ("Left-Putamen",                   "Right-Putamen"),
    "bi_Thalamus":                 ("Left-Thalamus",                  "Right-Thalamus"),
    "bi_Accumbens_area":           ("Left-Accumbens-area",            "Right-Accumbens-area"),
    "bi_VentralDC":                ("Left-VentralDC",                 "Right-VentralDC"),
    "bi_Cerebellum_Cortex":        ("Left-Cerebellum-Cortex",         "Right-Cerebellum-Cortex"),
    "bi_Cerebellum_White_Matter":  ("Left-Cerebellum-White-Matter",   "Right-Cerebellum-White-Matter"),
    "bi_Cerebral_White_Matter":    ("Left-Cerebral-White-Matter",     "Right-Cerebral-White-Matter"),
    "bi_entorhinal":               ("ctx-lh-entorhinal",              "ctx-rh-entorhinal"),
    "bi_parahippocampal":          ("ctx-lh-parahippocampal",         "ctx-rh-parahippocampal"),
    "bi_fusiform":                 ("ctx-lh-fusiform",                "ctx-rh-fusiform"),
    "bi_inferiortemporal":         ("ctx-lh-inferiortemporal",        "ctx-rh-inferiortemporal"),
    "bi_middletemporal":           ("ctx-lh-middletemporal",          "ctx-rh-middletemporal"),
    "bi_superiortemporal":         ("ctx-lh-superiortemporal",        "ctx-rh-superiortemporal"),
    "bi_inferiorparietal":         ("ctx-lh-inferiorparietal",        "ctx-rh-inferiorparietal"),
    "bi_superiorparietal":         ("ctx-lh-superiorparietal",        "ctx-rh-superiorparietal"),
    "bi_supramarginal":            ("ctx-lh-supramarginal",           "ctx-rh-supramarginal"),
    "bi_precuneus":                ("ctx-lh-precuneus",               "ctx-rh-precuneus"),
    "bi_isthmuscingulate":         ("ctx-lh-isthmuscingulate",        "ctx-rh-isthmuscingulate"),
    "bi_posteriorcingulate":       ("ctx-lh-posteriorcingulate",      "ctx-rh-posteriorcingulate"),
    "bi_caudalanteriorcingulate":  ("ctx-lh-caudalanteriorcingulate", "ctx-rh-caudalanteriorcingulate"),
    "bi_rostralanteriorcingulate": ("ctx-lh-rostralanteriorcingulate","ctx-rh-rostralanteriorcingulate"),
    "bi_lateraloccipital":         ("ctx-lh-lateraloccipital",        "ctx-rh-lateraloccipital"),
    "bi_lingual":                  ("ctx-lh-lingual",                 "ctx-rh-lingual"),
    "bi_cuneus":                   ("ctx-lh-cuneus",                  "ctx-rh-cuneus"),
    "bi_pericalcarine":            ("ctx-lh-pericalcarine",           "ctx-rh-pericalcarine"),
    "bi_insula":                   ("ctx-lh-insula",                  "ctx-rh-insula"),
    "bi_superiorfrontal":          ("ctx-lh-superiorfrontal",         "ctx-rh-superiorfrontal"),
    "bi_rostralmiddlefrontal":     ("ctx-lh-rostralmiddlefrontal",    "ctx-rh-rostralmiddlefrontal"),
    "bi_caudalmiddlefrontal":      ("ctx-lh-caudalmiddlefrontal",     "ctx-rh-caudalmiddlefrontal"),
    "bi_lateralorbitofrontal":     ("ctx-lh-lateralorbitofrontal",    "ctx-rh-lateralorbitofrontal"),
    "bi_medialorbitofrontal":      ("ctx-lh-medialorbitofrontal",     "ctx-rh-medialorbitofrontal"),
    "bi_parsopercularis":          ("ctx-lh-parsopercularis",         "ctx-rh-parsopercularis"),
    "bi_parstriangularis":         ("ctx-lh-parstriangularis",        "ctx-rh-parstriangularis"),
    "bi_parsorbitalis":            ("ctx-lh-parsorbitalis",           "ctx-rh-parsorbitalis"),
    "bi_precentral":               ("ctx-lh-precentral",              "ctx-rh-precentral"),
    "bi_postcentral":              ("ctx-lh-postcentral",             "ctx-rh-postcentral"),
    "bi_paracentral":              ("ctx-lh-paracentral",             "ctx-rh-paracentral"),
    "bi_bankssts":                 ("ctx-lh-bankssts",                "ctx-rh-bankssts"),
    "bi_transversetemporal":       ("ctx-lh-transversetemporal",      "ctx-rh-transversetemporal"),
    "bi_temporalpole":             ("ctx-lh-temporalpole",            "ctx-rh-temporalpole"),
    "bi_frontalpole":              ("ctx-lh-frontalpole",             "ctx-rh-frontalpole"),
}

REF_REGIONS = ("Left-Cerebellum-Cortex", "Right-Cerebellum-Cortex")

# ── A4 column mappings ────────────────────────────────────────────────────────
STRUCT_TO_A4_MEAN = {
    "3rd-Ventricle":                  "Mean_3rd_Ventricle",
    "4th-Ventricle":                  "Mean_4th_Ventricle",
    "Brain-Stem":                     "Mean_Brain_Stem",
    "Optic-Chiasm":                   "Mean_Optic_Chiasm",
    "WM-hypointensities":             "Mean_WM_hypointensities",
    "Left-Lateral-Ventricle":         "Mean_Left_Lateral_Ventricle",
    "Right-Lateral-Ventricle":        "Mean_Right_Lateral_Ventricle",
    "Left-Inf-Lat-Vent":              "Mean_Left_Inf_Lat_Vent",
    "Right-Inf-Lat-Vent":             "Mean_Right_Inf_Lat_Vent",
    "Left-Cerebral-White-Matter":     "Mean_Left_Cerebral_White_Matter",
    "Right-Cerebral-White-Matter":    "Mean_Right_Cerebral_White_Matter",
    "Left-Cerebellum-White-Matter":   "Mean_Left_Cerebellum_White_Matter",
    "Right-Cerebellum-White-Matter":  "Mean_Right_Cerebellum_White_Matter",
    "Left-Cerebellum-Cortex":         "Mean_Left_Cerebellum_Cortex",
    "Right-Cerebellum-Cortex":        "Mean_Right_Cerebellum_Cortex",
    "Left-Thalamus":                  "Mean_Left_Thalamus",
    "Right-Thalamus":                 "Mean_Right_Thalamus",
    "Left-Caudate":                   "Mean_Left_Caudate",
    "Right-Caudate":                  "Mean_Right_Caudate",
    "Left-Putamen":                   "Mean_Left_Putamen",
    "Right-Putamen":                  "Mean_Right_Putamen",
    "Left-Pallidum":                  "Mean_Left_Pallidum",
    "Right-Pallidum":                 "Mean_Right_Pallidum",
    "Left-Hippocampus":               "Mean_Left_Hippocampus",
    "Right-Hippocampus":              "Mean_Right_Hippocampus",
    "Left-Amygdala":                  "Mean_Left_Amygdala",
    "Right-Amygdala":                 "Mean_Right_Amygdala",
    "Left-Accumbens-area":            "Mean_Left_Accumbens_area",
    "Right-Accumbens-area":           "Mean_Right_Accumbens_area",
    "Left-VentralDC":                 "Mean_Left_VentralDC",
    "Right-VentralDC":                "Mean_Right_VentralDC",
    "Left-choroid-plexus":            "Mean_Left_choroid_plexus",
    "Right-choroid-plexus":           "Mean_Right_choroid_plexus",
    "ctx-lh-bankssts":                "Mean_ctx_lh_bankssts",
    "ctx-lh-caudalanteriorcingulate": "Mean_ctx_lh_caudalanteriorcingulate",
    "ctx-lh-caudalmiddlefrontal":     "Mean_ctx_lh_caudalmiddlefrontal",
    "ctx-lh-cuneus":                  "Mean_ctx_lh_cuneus",
    "ctx-lh-entorhinal":              "Mean_ctx_lh_entorhinal",
    "ctx-lh-fusiform":                "Mean_ctx_lh_fusiform",
    "ctx-lh-inferiorparietal":        "Mean_ctx_lh_inferiorparietal",
    "ctx-lh-inferiortemporal":        "Mean_ctx_lh_inferiortemporal",
    "ctx-lh-isthmuscingulate":        "Mean_ctx_lh_isthmuscingulate",
    "ctx-lh-lateraloccipital":        "Mean_ctx_lh_lateraloccipital",
    "ctx-lh-lateralorbitofrontal":    "Mean_ctx_lh_lateralorbitofrontal",
    "ctx-lh-lingual":                 "Mean_ctx_lh_lingual",
    "ctx-lh-medialorbitofrontal":     "Mean_ctx_lh_medialorbitofrontal",
    "ctx-lh-middletemporal":          "Mean_ctx_lh_middletemporal",
    "ctx-lh-parahippocampal":         "Mean_ctx_lh_parahippocampal",
    "ctx-lh-paracentral":             "Mean_ctx_lh_paracentral",
    "ctx-lh-parsopercularis":         "Mean_ctx_lh_parsopercularis",
    "ctx-lh-parsorbitalis":           "Mean_ctx_lh_parsorbitalis",
    "ctx-lh-parstriangularis":        "Mean_ctx_lh_parstriangularis",
    "ctx-lh-pericalcarine":           "Mean_ctx_lh_pericalcarine",
    "ctx-lh-postcentral":             "Mean_ctx_lh_postcentral",
    "ctx-lh-posteriorcingulate":      "Mean_ctx_lh_posteriorcingulate",
    "ctx-lh-precentral":              "Mean_ctx_lh_precentral",
    "ctx-lh-precuneus":               "Mean_ctx_lh_precuneus",
    "ctx-lh-rostralanteriorcingulate":"Mean_ctx_lh_rostralanteriorcingulate",
    "ctx-lh-rostralmiddlefrontal":    "Mean_ctx_lh_rostralmiddlefrontal",
    "ctx-lh-superiorfrontal":         "Mean_ctx_lh_superiorfrontal",
    "ctx-lh-superiorparietal":        "Mean_ctx_lh_superiorparietal",
    "ctx-lh-superiortemporal":        "Mean_ctx_lh_superiortemporal",
    "ctx-lh-supramarginal":           "Mean_ctx_lh_supramarginal",
    "ctx-lh-frontalpole":             "Mean_ctx_lh_frontalpole",
    "ctx-lh-temporalpole":            "Mean_ctx_lh_temporalpole",
    "ctx-lh-transversetemporal":      "Mean_ctx_lh_transversetemporal",
    "ctx-lh-insula":                  "Mean_ctx_lh_insula",
    "ctx-rh-bankssts":                "Mean_ctx_rh_bankssts",
    "ctx-rh-caudalanteriorcingulate": "Mean_ctx_rh_caudalanteriorcingulate",
    "ctx-rh-caudalmiddlefrontal":     "Mean_ctx_rh_caudalmiddlefrontal",
    "ctx-rh-cuneus":                  "Mean_ctx_rh_cuneus",
    "ctx-rh-entorhinal":              "Mean_ctx_rh_entorhinal",
    "ctx-rh-fusiform":                "Mean_ctx_rh_fusiform",
    "ctx-rh-inferiorparietal":        "Mean_ctx_rh_inferiorparietal",
    "ctx-rh-inferiortemporal":        "Mean_ctx_rh_inferiortemporal",
    "ctx-rh-isthmuscingulate":        "Mean_ctx_rh_isthmuscingulate",
    "ctx-rh-lateraloccipital":        "Mean_ctx_rh_lateraloccipital",
    "ctx-rh-lateralorbitofrontal":    "Mean_ctx_rh_lateralorbitofrontal",
    "ctx-rh-lingual":                 "Mean_ctx_rh_lingual",
    "ctx-rh-medialorbitofrontal":     "Mean_ctx_rh_medialorbitofrontal",
    "ctx-rh-middletemporal":          "Mean_ctx_rh_middletemporal",
    "ctx-rh-parahippocampal":         "Mean_ctx_rh_parahippocampal",
    "ctx-rh-paracentral":             "Mean_ctx_rh_paracentral",
    "ctx-rh-parsopercularis":         "Mean_ctx_rh_parsopercularis",
    "ctx-rh-parsorbitalis":           "Mean_ctx_rh_parsorbitalis",
    "ctx-rh-parstriangularis":        "Mean_ctx_rh_parstriangularis",
    "ctx-rh-pericalcarine":           "Mean_ctx_rh_pericalcarine",
    "ctx-rh-postcentral":             "Mean_ctx_rh_postcentral",
    "ctx-rh-posteriorcingulate":      "Mean_ctx_rh_posteriorcingulate",
    "ctx-rh-precentral":              "Mean_ctx_rh_precentral",
    "ctx-rh-precuneus":               "Mean_ctx_rh_precuneus",
    "ctx-rh-rostralanteriorcingulate":"Mean_ctx_rh_rostralanteriorcingulate",
    "ctx-rh-rostralmiddlefrontal":    "Mean_ctx_rh_rostralmiddlefrontal",
    "ctx-rh-superiorfrontal":         "Mean_ctx_rh_superiorfrontal",
    "ctx-rh-superiorparietal":        "Mean_ctx_rh_superiorparietal",
    "ctx-rh-superiortemporal":        "Mean_ctx_rh_superiortemporal",
    "ctx-rh-supramarginal":           "Mean_ctx_rh_supramarginal",
    "ctx-rh-frontalpole":             "Mean_ctx_rh_frontalpole",
    "ctx-rh-temporalpole":            "Mean_ctx_rh_temporalpole",
    "ctx-rh-transversetemporal":      "Mean_ctx_rh_transversetemporal",
    "ctx-rh-insula":                  "Mean_ctx_rh_insula",
}

STRUCT_TO_A4_PVC = {
    "Brain-Stem":                     "PVC_Brain_Stem",
    "Left-Cerebral-White-Matter":     "PVC_Left_Cerebral_White_Matter",
    "Right-Cerebral-White-Matter":    "PVC_Right_Cerebral_White_Matter",
    "Left-Cerebellum-White-Matter":   "PVC_Left_Cerebellum_White_Matter",
    "Right-Cerebellum-White-Matter":  "PVC_Right_Cerebellum_White_Matter",
    "Left-Cerebellum-Cortex":         "PVC_Left_Cerebellum_Cortex",
    "Right-Cerebellum-Cortex":        "PVC_Right_Cerebellum_Cortex",
    "Left-Thalamus":                  "PVC_Left_Thalamus",
    "Right-Thalamus":                 "PVC_Right_Thalamus",
    "Left-Caudate":                   "PVC_Left_Caudate",
    "Right-Caudate":                  "PVC_Right_Caudate",
    "Left-Putamen":                   "PVC_Left_Putamen",
    "Right-Putamen":                  "PVC_Right_Putamen",
    "Left-Pallidum":                  "PVC_Left_Pallidum",
    "Right-Pallidum":                 "PVC_Right_Pallidum",
    "Left-Hippocampus":               "PVC_Left_Hippocampus",
    "Right-Hippocampus":              "PVC_Right_Hippocampus",
    "Left-Amygdala":                  "PVC_Left_Amygdala",
    "Right-Amygdala":                 "PVC_Right_Amygdala",
    "Left-Accumbens-area":            "PVC_Left_Accumbens_area",
    "Right-Accumbens-area":           "PVC_Right_Accumbens_area",
    "Left-VentralDC":                 "PVC_Left_VentralDC",
    "Right-VentralDC":                "PVC_Right_VentralDC",
    "Left-choroid-plexus":            "PVC_Left_choroid_plexus",
    "Right-choroid-plexus":           "PVC_Right_choroid_plexus",
    "ctx-lh-bankssts":                "PVC_ctx_lh_bankssts",
    "ctx-lh-caudalanteriorcingulate": "PVC_ctx_lh_caudalanteriorcingulate",
    "ctx-lh-caudalmiddlefrontal":     "PVC_ctx_lh_caudalmiddlefrontal",
    "ctx-lh-cuneus":                  "PVC_ctx_lh_cuneus",
    "ctx-lh-entorhinal":              "PVC_ctx_lh_entorhinal",
    "ctx-lh-fusiform":                "PVC_ctx_lh_fusiform",
    "ctx-lh-inferiorparietal":        "PVC_ctx_lh_inferiorparietal",
    "ctx-lh-inferiortemporal":        "PVC_ctx_lh_inferiortemporal",
    "ctx-lh-isthmuscingulate":        "PVC_ctx_lh_isthmuscingulate",
    "ctx-lh-lateraloccipital":        "PVC_ctx_lh_lateraloccipital",
    "ctx-lh-lateralorbitofrontal":    "PVC_ctx_lh_lateralorbitofrontal",
    "ctx-lh-lingual":                 "PVC_ctx_lh_lingual",
    "ctx-lh-medialorbitofrontal":     "PVC_ctx_lh_medialorbitofrontal",
    "ctx-lh-middletemporal":          "PVC_ctx_lh_middletemporal",
    "ctx-lh-parahippocampal":         "PVC_ctx_lh_parahippocampal",
    "ctx-lh-paracentral":             "PVC_ctx_lh_paracentral",
    "ctx-lh-parsopercularis":         "PVC_ctx_lh_parsopercularis",
    "ctx-lh-parsorbitalis":           "PVC_ctx_lh_parsorbitalis",
    "ctx-lh-parstriangularis":        "PVC_ctx_lh_parstriangularis",
    "ctx-lh-pericalcarine":           "PVC_ctx_lh_pericalcarine",
    "ctx-lh-postcentral":             "PVC_ctx_lh_postcentral",
    "ctx-lh-posteriorcingulate":      "PVC_ctx_lh_posteriorcingulate",
    "ctx-lh-precentral":              "PVC_ctx_lh_precentral",
    "ctx-lh-precuneus":               "PVC_ctx_lh_precuneus",
    "ctx-lh-rostralanteriorcingulate":"PVC_ctx_lh_rostralanteriorcingulate",
    "ctx-lh-rostralmiddlefrontal":    "PVC_ctx_lh_rostralmiddlefrontal",
    "ctx-lh-superiorfrontal":         "PVC_ctx_lh_superiorfrontal",
    "ctx-lh-superiorparietal":        "PVC_ctx_lh_superiorparietal",
    "ctx-lh-superiortemporal":        "PVC_ctx_lh_superiortemporal",
    "ctx-lh-supramarginal":           "PVC_ctx_lh_supramarginal",
    "ctx-lh-frontalpole":             "PVC_ctx_lh_frontalpole",
    "ctx-lh-temporalpole":            "PVC_ctx_lh_temporalpole",
    "ctx-lh-transversetemporal":      "PVC_ctx_lh_transversetemporal",
    "ctx-lh-insula":                  "PVC_ctx_lh_insula",
    "ctx-rh-bankssts":                "PVC_ctx_rh_bankssts",
    "ctx-rh-caudalanteriorcingulate": "PVC_ctx_rh_caudalanteriorcingulate",
    "ctx-rh-caudalmiddlefrontal":     "PVC_ctx_rh_caudalmiddlefrontal",
    "ctx-rh-cuneus":                  "PVC_ctx_rh_cuneus",
    "ctx-rh-entorhinal":              "PVC_ctx_rh_entorhinal",
    "ctx-rh-fusiform":                "PVC_ctx_rh_fusiform",
    "ctx-rh-inferiorparietal":        "PVC_ctx_rh_inferiorparietal",
    "ctx-rh-inferiortemporal":        "PVC_ctx_rh_inferiortemporal",
    "ctx-rh-isthmuscingulate":        "PVC_ctx_rh_isthmuscingulate",
    "ctx-rh-lateraloccipital":        "PVC_ctx_rh_lateraloccipital",
    "ctx-rh-lateralorbitofrontal":    "PVC_ctx_rh_lateralorbitofrontal",
    "ctx-rh-lingual":                 "PVC_ctx_rh_lingual",
    "ctx-rh-medialorbitofrontal":     "PVC_ctx_rh_medialorbitofrontal",
    "ctx-rh-middletemporal":          "PVC_ctx_rh_middletemporal",
    "ctx-rh-parahippocampal":         "PVC_ctx_rh_parahippocampal",
    "ctx-rh-paracentral":             "PVC_ctx_rh_paracentral",
    "ctx-rh-parsopercularis":         "PVC_ctx_rh_parsopercularis",
    "ctx-rh-parsorbitalis":           "PVC_ctx_rh_parsorbitalis",
    "ctx-rh-parstriangularis":        "PVC_ctx_rh_parstriangularis",
    "ctx-rh-pericalcarine":           "PVC_ctx_rh_pericalcarine",
    "ctx-rh-postcentral":             "PVC_ctx_rh_postcentral",
    "ctx-rh-posteriorcingulate":      "PVC_ctx_rh_posteriorcingulate",
    "ctx-rh-precentral":              "PVC_ctx_rh_precentral",
    "ctx-rh-precuneus":               "PVC_ctx_rh_precuneus",
    "ctx-rh-rostralanteriorcingulate":"PVC_ctx_rh_rostralanteriorcingulate",
    "ctx-rh-rostralmiddlefrontal":    "PVC_ctx_rh_rostralmiddlefrontal",
    "ctx-rh-superiorfrontal":         "PVC_ctx_rh_superiorfrontal",
    "ctx-rh-superiorparietal":        "PVC_ctx_rh_superiorparietal",
    "ctx-rh-superiortemporal":        "PVC_ctx_rh_superiortemporal",
    "ctx-rh-supramarginal":           "PVC_ctx_rh_supramarginal",
    "ctx-rh-frontalpole":             "PVC_ctx_rh_frontalpole",
    "ctx-rh-temporalpole":            "PVC_ctx_rh_temporalpole",
    "ctx-rh-transversetemporal":      "PVC_ctx_rh_transversetemporal",
    "ctx-rh-insula":                  "PVC_ctx_rh_insula",
}

STRUCT_TO_A4_VOL = {
    "3rd-Ventricle":                  "Volume_mm3_3rd_Ventricle",
    "4th-Ventricle":                  "Volume_mm3_4th_Ventricle",
    "Brain-Stem":                     "Volume_mm3_Brain_Stem",
    "Optic-Chiasm":                   "Volume_mm3_Optic_Chiasm",
    "WM-hypointensities":             "Volume_mm3_WM_hypointensities",
    "Left-Lateral-Ventricle":         "Volume_mm3_Left_Lateral_Ventricle",
    "Right-Lateral-Ventricle":        "Volume_mm3_Right_Lateral_Ventricle",
    "Left-Inf-Lat-Vent":              "Volume_mm3_Left_Inf_Lat_Vent",
    "Right-Inf-Lat-Vent":             "Volume_mm3_Right_Inf_Lat_Vent",
    "Left-Cerebral-White-Matter":     "Volume_mm3_Left_Cerebral_White_Matter",
    "Right-Cerebral-White-Matter":    "Volume_mm3_Right_Cerebral_White_Matter",
    "Left-Cerebellum-White-Matter":   "Volume_mm3_Left_Cerebellum_White_Matter",
    "Right-Cerebellum-White-Matter":  "Volume_mm3_Right_Cerebellum_White_Matter",
    "Left-Cerebellum-Cortex":         "Volume_mm3_Left_Cerebellum_Cortex",
    "Right-Cerebellum-Cortex":        "Volume_mm3_Right_Cerebellum_Cortex",
    "Left-Thalamus":                  "Volume_mm3_Left_Thalamus",
    "Right-Thalamus":                 "Volume_mm3_Right_Thalamus",
    "Left-Caudate":                   "Volume_mm3_Left_Caudate",
    "Right-Caudate":                  "Volume_mm3_Right_Caudate",
    "Left-Putamen":                   "Volume_mm3_Left_Putamen",
    "Right-Putamen":                  "Volume_mm3_Right_Putamen",
    "Left-Pallidum":                  "Volume_mm3_Left_Pallidum",
    "Right-Pallidum":                 "Volume_mm3_Right_Pallidum",
    "Left-Hippocampus":               "Volume_mm3_Left_Hippocampus",
    "Right-Hippocampus":              "Volume_mm3_Right_Hippocampus",
    "Left-Amygdala":                  "Volume_mm3_Left_Amygdala",
    "Right-Amygdala":                 "Volume_mm3_Right_Amygdala",
    "Left-Accumbens-area":            "Volume_mm3_Left_Accumbens_area",
    "Right-Accumbens-area":           "Volume_mm3_Right_Accumbens_area",
    "Left-VentralDC":                 "Volume_mm3_Left_VentralDC",
    "Right-VentralDC":                "Volume_mm3_Right_VentralDC",
    "Left-choroid-plexus":            "Volume_mm3_Left_choroid_plexus",
    "Right-choroid-plexus":           "Volume_mm3_Right_choroid_plexus",
    "ctx-lh-bankssts":                "Volume_mm3_ctx_lh_bankssts",
    "ctx-lh-caudalanteriorcingulate": "Volume_mm3_ctx_lh_caudalanteriorcingulate",
    "ctx-lh-caudalmiddlefrontal":     "Volume_mm3_ctx_lh_caudalmiddlefrontal",
    "ctx-lh-cuneus":                  "Volume_mm3_ctx_lh_cuneus",
    "ctx-lh-entorhinal":              "Volume_mm3_ctx_lh_entorhinal",
    "ctx-lh-fusiform":                "Volume_mm3_ctx_lh_fusiform",
    "ctx-lh-inferiorparietal":        "Volume_mm3_ctx_lh_inferiorparietal",
    "ctx-lh-inferiortemporal":        "Volume_mm3_ctx_lh_inferiortemporal",
    "ctx-lh-isthmuscingulate":        "Volume_mm3_ctx_lh_isthmuscingulate",
    "ctx-lh-lateraloccipital":        "Volume_mm3_ctx_lh_lateraloccipital",
    "ctx-lh-lateralorbitofrontal":    "Volume_mm3_ctx_lh_lateralorbitofrontal",
    "ctx-lh-lingual":                 "Volume_mm3_ctx_lh_lingual",
    "ctx-lh-medialorbitofrontal":     "Volume_mm3_ctx_lh_medialorbitofrontal",
    "ctx-lh-middletemporal":          "Volume_mm3_ctx_lh_middletemporal",
    "ctx-lh-parahippocampal":         "Volume_mm3_ctx_lh_parahippocampal",
    "ctx-lh-paracentral":             "Volume_mm3_ctx_lh_paracentral",
    "ctx-lh-parsopercularis":         "Volume_mm3_ctx_lh_parsopercularis",
    "ctx-lh-parsorbitalis":           "Volume_mm3_ctx_lh_parsorbitalis",
    "ctx-lh-parstriangularis":        "Volume_mm3_ctx_lh_parstriangularis",
    "ctx-lh-pericalcarine":           "Volume_mm3_ctx_lh_pericalcarine",
    "ctx-lh-postcentral":             "Volume_mm3_ctx_lh_postcentral",
    "ctx-lh-posteriorcingulate":      "Volume_mm3_ctx_lh_posteriorcingulate",
    "ctx-lh-precentral":              "Volume_mm3_ctx_lh_precentral",
    "ctx-lh-precuneus":               "Volume_mm3_ctx_lh_precuneus",
    "ctx-lh-rostralanteriorcingulate":"Volume_mm3_ctx_lh_rostralanteriorcingulate",
    "ctx-lh-rostralmiddlefrontal":    "Volume_mm3_ctx_lh_rostralmiddlefrontal",
    "ctx-lh-superiorfrontal":         "Volume_mm3_ctx_lh_superiorfrontal",
    "ctx-lh-superiorparietal":        "Volume_mm3_ctx_lh_superiorparietal",
    "ctx-lh-superiortemporal":        "Volume_mm3_ctx_lh_superiortemporal",
    "ctx-lh-supramarginal":           "Volume_mm3_ctx_lh_supramarginal",
    "ctx-lh-frontalpole":             "Volume_mm3_ctx_lh_frontalpole",
    "ctx-lh-temporalpole":            "Volume_mm3_ctx_lh_temporalpole",
    "ctx-lh-transversetemporal":      "Volume_mm3_ctx_lh_transversetemporal",
    "ctx-lh-insula":                  "Volume_mm3_ctx_lh_insula",
    "ctx-rh-bankssts":                "Volume_mm3_ctx_rh_bankssts",
    "ctx-rh-caudalanteriorcingulate": "Volume_mm3_ctx_rh_caudalanteriorcingulate",
    "ctx-rh-caudalmiddlefrontal":     "Volume_mm3_ctx_rh_caudalmiddlefrontal",
    "ctx-rh-cuneus":                  "Volume_mm3_ctx_rh_cuneus",
    "ctx-rh-entorhinal":              "Volume_mm3_ctx_rh_entorhinal",
    "ctx-rh-fusiform":                "Volume_mm3_ctx_rh_fusiform",
    "ctx-rh-inferiorparietal":        "Volume_mm3_ctx_rh_inferiorparietal",
    "ctx-rh-inferiortemporal":        "Volume_mm3_ctx_rh_inferiortemporal",
    "ctx-rh-isthmuscingulate":        "Volume_mm3_ctx_rh_isthmuscingulate",
    "ctx-rh-lateraloccipital":        "Volume_mm3_ctx_rh_lateraloccipital",
    "ctx-rh-lateralorbitofrontal":    "Volume_mm3_ctx_rh_lateralorbitofrontal",
    "ctx-rh-lingual":                 "Volume_mm3_ctx_rh_lingual",
    "ctx-rh-medialorbitofrontal":     "Volume_mm3_ctx_rh_medialorbitofrontal",
    "ctx-rh-middletemporal":          "Volume_mm3_ctx_rh_middletemporal",
    "ctx-rh-parahippocampal":         "Volume_mm3_ctx_rh_parahippocampal",
    "ctx-rh-paracentral":             "Volume_mm3_ctx_rh_paracentral",
    "ctx-rh-parsopercularis":         "Volume_mm3_ctx_rh_parsopercularis",
    "ctx-rh-parsorbitalis":           "Volume_mm3_ctx_rh_parsorbitalis",
    "ctx-rh-parstriangularis":        "Volume_mm3_ctx_rh_parstriangularis",
    "ctx-rh-pericalcarine":           "Volume_mm3_ctx_rh_pericalcarine",
    "ctx-rh-postcentral":             "Volume_mm3_ctx_rh_postcentral",
    "ctx-rh-posteriorcingulate":      "Volume_mm3_ctx_rh_posteriorcingulate",
    "ctx-rh-precentral":              "Volume_mm3_ctx_rh_precentral",
    "ctx-rh-precuneus":               "Volume_mm3_ctx_rh_precuneus",
    "ctx-rh-rostralanteriorcingulate":"Volume_mm3_ctx_rh_rostralanteriorcingulate",
    "ctx-rh-rostralmiddlefrontal":    "Volume_mm3_ctx_rh_rostralmiddlefrontal",
    "ctx-rh-superiorfrontal":         "Volume_mm3_ctx_rh_superiorfrontal",
    "ctx-rh-superiorparietal":        "Volume_mm3_ctx_rh_superiorparietal",
    "ctx-rh-superiortemporal":        "Volume_mm3_ctx_rh_superiortemporal",
    "ctx-rh-supramarginal":           "Volume_mm3_ctx_rh_supramarginal",
    "ctx-rh-frontalpole":             "Volume_mm3_ctx_rh_frontalpole",
    "ctx-rh-temporalpole":            "Volume_mm3_ctx_rh_temporalpole",
    "ctx-rh-transversetemporal":      "Volume_mm3_ctx_rh_transversetemporal",
    "ctx-rh-insula":                  "Volume_mm3_ctx_rh_insula",
}

STRUCT_TO_A4_NVOX = {
    "Brain-Stem":                     "NumVoxels_Brain_Stem",
    "Left-Cerebral-White-Matter":     "NumVoxels_Left_Cerebral_White_Matter",
    "Right-Cerebral-White-Matter":    "NumVoxels_Right_Cerebral_White_Matter",
    "Left-Cerebellum-White-Matter":   "NumVoxels_Left_Cerebellum_White_Matter",
    "Right-Cerebellum-White-Matter":  "NumVoxels_Right_Cerebellum_White_Matter",
    "Left-Cerebellum-Cortex":         "NumVoxels_Left_Cerebellum_Cortex",
    "Right-Cerebellum-Cortex":        "NumVoxels_Right_Cerebellum_Cortex",
    "Left-Thalamus":                  "NumVoxels_Left_Thalamus",
    "Right-Thalamus":                 "NumVoxels_Right_Thalamus",
    "Left-Caudate":                   "NumVoxels_Left_Caudate",
    "Right-Caudate":                  "NumVoxels_Right_Caudate",
    "Left-Putamen":                   "NumVoxels_Left_Putamen",
    "Right-Putamen":                  "NumVoxels_Right_Putamen",
    "Left-Pallidum":                  "NumVoxels_Left_Pallidum",
    "Right-Pallidum":                 "NumVoxels_Right_Pallidum",
    "Left-Hippocampus":               "NumVoxels_Left_Hippocampus",
    "Right-Hippocampus":              "NumVoxels_Right_Hippocampus",
    "Left-Amygdala":                  "NumVoxels_Left_Amygdala",
    "Right-Amygdala":                 "NumVoxels_Right_Amygdala",
    "Left-Accumbens-area":            "NumVoxels_Left_Accumbens_area",
    "Right-Accumbens-area":           "NumVoxels_Right_Accumbens_area",
    "Left-VentralDC":                 "NumVoxels_Left_VentralDC",
    "Right-VentralDC":                "NumVoxels_Right_VentralDC",
    "Left-choroid-plexus":            "NumVoxels_Left_choroid_plexus",
    "Right-choroid-plexus":           "NumVoxels_Right_choroid_plexus",
    "ctx-lh-bankssts":                "NumVoxels_ctx_lh_bankssts",
    "ctx-lh-caudalanteriorcingulate": "NumVoxels_ctx_lh_caudalanteriorcingulate",
    "ctx-lh-caudalmiddlefrontal":     "NumVoxels_ctx_lh_caudalmiddlefrontal",
    "ctx-lh-cuneus":                  "NumVoxels_ctx_lh_cuneus",
    "ctx-lh-entorhinal":              "NumVoxels_ctx_lh_entorhinal",
    "ctx-lh-fusiform":                "NumVoxels_ctx_lh_fusiform",
    "ctx-lh-inferiorparietal":        "NumVoxels_ctx_lh_inferiorparietal",
    "ctx-lh-inferiortemporal":        "NumVoxels_ctx_lh_inferiortemporal",
    "ctx-lh-isthmuscingulate":        "NumVoxels_ctx_lh_isthmuscingulate",
    "ctx-lh-lateraloccipital":        "NumVoxels_ctx_lh_lateraloccipital",
    "ctx-lh-lateralorbitofrontal":    "NumVoxels_ctx_lh_lateralorbitofrontal",
    "ctx-lh-lingual":                 "NumVoxels_ctx_lh_lingual",
    "ctx-lh-medialorbitofrontal":     "NumVoxels_ctx_lh_medialorbitofrontal",
    "ctx-lh-middletemporal":          "NumVoxels_ctx_lh_middletemporal",
    "ctx-lh-parahippocampal":         "NumVoxels_ctx_lh_parahippocampal",
    "ctx-lh-paracentral":             "NumVoxels_ctx_lh_paracentral",
    "ctx-lh-parsopercularis":         "NumVoxels_ctx_lh_parsopercularis",
    "ctx-lh-parsorbitalis":           "NumVoxels_ctx_lh_parsorbitalis",
    "ctx-lh-parstriangularis":        "NumVoxels_ctx_lh_parstriangularis",
    "ctx-lh-pericalcarine":           "NumVoxels_ctx_lh_pericalcarine",
    "ctx-lh-postcentral":             "NumVoxels_ctx_lh_postcentral",
    "ctx-lh-posteriorcingulate":      "NumVoxels_ctx_lh_posteriorcingulate",
    "ctx-lh-precentral":              "NumVoxels_ctx_lh_precentral",
    "ctx-lh-precuneus":               "NumVoxels_ctx_lh_precuneus",
    "ctx-lh-rostralanteriorcingulate":"NumVoxels_ctx_lh_rostralanteriorcingulate",
    "ctx-lh-rostralmiddlefrontal":    "NumVoxels_ctx_lh_rostralmiddlefrontal",
    "ctx-lh-superiorfrontal":         "NumVoxels_ctx_lh_superiorfrontal",
    "ctx-lh-superiorparietal":        "NumVoxels_ctx_lh_superiorparietal",
    "ctx-lh-superiortemporal":        "NumVoxels_ctx_lh_superiortemporal",
    "ctx-lh-supramarginal":           "NumVoxels_ctx_lh_supramarginal",
    "ctx-lh-frontalpole":             "NumVoxels_ctx_lh_frontalpole",
    "ctx-lh-temporalpole":            "NumVoxels_ctx_lh_temporalpole",
    "ctx-lh-transversetemporal":      "NumVoxels_ctx_lh_transversetemporal",
    "ctx-lh-insula":                  "NumVoxels_ctx_lh_insula",
    "ctx-rh-bankssts":                "NumVoxels_ctx_rh_bankssts",
    "ctx-rh-caudalanteriorcingulate": "NumVoxels_ctx_rh_caudalanteriorcingulate",
    "ctx-rh-caudalmiddlefrontal":     "NumVoxels_ctx_rh_caudalmiddlefrontal",
    "ctx-rh-cuneus":                  "NumVoxels_ctx_rh_cuneus",
    "ctx-rh-entorhinal":              "NumVoxels_ctx_rh_entorhinal",
    "ctx-rh-fusiform":                "NumVoxels_ctx_rh_fusiform",
    "ctx-rh-inferiorparietal":        "NumVoxels_ctx_rh_inferiorparietal",
    "ctx-rh-inferiortemporal":        "NumVoxels_ctx_rh_inferiortemporal",
    "ctx-rh-isthmuscingulate":        "NumVoxels_ctx_rh_isthmuscingulate",
    "ctx-rh-lateraloccipital":        "NumVoxels_ctx_rh_lateraloccipital",
    "ctx-rh-lateralorbitofrontal":    "NumVoxels_ctx_rh_lateralorbitofrontal",
    "ctx-rh-lingual":                 "NumVoxels_ctx_rh_lingual",
    "ctx-rh-medialorbitofrontal":     "NumVoxels_ctx_rh_medialorbitofrontal",
    "ctx-rh-middletemporal":          "NumVoxels_ctx_rh_middletemporal",
    "ctx-rh-parahippocampal":         "NumVoxels_ctx_rh_parahippocampal",
    "ctx-rh-paracentral":             "NumVoxels_ctx_rh_paracentral",
    "ctx-rh-parsopercularis":         "NumVoxels_ctx_rh_parsopercularis",
    "ctx-rh-parsorbitalis":           "NumVoxels_ctx_rh_parsorbitalis",
    "ctx-rh-parstriangularis":        "NumVoxels_ctx_rh_parstriangularis",
    "ctx-rh-pericalcarine":           "NumVoxels_ctx_rh_pericalcarine",
    "ctx-rh-postcentral":             "NumVoxels_ctx_rh_postcentral",
    "ctx-rh-posteriorcingulate":      "NumVoxels_ctx_rh_posteriorcingulate",
    "ctx-rh-precentral":              "NumVoxels_ctx_rh_precentral",
    "ctx-rh-precuneus":               "NumVoxels_ctx_rh_precuneus",
    "ctx-rh-rostralanteriorcingulate":"NumVoxels_ctx_rh_rostralanteriorcingulate",
    "ctx-rh-rostralmiddlefrontal":    "NumVoxels_ctx_rh_rostralmiddlefrontal",
    "ctx-rh-superiorfrontal":         "NumVoxels_ctx_rh_superiorfrontal",
    "ctx-rh-superiorparietal":        "NumVoxels_ctx_rh_superiorparietal",
    "ctx-rh-superiortemporal":        "NumVoxels_ctx_rh_superiortemporal",
    "ctx-rh-supramarginal":           "NumVoxels_ctx_rh_supramarginal",
    "ctx-rh-frontalpole":             "NumVoxels_ctx_rh_frontalpole",
    "ctx-rh-temporalpole":            "NumVoxels_ctx_rh_temporalpole",
    "ctx-rh-transversetemporal":      "NumVoxels_ctx_rh_transversetemporal",
    "ctx-rh-insula":                  "NumVoxels_ctx_rh_insula",
}

VOL_THRESHOLD  = 50000
NVOX_THRESHOLD = 15000


# ── loaders ───────────────────────────────────────────────────────────────────

def load_segstats(path):
    result = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 6:
                try:
                    result[parts[4]] = {
                        "nvoxels": float(parts[2]),
                        "volume":  float(parts[3]),
                        "mean":    float(parts[5]),
                    }
                except (ValueError, IndexError):
                    continue
    return result


def load_gtm(path):
    result = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 7:
                try:
                    result[parts[2]] = {
                        "nvoxels": float(parts[4]),
                        "mean":    float(parts[6]),
                    }
                except (ValueError, IndexError):
                    continue
    return result


def load_a4_row(path, subject_id):
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip()
    id_col = next(c for c in df.columns if c.strip().upper() == "ID"
                  or "subject" in c.lower())
    row = df[df[id_col].astype(str).str.strip() == str(subject_id)]
    if row.empty:
        raise ValueError(f"Subject {subject_id} not found in {path}")
    return row.iloc[0]


def normalize_nopvc(seg_dict):
    ref_vals = [seg_dict[r]["mean"]   for r in REF_REGIONS if r in seg_dict]
    ref_vols = [seg_dict[r]["volume"] for r in REF_REGIONS if r in seg_dict]
    if not ref_vals:
        return {s: seg_dict[s]["mean"] for s in seg_dict}
    ref = sum(m * v for m, v in zip(ref_vals, ref_vols)) / sum(ref_vols)
    return {s: seg_dict[s]["mean"] / ref for s in seg_dict}


def compute_bilateral_suvr(seg_norm, seg_raw, a4_row):
    """Bilateral SUVR weighted by Volume_mm3 — no-PVC."""
    # A4 reference: volume-weighted bilateral cerebellar cortex
    a4_ref_lh  = float(a4_row.get("Mean_Left_Cerebellum_Cortex",  1.0))
    a4_ref_rh  = float(a4_row.get("Mean_Right_Cerebellum_Cortex", 1.0))
    a4_vol_lh  = float(a4_row.get("Volume_mm3_Left_Cerebellum_Cortex",  1.0))
    a4_vol_rh  = float(a4_row.get("Volume_mm3_Right_Cerebellum_Cortex", 1.0))
    a4_ref     = (a4_ref_lh * a4_vol_lh + a4_ref_rh * a4_vol_rh) / (a4_vol_lh + a4_vol_rh)

    our_suvr = {}
    a4_suvr  = {}

    for bi_name, (lh, rh) in BILATERAL_REGIONS.items():
        # ours: volume-weighted
        lh_d = seg_raw.get(lh)
        rh_d = seg_raw.get(rh)
        if lh_d and rh_d:
            total_vol = lh_d["volume"] + rh_d["volume"]
            weighted  = (lh_d["mean"] * lh_d["volume"] +
                         rh_d["mean"] * rh_d["volume"]) / total_vol
            ref = seg_norm.get(lh, seg_raw[lh]["mean"]) / seg_raw[lh]["mean"] \
                if lh in seg_raw else 1.0
            # use the normalization factor
            lh_suvr = seg_norm.get(lh)
            rh_suvr = seg_norm.get(rh)
            if lh_suvr and rh_suvr:
                our_suvr[bi_name] = (lh_suvr * lh_d["volume"] +
                                     rh_suvr * rh_d["volume"]) / total_vol
        elif lh_d and lh in seg_norm:
            our_suvr[bi_name] = seg_norm[lh]
        elif rh_d and rh in seg_norm:
            our_suvr[bi_name] = seg_norm[rh]

        # A4: from the bi_ columns
        bi_col = f"bi_{bi_name.replace('bi_', '')}"
        # try direct bi_ column first
        a4_col_bi = f"bi_{bi_name.replace('bi_','')}"
        # A4 stores as bi_Hippocampus etc
        try:
            a4_val = float(a4_row[bi_name])
            a4_suvr[bi_name] = a4_val
        except (KeyError, ValueError, TypeError):
            pass

    return our_suvr, a4_suvr


def compute_bilateral_suvr_gtm(gtm_dict, a4_pvc_row):
    """Bilateral SUVR weighted by NVoxels — PVC."""
    our_suvr = {}
    a4_suvr  = {}

    for bi_name, (lh, rh) in BILATERAL_REGIONS.items():
        lh_d = gtm_dict.get(lh)
        rh_d = gtm_dict.get(rh)
        if lh_d and rh_d:
            total_vox = lh_d["nvoxels"] + rh_d["nvoxels"]
            our_suvr[bi_name] = (lh_d["mean"] * lh_d["nvoxels"] +
                                  rh_d["mean"] * rh_d["nvoxels"]) / total_vox
        elif lh_d:
            our_suvr[bi_name] = lh_d["mean"]
        elif rh_d:
            our_suvr[bi_name] = rh_d["mean"]

        try:
            a4_suvr[bi_name] = float(a4_pvc_row[bi_name])
        except (KeyError, ValueError, TypeError):
            pass

    return our_suvr, a4_suvr


# ── scatter panel ─────────────────────────────────────────────────────────────

def scatter_panel(ax, x_vals, y_vals, labels, xlabel, ylabel, title, color,
                  threshold=None):
    if threshold:
        filtered = [(x, y, l) for x, y, l in zip(x_vals, y_vals, labels)
                    if x > 0 and y > 0 and x < threshold]
        if not filtered:
            return [], [], []
        x_vals, y_vals, labels = zip(*filtered)

    x = np.array(x_vals)
    y = np.array(y_vals)

    # filter negatives
    mask = (x > 0) & (y > 0)
    x, y = x[mask], y[mask]
    labels = [l for l, m in zip(labels, mask) if m]

    if len(x) < 2:
        return list(x), list(y), list(labels)

    ax.scatter(x, y, color=color, s=28, alpha=0.85, zorder=3,
               linewidths=0.5, edgecolors="white")

    all_vals = np.concatenate([x, y])
    vmin = all_vals.min() - 0.05 * abs(all_vals.min())
    vmax = all_vals.max() + 0.05 * abs(all_vals.max())
    ax.set_xlim(vmin, vmax)
    ax.set_ylim(vmin, vmax)
    ax.plot([vmin, vmax], [vmin, vmax], color="gray", linestyle="--",
            linewidth=1.2, alpha=0.7, zorder=2, label="identity")
    ax.set_aspect("equal")

    slope, intercept, r, _, _ = stats.linregress(x, y)
    x_line = np.linspace(vmin, vmax, 200)
    ax.plot(x_line, slope * x_line + intercept, color="#185FA5",
            linewidth=1.8, zorder=4, label=f"r = {r:.3f}")

    mape = np.mean(np.abs(x - y) / (np.abs(x) + 1e-9) * 100)
    ax.text(0.04, 0.96,
            f"r = {r:.3f}\nslope = {slope:.3f}\nMAPE = {mape:.2f}%",
            transform=ax.transAxes, fontsize=8, verticalalignment="top",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                      edgecolor="#cccccc", alpha=0.85))

    ax.set_xlabel(xlabel, fontsize=9)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_title(title, fontsize=10, fontweight="bold", pad=6)
    ax.grid(True, linestyle=":", alpha=0.4, linewidth=0.7)
    ax.tick_params(labelsize=8)
    ax.legend(fontsize=7, loc="lower right")

    return list(x), list(y), list(labels)


# ── interactive HTML ──────────────────────────────────────────────────────────

def generate_html(subject_id, panels_info, out_path):
    panels_data = []
    for p in panels_info:
        if not p["x"]:
            continue
        xa = np.array(p["x"])
        xb = np.array(p["y"])
        slope, intercept, r, _, _ = stats.linregress(xa, xb)
        mape = float(np.mean(np.abs(xa - xb) / (np.abs(xa) + 1e-9) * 100))
        points = [{"label": p["labels"][i],
                   "x": round(float(xa[i]), 4),
                   "y": round(float(xb[i]), 4)}
                  for i in range(len(p["labels"]))]
        vmin = float(min(xa.min(), xb.min())) - 0.05
        vmax = float(max(xa.max(), xb.max())) + 0.05
        panels_data.append({
            "title":  p["title"],
            "xlabel": p["xlabel"],
            "ylabel": p["ylabel"],
            "color":  p["color"],
            "r":      round(float(r), 3),
            "slope":  round(float(slope), 3),
            "mape":   round(mape, 3),
            "vmin":   round(vmin, 4),
            "vmax":   round(vmax, 4),
            "points": points,
            "reg_x":  [round(vmin, 4), round(vmax, 4)],
            "reg_y":  [round(slope * vmin + intercept, 4),
                       round(slope * vmax + intercept, 4)],
        })

    data_json = json.dumps(panels_data)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>4way — {subject_id}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>
  body {{ font-family:system-ui,sans-serif; background:#fff; color:#1a1a1a; padding:24px; }}
  h2 {{ font-size:15px; font-weight:600; margin:0 0 16px; }}
  .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:24px; }}
  .panel-title {{ font-size:13px; font-weight:600; text-align:center; margin-bottom:4px; }}
  .panel-stats {{ font-size:11px; color:#666; text-align:center; margin-bottom:6px; }}
  .canvas-wrap {{ position:relative; width:100%; height:300px; }}
  #tooltip {{
    position:fixed; pointer-events:none; background:#fff; border:1px solid #ddd;
    border-radius:6px; padding:6px 10px; font-size:11px; display:none;
    box-shadow:0 2px 8px rgba(0,0,0,.12); z-index:100; line-height:1.6;
  }}
</style>
</head>
<body>
<h2>Pipeline validation — {subject_id}</h2>
<div id="tooltip"></div>
<div class="grid" id="grid"></div>
<script>
const PANELS = {data_json};
const tooltip = document.getElementById('tooltip');
const grid    = document.getElementById('grid');

PANELS.forEach((p, pi) => {{
  const div = document.createElement('div');
  div.innerHTML = `
    <div class="panel-title">${{p.title}}</div>
    <div class="panel-stats">r=${{p.r}} | slope=${{p.slope}} | MAPE=${{p.mape}}%</div>
    <div class="canvas-wrap"><canvas id="c${{pi}}"></canvas></div>
  `;
  grid.appendChild(div);
  const ctx = document.getElementById('c'+pi).getContext('2d');
  new Chart(ctx, {{
    type:'scatter',
    data:{{ datasets:[
      {{ label:'regions',
         data:p.points.map(pt=>({{x:pt.x,y:pt.y,label:pt.label}})),
         backgroundColor:p.color+'cc', pointRadius:5, pointHoverRadius:7, borderWidth:0 }},
      {{ label:'identity',
         data:[{{x:p.vmin,y:p.vmin}},{{x:p.vmax,y:p.vmax}}],
         type:'line', borderColor:'#aaa', borderWidth:1.5,
         borderDash:[6,4], pointRadius:0, fill:false }},
      {{ label:'regression',
         data:[{{x:p.reg_x[0],y:p.reg_y[0]}},{{x:p.reg_x[1],y:p.reg_y[1]}}],
         type:'line', borderColor:'#185FA5', borderWidth:2,
         pointRadius:0, fill:false }},
    ]}},
    options:{{
      responsive:true, maintainAspectRatio:false, animation:false,
      plugins:{{ legend:{{display:false}}, tooltip:{{enabled:false}} }},
      scales:{{
        x:{{min:p.vmin,max:p.vmax,
            title:{{display:true,text:p.xlabel,font:{{size:11}}}},
            ticks:{{font:{{size:10}}}},grid:{{color:'rgba(0,0,0,.06)'}}}},
        y:{{min:p.vmin,max:p.vmax,
            title:{{display:true,text:p.ylabel,font:{{size:11}}}},
            ticks:{{font:{{size:10}}}},grid:{{color:'rgba(0,0,0,.06)'}}}},
      }},
      onHover:(event,elements)=>{{
        if(elements.length>0 && elements[0].datasetIndex===0){{
          const pt=p.points[elements[0].index];
          const mape=(Math.abs(pt.y-pt.x)/(Math.abs(pt.x)+1e-9)*100).toFixed(1);
          tooltip.style.display='block';
          tooltip.style.left=(event.native.clientX+14)+'px';
          tooltip.style.top=(event.native.clientY-28)+'px';
          tooltip.innerHTML=`
            <strong>${{pt.label}}</strong><br>
            ${{p.xlabel}}: ${{pt.x.toFixed(4)}}<br>
            ${{p.ylabel}}: ${{pt.y.toFixed(4)}}<br>
            MAPE: ${{mape}}%
          `;
        }} else {{ tooltip.style.display='none'; }}
      }},
    }}
  }});
}});
document.addEventListener('mousemove',e=>{{
  if(tooltip.style.display==='block'){{
    tooltip.style.left=(e.clientX+14)+'px';
    tooltip.style.top=(e.clientY-28)+'px';
  }}
}});
</script>
</body>
</html>"""

    with open(out_path, "w") as f:
        f.write(html)
    print(f"HTML saved: {out_path}")


# ── Bland-Altman ──────────────────────────────────────────────────────────────

def bland_altman_stats(a4, ours):
    """Return (bias, loa_lo, loa_hi, diff, mean). Difference = ours - A4."""
    a4   = np.asarray(a4, dtype=float)
    ours = np.asarray(ours, dtype=float)
    diff = ours - a4
    mean = (ours + a4) / 2.0
    bias = np.mean(diff)
    sd   = np.std(diff, ddof=1) if len(diff) > 1 else 0.0
    return bias, bias - 1.96 * sd, bias + 1.96 * sd, diff, mean


def bland_altman_panel(ax, a4, ours, title, color="#534AB7"):
    """Draw a Bland-Altman panel on ax. Difference = ours - A4."""
    bias, lo, hi, diff, mean = bland_altman_stats(a4, ours)
    ax.scatter(mean, diff, s=18, alpha=0.6, color=color, edgecolors="none")
    ax.axhline(bias, color="#333333", lw=1.5, label=f"bias = {bias:+.4f}")
    ax.axhline(hi, color="#B03030", lw=1.0, ls="--", label=f"+1.96 SD = {hi:+.4f}")
    ax.axhline(lo, color="#B03030", lw=1.0, ls="--", label=f"-1.96 SD = {lo:+.4f}")
    ax.axhline(0.0, color="#999999", lw=0.8, ls=":")
    ax.set_xlabel("Mean (A4 + ours) / 2")
    ax.set_ylabel("Difference (ours - A4)")
    ax.set_title(title, fontsize=11)
    ax.legend(fontsize=8, loc="best")
    return bias, lo, hi


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id",         required=True)
    parser.add_argument("--nopvc_ours", required=True, help="output.csv")
    parser.add_argument("--pvc_ours",   required=True, help="gtm.stats.dat")
    parser.add_argument("--nopvc_a4",   required=True, help="TAUSUVR_26Jan2026.csv")
    parser.add_argument("--pvc_a4",     required=True, help="TAUSUVR_PETSURFER_26Jan2026.csv")
    parser.add_argument("--out",        default="4way.png")
    args = parser.parse_args()

    print(f"Loading data for {args.id}...")

    # ── load data ─────────────────────────────────────────────────────────────
    seg_raw  = load_segstats(args.nopvc_ours)
    seg_norm = normalize_nopvc(seg_raw)
    gtm      = load_gtm(args.pvc_ours)
    a4_nopvc = load_a4_row(args.nopvc_a4, args.id)
    a4_pvc   = load_a4_row(args.pvc_a4,   args.id)

    # ── SUVR bilateral ────────────────────────────────────────────────────────
    our_suvr_nopvc, a4_suvr_nopvc = compute_bilateral_suvr(seg_norm, seg_raw, a4_nopvc)
    our_suvr_pvc,   a4_suvr_pvc   = compute_bilateral_suvr_gtm(gtm, a4_pvc)

    common_nopvc = [r for r in BILATERAL_REGIONS
                    if r in our_suvr_nopvc and r in a4_suvr_nopvc]
    common_pvc   = [r for r in BILATERAL_REGIONS
                    if r in our_suvr_pvc   and r in a4_suvr_pvc]

    x_suvr_nopvc_a4  = [a4_suvr_nopvc[r]  for r in common_nopvc]
    y_suvr_nopvc_our = [our_suvr_nopvc[r] for r in common_nopvc]
    x_suvr_pvc_a4    = [a4_suvr_pvc[r]    for r in common_pvc]
    y_suvr_pvc_our   = [our_suvr_pvc[r]   for r in common_pvc]

    print(f"SUVR no-PVC: {len(common_nopvc)} bilateral regions")
    print(f"SUVR PVC:    {len(common_pvc)} bilateral regions")

    # ── Mean intensity ────────────────────────────────────────────────────────
    mean_x, mean_y, mean_labels = [], [], []
    for struct, a4_col in STRUCT_TO_A4_MEAN.items():
        if struct in seg_norm and a4_col in a4_nopvc.index:
            try:
                a4_val  = float(a4_nopvc[a4_col])
                our_val = seg_norm[struct]
                if a4_val > 0 and our_val > 0:
                    mean_x.append(a4_val)
                    mean_y.append(our_val)
                    mean_labels.append(struct)
            except (ValueError, TypeError):
                pass

    pvc_mean_x, pvc_mean_y, pvc_mean_labels = [], [], []
    for struct, pvc_col in STRUCT_TO_A4_PVC.items():
        if struct in gtm and pvc_col in a4_pvc.index:
            try:
                a4_val  = float(a4_pvc[pvc_col])
                our_val = gtm[struct]["mean"]
                if a4_val > 0 and our_val > 0:
                    pvc_mean_x.append(a4_val)
                    pvc_mean_y.append(our_val)
                    pvc_mean_labels.append(struct)
            except (ValueError, TypeError):
                pass

    # ── Volume no-PVC ─────────────────────────────────────────────────────────
    vol_x, vol_y, vol_labels = [], [], []
    for struct, a4_col in STRUCT_TO_A4_VOL.items():
        if struct in seg_raw and a4_col in a4_nopvc.index:
            try:
                a4_val  = float(a4_nopvc[a4_col])
                our_val = seg_raw[struct]["volume"]
                if a4_val > 0 and our_val > 0 and a4_val < VOL_THRESHOLD:
                    vol_x.append(a4_val)
                    vol_y.append(our_val)
                    vol_labels.append(struct)
            except (ValueError, TypeError):
                pass

    # ── NVoxels PVC ───────────────────────────────────────────────────────────
    nvox_x, nvox_y, nvox_labels = [], [], []
    for struct, a4_col in STRUCT_TO_A4_NVOX.items():
        if struct in gtm and a4_col in a4_pvc.index:
            try:
                a4_val  = float(a4_pvc[a4_col])
                our_val = gtm[struct]["nvoxels"]
                if a4_val > 0 and our_val > 0 and a4_val < NVOX_THRESHOLD:
                    nvox_x.append(a4_val)
                    nvox_y.append(our_val)
                    nvox_labels.append(struct)
            except (ValueError, TypeError):
                pass

    print(f"Mean no-PVC: {len(mean_labels)} regions")
    print(f"Mean PVC:    {len(pvc_mean_labels)} regions")
    print(f"Volume:      {len(vol_labels)} regions (< {VOL_THRESHOLD:,} mm³)")
    print(f"NVoxels:     {len(nvox_labels)} regions (< {NVOX_THRESHOLD:,})")

    # ── figure 3x2 ────────────────────────────────────────────────────────────
    fig = plt.figure(figsize=(14, 20))
    fig.suptitle(f"Pipeline validation — {args.id}",
                 fontsize=13, fontweight="bold", y=0.99)

    gs = gridspec.GridSpec(3, 2, figure=fig,
                           hspace=0.40, wspace=0.32,
                           left=0.09, right=0.97,
                           top=0.96, bottom=0.04)

    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[0, 1])
    ax3 = fig.add_subplot(gs[1, 0])
    ax4 = fig.add_subplot(gs[1, 1])
    ax5 = fig.add_subplot(gs[2, 0])
    ax6 = fig.add_subplot(gs[2, 1])

    rx1, ry1, rl1 = scatter_panel(ax1, x_suvr_nopvc_a4, y_suvr_nopvc_our,
                                   common_nopvc,
                                   "A4 SUVR (no PVC)", "Ours SUVR (no PVC)",
                                   f"SUVR no-PVC: ours vs A4  [{len(common_nopvc)} regions]",
                                   color="#D85A30")

    rx2, ry2, rl2 = scatter_panel(ax2, x_suvr_pvc_a4, y_suvr_pvc_our,
                                   common_pvc,
                                   "A4 SUVR (PVC)", "Ours SUVR (PVC)",
                                   f"SUVR PVC: ours vs A4  [{len(common_pvc)} regions]",
                                   color="#534AB7")

    rx3, ry3, rl3 = scatter_panel(ax3, mean_x, mean_y, mean_labels,
                                   "A4 Mean (no PVC)", "Ours Mean (no PVC)",
                                   f"Mean intensity no-PVC  [{len(mean_labels)} regions]",
                                   color="#0F6E56")

    rx4, ry4, rl4 = scatter_panel(ax4, pvc_mean_x, pvc_mean_y, pvc_mean_labels,
                                   "A4 PVC", "Ours PVC",
                                   f"Mean intensity PVC  [{len(pvc_mean_labels)} regions]",
                                   color="#BA7517")

    rx5, ry5, rl5 = scatter_panel(ax5, vol_x, vol_y, vol_labels,
                                   "A4 Volume_mm3", "Ours Volume_mm3",
                                   f"Volume mm³ no-PVC  [< {VOL_THRESHOLD:,} mm³]",
                                   color="#993C1D")

    rx6, ry6, rl6 = scatter_panel(ax6, nvox_x, nvox_y, nvox_labels,
                                   "A4 NVoxels (PVC)", "Ours NVoxels (PVC)",
                                   f"NVoxels MRI space PVC  [< {NVOX_THRESHOLD:,}]",
                                   color="#3C3489")

    plt.savefig(args.out, dpi=180, bbox_inches="tight")
    print(f"\nSaved: {args.out}")

    # ── per-subject Bland-Altman figure (no-PVC and PVC SUVR) ──────────────────
    if rx1 and rx2:
        fig_ba, (axb1, axb2) = plt.subplots(1, 2, figsize=(14, 6))
        bland_altman_panel(axb1, rx1, ry1,
                           f"Bland-Altman SUVR no-PVC — {args.id}  [{len(rx1)} reg]",
                           color="#D85A30")
        bland_altman_panel(axb2, rx2, ry2,
                           f"Bland-Altman SUVR PVC — {args.id}  [{len(rx2)} reg]",
                           color="#534AB7")
        ba_out = args.out.replace(".png", "_BA.png")
        fig_ba.tight_layout()
        fig_ba.savefig(ba_out, dpi=180, bbox_inches="tight")
        print(f"Saved: {ba_out}")
    # NRMSE: RMSE / range(A4 reference) * 100.
    # Bland-Altman: bias = mean(ours - A4); LoA = bias +/- 1.96*SD(ours - A4).
    #   difference = ours - A4  => positive bias = overestimation relative to A4.
    print("\n── Summary ──────────────────────────────────────────────────────────────────────────────")
    print(f"{'Comparison':<35} {'N':>4} {'r':>6} {'slope':>7} {'MAPE':>8} {'NRMSE':>8} {'bias':>8} {'LoA_lo':>8} {'LoA_hi':>8}")
    print("-" * 106)

    for label, xa, xb in [
        ("SUVR no-PVC: ours vs A4",   rx1, ry1),
        ("SUVR PVC: ours vs A4",      rx2, ry2),
        ("Mean no-PVC: ours vs A4",   rx3, ry3),
        ("Mean PVC: ours vs A4",      rx4, ry4),
        ("Volume mm3: ours vs A4",    rx5, ry5),
        ("NVoxels PVC: ours vs A4",   rx6, ry6),
    ]:
        if not xa:
            continue
        xa, xb = np.array(xa), np.array(xb)
        slope, _, r, _, _ = stats.linregress(xa, xb)
        mape = np.mean(np.abs(xa - xb) / (np.abs(xa) + 1e-9) * 100)
        rmse = np.sqrt(np.mean((xa - xb) ** 2))
        rng  = xa.max() - xa.min()
        nrmse = (rmse / rng * 100) if rng > 0 else float("nan")
        # Bland-Altman (difference = ours - A4 = xb - xa)
        diff   = xb - xa
        bias   = np.mean(diff)
        loa_lo = bias - 1.96 * np.std(diff, ddof=1)
        loa_hi = bias + 1.96 * np.std(diff, ddof=1)
        print(f"{label:<35} {len(xa):>4} {r:>6.3f} {slope:>7.3f} {mape:>7.2f}% {nrmse:>7.2f}% "
              f"{bias:>+8.4f} {loa_lo:>+8.4f} {loa_hi:>+8.4f}")

    # ── HTML ──────────────────────────────────────────────────────────────────
    panels_info = [
        {"title": f"SUVR no-PVC: ours vs A4  [{len(rx1)} regions]",
         "xlabel": "A4 SUVR (no PVC)", "ylabel": "Ours SUVR (no PVC)",
         "color": "#D85A30", "x": rx1, "y": ry1, "labels": rl1},
        {"title": f"SUVR PVC: ours vs A4  [{len(rx2)} regions]",
         "xlabel": "A4 SUVR (PVC)", "ylabel": "Ours SUVR (PVC)",
         "color": "#534AB7", "x": rx2, "y": ry2, "labels": rl2},
        {"title": f"Mean intensity no-PVC  [{len(rx3)} regions]",
         "xlabel": "A4 Mean (no PVC)", "ylabel": "Ours Mean (no PVC)",
         "color": "#0F6E56", "x": rx3, "y": ry3, "labels": rl3},
        {"title": f"Mean intensity PVC  [{len(rx4)} regions]",
         "xlabel": "A4 PVC", "ylabel": "Ours PVC",
         "color": "#BA7517", "x": rx4, "y": ry4, "labels": rl4},
        {"title": f"Volume mm³ no-PVC  [< {VOL_THRESHOLD:,} mm³]",
         "xlabel": "A4 Volume_mm3", "ylabel": "Ours Volume_mm3",
         "color": "#993C1D", "x": rx5, "y": ry5, "labels": rl5},
        {"title": f"NVoxels MRI space PVC  [< {NVOX_THRESHOLD:,}]",
         "xlabel": "A4 NVoxels", "ylabel": "Ours NVoxels",
         "color": "#3C3489", "x": rx6, "y": ry6, "labels": rl6},
    ]

    html_path = args.out.replace(".png", ".html")
    generate_html(args.id, panels_info, html_path)


if __name__ == "__main__":
    main()