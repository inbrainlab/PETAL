# Installation Guide (from a blank machine)

This walks through everything a fresh Linux/macOS machine needs before
`code/replication_tool/run_public_pipeline.sh` can run.

Every step below is CPU-only (classic FreeSurfer `recon-all`, the
default method, `RECON_METHOD=freesurfer`). The GPU/FastSurfer path
(`RECON_METHOD=fastsurfer`) is optional — skip it if you only plan to
use classic FreeSurfer.

The working directory used throughout this guide, `~/fastsurfer/`, is
just an example (set by the `FASTSURFER_BASE` variable at the top of
the script) — use whatever path you prefer, as long as it matches what
`FASTSURFER_BASE` points to.

**If you install anything below at a different path than shown here,
this is where to change it in the code:**

| What | Default in this guide | Edit this variable, in this file |
|---|---|---|
| Working directory | `~/fastsurfer/` | `FASTSURFER_BASE` — `code/replication_tool/run_public_pipeline.sh` line 32 |
| FreeSurfer license | `~/fastsurfer/fs_license/.license` | `FS_LICENSE_DIR` — `code/replication_tool/run_public_pipeline.sh` line 35 (derives from `FASTSURFER_BASE` by default) |
| Matlab Compiled Runtime (MCR v97) | `~/freesurfer-mcr/MCRv97` | Not a variable here — it's a hardcoded Docker mount path at `code/replication_tool/run_public_pipeline.sh` line 185 |
| Python virtualenv | `~/.venv_fastsurfer` | `PYTHON` — `code/replication_tool/run_public_pipeline.sh` line 38 |
| Subject data folder | `$FASTSURFER_BASE/mri_data` | `MRI_DATA_DIR` — `code/replication_tool/run_public_pipeline.sh` line 33 (or export the `MRI_DATA_DIR` environment variable instead of editing the script) |

Line numbers are for this version of the script; if they've drifted,
search for the `# ── configuration ──` block near the top of the file
— every path used by the script is declared there.

## Checking everything is installed

Once you have gone through the steps above, run:

```bash
bash code/replication_tool/check_install.sh [--tracer FTP|FDG]
```

It reads the same variables and defaults as `run_public_pipeline.sh` (so it checks exactly what the pipeline will
use on this machine): Docker and the FreeSurfer/FastSurfer images, the FreeSurfer license, the MCR runtime, the
Python virtualenv and its packages, the helper scripts next to the pipeline, `FS_LUT`/`FSROI_LIST` (only needed to
compare against the published values), and whether `MRI_DATA_DIR` has subject folders directly inside it. Each line
is `OK`, `WARN` (optional, the pipeline still runs without it) or `FAIL` (the pipeline will stop on this), with the
exact command to fix it. Exit code is 0 only if nothing failed.

## 1. Docker

Linux — the official convenience script installs Docker Engine on most
distributions in one line:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER   # then log out/in for this to take effect
```

macOS — install Docker Desktop:
https://www.docker.com/products/docker-desktop/

For a manual, distribution-specific install (or troubleshooting), see
Docker's own guide: https://docs.docker.com/engine/install/

Verify either way:

```bash
docker run --rm hello-world
```

## 2. Docker images

Both images are pulled straight from Docker Hub — no local build needed:

- `freesurfer/freesurfer:7.4.1` (required, classic FreeSurfer, the
  default method): https://hub.docker.com/r/freesurfer/freesurfer
- `deepmi/fastsurfer:cu126-v2.4.2` (optional, only for
  `RECON_METHOD=fastsurfer`, GPU/secondary method):
  https://hub.docker.com/r/deepmi/fastsurfer

```bash
# required — classic FreeSurfer (default method)
docker pull freesurfer/freesurfer:7.4.1

# optional — only if you plan to use RECON_METHOD=fastsurfer (GPU, secondary method)
docker pull deepmi/fastsurfer:cu126-v2.4.2
```

The FastSurfer image also needs the NVIDIA Container Toolkit and a
compatible GPU/driver — see NVIDIA's install docs for your distribution.
Not needed for the default classic-FreeSurfer path.

## 3. FreeSurfer license

Request a free license at
https://surfer.nmr.mgh.harvard.edu/registration.html, then save it as:

```bash
mkdir -p ~/fastsurfer/fs_license
# paste the license content you received into this file:
nano ~/fastsurfer/fs_license/.license
```

The script checks for this exact path and hard-fails if it is missing.

## 4. Matlab Compiled Runtime (MCR v97)

Needed by `segmentBS.sh` (brainstem/pons segmentation) — a free runtime
only, not a full Matlab install. Download MCR v97 (R2019b) for your
platform from MathWorks:
https://www.mathworks.com/products/compiler/matlab-runtime.html, then
run its installer in silent mode, e.g.:

```bash
./install -mode silent -agreeToLicense yes -destinationFolder ~/freesurfer-mcr
```

Confirm the runtime lands at `~/freesurfer-mcr/MCRv97` (FreeSurfer's
Docker image expects that exact path/version — this path is hardcoded
in the script, see the table above).

## 5. Python virtualenv

```bash
python3 -m venv ~/.venv_fastsurfer
~/.venv_fastsurfer/bin/pip install --upgrade pip
~/.venv_fastsurfer/bin/pip install nibabel numpy
```

`nibabel`/`numpy` are the only third-party packages needed — they back a
couple of small inline Python steps inside `run_public_pipeline.sh`
(reading NIfTI headers/frame counts). Nothing else is required: the
region-level CSVs are produced by `mri_segstats`, which ships inside
the FreeSurfer Docker image itself.

## 6. Place your subject data

Two naming conventions are recognized, each with its own subject-ID
scheme (don't mix them within the same subject folder):

```
# A4 convention (subject IDs like A4:35:7415)
~/fastsurfer/mri_data/A4:35:7415/A4:35:7415_T1.nii
~/fastsurfer/mri_data/A4:35:7415/A4_A4:35:7415_MR_Flortaucipir_Br_*.nii   # FTP
~/fastsurfer/mri_data/A4:35:7415/A4_A4:35:7415_MR_FDG_Br_*.nii            # FDG

# ADNI convention (subject IDs like ADNI:294:ec36, with the ADNI Image ID)
~/fastsurfer/mri_data/ADNI:294:ec36/ADNI:294:ec36_I123456_T1.nii
~/fastsurfer/mri_data/ADNI:294:ec36/ADNI:294:ec36_I123456_FTP.nii             # or _AV1451.nii
~/fastsurfer/mri_data/ADNI:294:ec36/ADNI:294:ec36_I123456_FDG.nii
```

If your files use neither naming, set `PET_GLOB_FTP`/`PET_GLOB_FDG` to
your own glob pattern before running the script.

## What you get out

Running `run_public_pipeline.sh <SUBJECT>` produces, per subject, under
`~/fastsurfer/output/<SUBJECT>/`:

- `output.csv` (FTP) / `output_fdg.csv` (FDG) — raw regional means from
  `mri_segstats` for the target region.
- `output_brainstem_fdg.csv` (FDG only) — raw regional means for the
  pons/brainstem, used as the FDG reference region.
- `gtmpvc_T1space_mask.output/gtm.stats.dat` (FTP only) — partial
  volume-corrected regional means.

If `PUBLIC_PACKAGE`, `FS_LUT` and `FSROI_LIST` are set, the script also
runs `evaluate_subject.py` at the end and compares your subject against
the published values, when that subject is among them. See the
repository's README for the full quick-start.
