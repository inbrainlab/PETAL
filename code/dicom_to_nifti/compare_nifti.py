#!/usr/bin/env python3
"""Compare NIfTI files with the same name in two folders (data, affine, header).
Usage: python3 compare_nifti.py NEW_DIR OLD_DIR      (searches recursively; run with a Python that has nibabel)"""
import glob
import os
import sys

import nibabel as nib
import numpy as np

new_dir, old_dir = sys.argv[1:3]
old = {os.path.basename(f): f for f in glob.glob(os.path.join(old_dir, "**", "*.nii*"), recursive=True)}
for new in sorted(glob.glob(os.path.join(new_dir, "**", "*.nii*"), recursive=True)):
    b = os.path.basename(new)
    if b not in old:
        print(f"{b[:50]}: no file with this name in {old_dir}")
        continue
    a, c = nib.load(new), nib.load(old[b])
    da, dc = np.asarray(a.dataobj), np.asarray(c.dataobj)
    same_shape = a.shape == c.shape
    print(f"{b[:50]}\n  shape new {a.shape} old {c.shape} | dtype {da.dtype} {dc.dtype}")
    if same_shape:
        eq = np.array_equal(da, dc)
        print(f"  data identical: {eq}" + ("" if eq else f" | max abs diff {np.abs(da.astype(float) - dc.astype(float)).max():.6g}"))
        print(f"  affine identical: {np.allclose(a.affine, c.affine)}")
        diff = [k for k in a.header.keys() if not np.array_equal(a.header[k], c.header[k], equal_nan=True)]
        print(f"  header fields that differ: {diff}")
