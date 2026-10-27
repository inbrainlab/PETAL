# Installation Guide (from a blank machine)

This walks through everything a fresh Linux/macOS machine needs before
`code/replication_tool/run_public_pipeline.sh` can run.

Every step below is CPU-only (classic FreeSurfer `recon-all`, the
default method, `RECON_METHOD=freesurfer`). The GPU/FastSurfer path
(`RECON_METHOD=fastsurfer`) is optional — skip it if you only plan to
use classic FreeSurfer.

The working directory used throughout this guide, `~/Downloads/pet_pipeline/`, is
just an example (set by the `PETPIPELINE_BASE` variable at the top of
the script) — use whatever path you prefer, as long as it matches what
`PETPIPELINE_BASE` points to.

**If you install anything below at a different path than shown here,
this is where to change it in the code:**

| What | Default in this guide | Edit this variable, in this file |
|---|---|---|
| Working directory | `~/Downloads/pet_pipeline/` (this is the default -- no edit needed if you download the repo and run it from `~/Downloads`) | `PETPIPELINE_BASE` — `code/replication_tool/run_public_pipeline.sh` line 32 |
| FreeSurfer license | `~/Downloads/pet_pipeline/fs_license/.license` | `FS_LICENSE_DIR` — `code/replication_tool/run_public_pipeline.sh` line 35 (derives from `PETPIPELINE_BASE` by default) |
| Matlab Compiled Runtime (MCR v97) | `$PETPIPELINE_BASE/MCRv97` | `MCR_DIR` in `code/replication_tool/run_public_pipeline.sh` (configuration block, next to `PETPIPELINE_BASE`/`FS_LICENSE_DIR`), defaults to `$PETPIPELINE_BASE/MCRv97` and can be overridden by exporting `MCR_DIR` |
| Python virtualenv | `~/.venv_pet_pipeline` | `PYTHON` — `code/replication_tool/run_public_pipeline.sh` line 38 |
| Subject data folder | `$PETPIPELINE_BASE/mri_data` | `MRI_DATA_DIR` — `code/replication_tool/run_public_pipeline.sh` line 33 (or export the `MRI_DATA_DIR` environment variable instead of editing the script) |

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
mkdir -p ~/Downloads/pet_pipeline/fs_license
# paste the license content you received into this file:
nano ~/Downloads/pet_pipeline/fs_license/.license
```

The script checks for this exact path and hard-fails if it is missing.

## 4. Matlab Compiled Runtime (MCR v97)

Needed by `segmentBS.sh` (brainstem/pons segmentation) — a free runtime
only, not a full Matlab install. Download MCR v97 (R2019b) for your
platform from MathWorks:
https://www.mathworks.com/products/compiler/matlab-runtime.html.

**Installer quirk (read this before running it):** the MathWorks installer
always creates its own version-named subfolder (`v97`) inside whatever
`-destinationFolder` you give it — it never places the runtime files
directly in that folder. If you install straight into
`$PETPIPELINE_BASE/MCRv97`, you end up with the real files one level too
deep, at `$PETPIPELINE_BASE/MCRv97/v97/...`, and FreeSurfer's Docker image
will fail to find the runtime (or fail with a `libmwmclmcrrt.so.9.7`
error if a previous, partial install already left some files directly in
that path). Install into a temporary folder instead, then move the `v97`
subfolder up into place with the exact name `MCRv97`.

MathWorks ships the MCR installer as a zip; once you download and extract it (into `~/Downloads`, like everything
else in this guide), the installer binary ends up somewhere like
`~/Downloads/MATLAB_Runtime_R2019b_Update_*_glnxa64/install` (the exact folder name depends on the file you
downloaded). Run it from there:

These commands use the literal default path (`~/Downloads/pet_pipeline`, matching this guide); if you set
`PETPIPELINE_BASE` to something else, replace it accordingly -- `$PETPIPELINE_BASE` is a variable read inside
`run_public_pipeline.sh`/`check_install.sh`, it is not set in your shell:

```bash
cd ~/Downloads/MATLAB_Runtime_R2019b_Update_*_glnxa64   # go to the folder where you extracted the installer (the * matches whatever update number you downloaded; must match exactly one folder)
./install -mode silent -agreeToLicense yes -destinationFolder ~/mcr_install_tmp   # run the installer into a temporary folder, never straight into the final MCRv97 path
mv ~/mcr_install_tmp/v97 ~/Downloads/pet_pipeline/MCRv97   # move the installer's own v97 subfolder up, renaming it to the final MCRv97 path
rmdir ~/mcr_install_tmp   # remove the now-empty temporary folder
```

Confirm the runtime lands directly at `~/Downloads/pet_pipeline/MCRv97` (FreeSurfer's
Docker image expects that exact path — it is hardcoded in the script,
see the table above, and derives from `PETPIPELINE_BASE`):

```bash
ls ~/Downloads/pet_pipeline/MCRv97/bin/glnxa64/libmwlaunchermain.so
ls ~/Downloads/pet_pipeline/MCRv97/runtime/glnxa64/libmwmclmcrrt.so.9.7
```

Both files must exist, or `segmentBS.sh` will fail (the second one only
shows up once the full runtime, not just a partial install, is in place).
`check_install.sh` (see below) verifies this for you.

## 5. Python virtualenv

```bash
python3 -m venv ~/.venv_pet_pipeline
~/.venv_pet_pipeline/bin/pip install --upgrade pip
~/.venv_pet_pipeline/bin/pip install nibabel numpy
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
~/Downloads/pet_pipeline/mri_data/A4:35:7415/A4:35:7415_T1.nii
~/Downloads/pet_pipeline/mri_data/A4:35:7415/A4_A4:35:7415_MR_Flortaucipir_Br_*.nii   # FTP
~/Downloads/pet_pipeline/mri_data/A4:35:7415/A4_A4:35:7415_MR_FDG_Br_*.nii            # FDG

# ADNI convention (subject IDs like ADNI:294:ec36, with the ADNI Image ID)
~/Downloads/pet_pipeline/mri_data/ADNI:294:ec36/ADNI:294:ec36_I123456_T1.nii
~/Downloads/pet_pipeline/mri_data/ADNI:294:ec36/ADNI:294:ec36_I123456_FTP.nii             # or _AV1451.nii
~/Downloads/pet_pipeline/mri_data/ADNI:294:ec36/ADNI:294:ec36_I123456_FDG.nii
```

If your files use neither naming, set `PET_GLOB_FTP`/`PET_GLOB_FDG` to
your own glob pattern before running the script.

## 7. dcm2niix (only if you are converting DICOM to NIfTI yourself)

Only needed for `code/dicom_to_nifti/dicom_to_nifti.py` (section 6 above assumes you already have NIfTI
files). Skip this if your data is already NIfTI.

```bash
# Debian/Ubuntu
sudo apt-get update && sudo apt-get install -y dcm2niix

# macOS (Homebrew)
brew install dcm2niix
```

If your distribution's package is older than v1.0.20240202 (the version used in this work) or unavailable,
download a prebuilt binary from the project's releases page instead:
https://github.com/rordenlab/dcm2niix/releases. Extract it anywhere and either add that folder to your
`PATH`, or pass `--dcm2niix /path/to/dcm2niix` to `dicom_to_nifti.py` every time (see `code/dicom_to_nifti/`'s
own usage in its docstring, `python3 code/dicom_to_nifti/dicom_to_nifti.py --help`).

Verify either way:

```bash
dcm2niix -v
```

**Getting the NIfTI files named the way `run_public_pipeline.sh` expects.** `dicom_to_nifti.py` converts and
organizes files under its own `--outdir` folder using dcm2niix's own output names, which do not match section 6's
naming convention by themselves. There are three ways to run it:

- without `--rename`: the files stay organized under `--outdir` with dcm2niix's own names; nothing is renamed.
- with `--rename` on its own (no folder after it): the organized files are renamed in place inside
  `--outdir` itself, to `<SUBJECT>_T1.nii`, `<SUBJECT>_FTP.nii`, `<SUBJECT>_FDG.nii`, etc. -- exactly what
  `run_public_pipeline.sh` looks for.
- with `--rename <folder>`: the organized files are moved and renamed into `<folder>` instead -- typically
  the `mri_data` folder `run_public_pipeline.sh` itself defaults to (`PETPIPELINE_BASE/mri_data`).

Either way it is a move, not a copy: the original dcm2niix-named file does not stick around alongside the
renamed one.

If a subject has more than one file of the same scan type, the one with the earliest scan date is used, and
the rest are printed so you can review them by hand:

```bash
python3 code/dicom_to_nifti/dicom_to_nifti.py --indir ~/Downloads/adni_download \
    --outdir ~/Downloads/pet_pipeline_raw --rename ~/Downloads/pet_pipeline/mri_data
```

## Running the whole cohort

Once `mri_data/` has more than one subject, use `code/replication_tool/run_cohort.sh` instead of calling
`run_public_pipeline.sh` once per subject by hand. It auto-discovers every subject folder under
`MRI_DATA_DIR`, runs `run_public_pipeline.sh` for each one in turn, and keeps one log file per subject under
`PETPIPELINE_BASE/logs/<SUBJECT>.log`:

```bash
nohup bash code/replication_tool/run_cohort.sh [--tracer FTP|FDG] [--rewrite N|0b|all] > logs/cohort.out 2>&1 &
tail -f logs/cohort.out
```

Any arguments given to `run_cohort.sh` (for example `--tracer FDG`) are forwarded as-is to
`run_public_pipeline.sh` for every subject. One subject failing does not stop the cohort; a failed subject
is reported at the end together with its log file. `run_public_pipeline.sh` is resumable per subject, so if
the cohort run is interrupted, simply running the same command again continues where it left off instead of
reprocessing finished subjects.

## What you get out

Running `bash run_public_pipeline.sh <SUBJECT>` produces, per subject, under
`~/Downloads/pet_pipeline/output/<SUBJECT>/`:

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
