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
| MATLAB (Centiloid only) | `/opt/MATLAB/R2022b/bin/matlab` | `MATLAB_BIN` in `code/centiloid/centiloid_pipeline_tracers.py` (configuration block), or export `CENTILOID_MATLAB_BIN` |
| SPM12 (Centiloid only) | `/opt/MATLAB/R2022b/toolbox/spm12` | `SPM12_PATH` in `code/centiloid/centiloid_pipeline_tracers.py`, or export `CENTILOID_SPM12_PATH` |
| MNI template (Centiloid only) | `/opt/MATLAB/R2022b/toolbox/spm12/canonical/avg152T1.nii` | `MNI_TEMPLATE` in `code/centiloid/centiloid_pipeline_tracers.py`, or export `CENTILOID_MNI_TEMPLATE` |
| SPM12 standalone run script (optional, Centiloid only, no MATLAB needed) | unset | export `CENTILOID_SPM_STANDALONE_RUN` |
| MATLAB Runtime dir for standalone (optional, Centiloid only) | unset | export `CENTILOID_SPM_MCR_DIR` |

Line numbers are for this version of the script; if they've drifted,
search for the `# ── configuration ──` block near the top of the file
— every path used by the script is declared there.

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
~/.venv_pet_pipeline/bin/pip install nibabel numpy pandas scipy matplotlib openpyxl
```

Installing everything here in one go, even if you only plan to run Tau/FDG today, avoids a
`ModuleNotFoundError` later if you end up running Centiloid too. `nibabel`/`numpy` are all that
`run_public_pipeline.sh` (Tau/FDG) itself needs -- they back a couple of small inline Python steps (reading
NIfTI headers/frame counts); the region-level CSVs themselves are produced by `mri_segstats`, which ships
inside the FreeSurfer Docker image. `pandas`/`scipy`/`matplotlib` are for `code/centiloid/centiloid_pipeline_tracers.py`
and `pandas`-using comparison scripts; `openpyxl` is only for `code/gaain_validation/klunk_gaain_validation_plot.py`.

**You never need to activate this virtualenv or think about which `python3` you're calling.**
`run_public_pipeline.sh`/`check_install.sh` already call this venv's own `python3` internally (via the
`$PYTHON` variable), and the scripts meant to be run directly with plain `python3` (`centiloid_pipeline_tracers.py`,
`klunk_gaain_validation_plot.py`, `compare_bilateral.py`, `compare_with_published.py`) detect it themselves:
if `~/.venv_pet_pipeline/bin/python3` exists and you did not happen to already run them with it, they
silently re-launch themselves under it before importing anything. So a plain

```bash
python3 code/centiloid/centiloid_pipeline_tracers.py --test <SUBJECT_ID>
```

picks up this virtualenv's packages automatically, as long as you created it at the default path above. If
you used a different virtualenv path, export `PYTHON` to point at its `python3` and the same auto-detection
uses that instead:

```bash
export PYTHON=/path/to/your/venv/bin/python3
```

## 6. Place your subject data

Two naming conventions are recognized, each with its own subject-ID
scheme (don't mix them within the same subject folder):

```
# A4 convention (subject IDs like B99999999)
~/Downloads/pet_pipeline/mri_data/B99999999/B99999999_T1.nii
~/Downloads/pet_pipeline/mri_data/B99999999/A4_B99999999_MR_Flortaucipir_Br_*.nii   # FTP
~/Downloads/pet_pipeline/mri_data/B99999999/A4_B99999999_MR_FDG_Br_*.nii            # FDG

# ADNI convention (subject IDs like 999_S_9999, with the ADNI Image ID)
~/Downloads/pet_pipeline/mri_data/999_S_9999/999_S_9999_I123456_T1.nii
~/Downloads/pet_pipeline/mri_data/999_S_9999/999_S_9999_I123456_FTP.nii             # or _AV1451.nii
~/Downloads/pet_pipeline/mri_data/999_S_9999/999_S_9999_I123456_FDG.nii
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

## 8. MATLAB + SPM12 (only needed for Centiloid/amyloid)

Only `code/centiloid/centiloid_pipeline_tracers.py` needs this -- Tau and FDG (`run_public_pipeline.sh`)
never call SPM, so skip this section entirely if you are not processing Centiloid/florbetapir.

Centiloid needs a real MATLAB installation (not the MCR runtime from section 4 above, which is unrelated to
this) with the SPM12 toolbox installed in it. Install both yourself (MATLAB license + SPM12, downloaded from
https://www.fil.ion.ucl.ac.uk/spm/software/spm12/) following their own instructions -- there is nothing
specific to this repo about that part.

**Telling the script where you installed them.** `centiloid_pipeline_tracers.py` looks for MATLAB and SPM12
at these default paths:

```
MATLAB:        /opt/MATLAB/R2022b/bin/matlab
SPM12:         /opt/MATLAB/R2022b/toolbox/spm12
MNI template:  /opt/MATLAB/R2022b/toolbox/spm12/canonical/avg152T1.nii
```

If your installation does not match this exactly (different MATLAB version, different install location, or
SPM12 installed somewhere else), export these three environment variables before running the script:

```bash
export CENTILOID_MATLAB_BIN=/path/to/bin/matlab
export CENTILOID_SPM12_PATH=/path/to/spm12
export CENTILOID_MNI_TEMPLATE=/path/to/spm12/canonical/avg152T1.nii
```

`avg152T1.nii` ships inside SPM12 itself, under its own `canonical/` folder, so once you know where SPM12 is
installed, the third path follows directly from it. No other setup, registration or configuration is
needed -- these three paths are everything the script needs to find and drive SPM12 through MATLAB.

**You do not strictly need a MATLAB license.** SPM12 is also distributed as a *standalone*, free
alternative: a version of SPM12 already compiled into a self-contained executable, paired with the free
MATLAB Runtime (a redistributable, license-free runtime -- the same kind of thing as the MCR used for
FreeSurfer's `segmentBS.sh` in section 4, just a different, SPM-specific build). If you cannot get a MATLAB
license, this is the route to use instead:

1. Download the SPM12 standalone build for your OS from
   https://www.fil.ion.ucl.ac.uk/spm/software/spm12/ (look for the "Standalone" / "Linux/macOS/Windows
   SPM12 Standalone" download, as opposed to the plain "SPM12" toolbox download used above). It comes with
   a `run_spm12.sh` script (or `.bat` on Windows).
2. Download and install the specific version of the MATLAB Runtime that the standalone build says it needs
   (the version has to match exactly -- the standalone page links directly to the right Runtime installer).
3. Point the pipeline at both, instead of at `CENTILOID_MATLAB_BIN`/`CENTILOID_SPM12_PATH`:

   ```bash
   export CENTILOID_SPM_STANDALONE_RUN=/path/to/spm12_standalone/run_spm12.sh
   export CENTILOID_SPM_MCR_DIR=/path/to/MATLAB_Runtime/R2022b/v912
   ```

   When both of these are set, `centiloid_pipeline_tracers.py` calls `run_spm12.sh <MCR_dir> batch
   <jobfile>` instead of a licensed `matlab` binary, and `CENTILOID_MATLAB_BIN`/`CENTILOID_SPM12_PATH` are
   then ignored. `CENTILOID_MNI_TEMPLATE` is unaffected either way -- it is just a file path the script
   reads directly, not something passed to MATLAB/SPM, so keep setting it (or its default) as usual.

Note SPM12 standalone only ships SPM's built-in toolboxes (Old Segment, Normalise, Coregister -- all of
which this pipeline already uses) -- it cannot run contributed/third-party SPM toolboxes without a full
MATLAB-based recompile, so if this pipeline's SPM usage ever grows beyond that, this standalone route may
stop being an option.

## Checking everything is installed

Once you have gone through every step above (1-7), run:

```bash
bash code/replication_tool/check_install.sh [--tracer FTP|FDG]
```

It reads the same variables and defaults as `run_public_pipeline.sh` (so it checks exactly what the pipeline will
use on this machine): Docker and the FreeSurfer/FastSurfer images, the FreeSurfer license, the MCR runtime, the
Python virtualenv and its packages, the helper scripts next to the pipeline, `FS_LUT`/`FSROI_LIST` (only needed to
compare against the published values), and whether `MRI_DATA_DIR` has subject folders directly inside it. Each line
is `OK`, `WARN` (optional, the pipeline still runs without it) or `FAIL` (the pipeline will stop on this), with the
exact command to fix it. Exit code is 0 only if nothing failed.

`bash check_install.sh --help` (and the same for `run_public_pipeline.sh` and `run_cohort.sh`) prints the full
usage for that script without running anything.

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
