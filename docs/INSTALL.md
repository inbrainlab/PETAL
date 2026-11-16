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
| SPM standalone run script (any SPM version, optional, Centiloid only, no MATLAB needed) | `$PETPIPELINE_BASE/spm12_standalone/run_spm*.sh` (auto-detected) | export `CENTILOID_SPM_STANDALONE_RUN` |
| MATLAB Runtime dir for standalone (optional, Centiloid only) | `$PETPIPELINE_BASE/spm12_standalone/MATLAB_Runtime/R2022b/v912` | export `CENTILOID_SPM_MCR_DIR` |

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

The pipeline utilizes a dedicated virtual environment located at `~/.venv_pet_pipeline`. Installing all
dependencies (`nibabel`, `numpy`, `pandas`, `scipy`, `matplotlib`, and `openpyxl`) in one go ensures full
support across Tau, FDG, and Centiloid modules.

**Automatic Environment Routing.** You never need to manually activate the virtual environment. Pipeline
wrappers (`run_public_pipeline.sh`, `check_install.sh`) and standalone Python scripts
(`centiloid_pipeline_tracers.py`, `klunk_gaain_validation_plot.py`, `compare_bilateral.py`,
`compare_with_published.py`) automatically detect `~/.venv_pet_pipeline/bin/python3` and self-launch under it
if invoked with plain `python3`.

If you used a different virtualenv path, export `PYTHON` to point at its `python3` and the same routing uses
that instead:

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

**You do not strictly need a MATLAB license.** SPM is also distributed as a free *standalone* build
(compiled SPM + MATLAB Runtime) from https://www.fil.ion.ucl.ac.uk/spm/. Any SPM version works for this
pipeline (SPM12, SPM25, SPM26, ...) -- tested and confirmed working with more than one. The standalone
download's launcher script is named after its own version (`run_spm12.sh`, `run_spm25.sh`, `run_spm26.sh`,
...), never just `run_spm12.sh` regardless of what you downloaded, so don't go looking for that exact
filename -- `centiloid_pipeline_tracers.py`/`check_install.sh` glob for whatever `run_spm*.sh` is actually
there. `centiloid_pipeline_tracers.py` auto-detects whichever of standalone or MATLAB is actually installed.
For a regular MATLAB install, it scans every version folder under the usual system locations (e.g. several
MATLAB versions side by side) and picks the newest one, so you don't need to match an exact version.
Standalone is expected self-contained inside `$PETPIPELINE_BASE/spm12_standalone` instead -- same convention
as `MCRv97` in section 4, no `sudo`/`/opt` install needed (the folder is still called `spm12_standalone` for
historical reasons; any SPM version's standalone download goes there). If your install lives somewhere
else, set `CENTILOID_SPM_STANDALONE_RUN`/`CENTILOID_SPM_MCR_DIR` (standalone) or
`CENTILOID_MATLAB_BIN`/`CENTILOID_SPM12_PATH` (regular MATLAB) to override.

The MATLAB Runtime scan handles both installer layouts seen in the wild: older versions nest an extra
version-code folder (`R2022b/v912`), newer ones (seen on `R2026a`) install directly into the release folder
(`R2026a/bin`, no `v9XX` level) -- either way, point `CENTILOID_SPM_MCR_DIR` at the release folder itself
(the one containing `bin/`, `toolbox/`, etc.), never at `bin/` or any file inside it.

Download the standalone zip for Linux, for whichever SPM version you're using, from the page above (it
bundles a `runtime_installer/` folder with the matching MATLAB Runtime, so you don't need a separate
MathWorks download for this path). Same installer quirk as section 4 applies to the Runtime half: it always
creates its own version-named subfolder, so install it into a temporary folder first, then move that
subfolder into place:

```bash
cd ~/Downloads   # go to where you downloaded the SPM12 standalone zip
unzip spm*_Standalone_Linux.zip -d ~/Downloads/pet_pipeline/spm12_standalone   # extracts run_spm*.sh and runtime_installer/ directly into place (exact zip name depends on your SPM version)
cd ~/Downloads/pet_pipeline/spm12_standalone/runtime_installer   # go to the bundled MATLAB Runtime installer
./install -mode silent -agreeToLicense yes -destinationFolder ~/mcr_install_tmp2   # run it into a temporary folder, never straight into the final MATLAB_Runtime path
mkdir -p ~/Downloads/pet_pipeline/spm12_standalone/MATLAB_Runtime/R2022b   # create the final, version-named destination folder
mv ~/mcr_install_tmp2/v912 ~/Downloads/pet_pipeline/spm12_standalone/MATLAB_Runtime/R2022b/v912   # move the installer's own version subfolder (v912 for R2022b -- match whatever your download says) into place
rmdir ~/mcr_install_tmp2   # remove the now-empty temporary folder
```

Confirm `run_spm*.sh` landed directly at `~/Downloads/pet_pipeline/spm12_standalone/run_spm*.sh` (not one
folder deeper -- whatever `run_spm*.sh` is actually called for your version) and that the Runtime landed at
`~/Downloads/pet_pipeline/spm12_standalone/MATLAB_Runtime/R2022b/v912/bin/glnxa64/` before relying on this
path -- the exact folder/version names depend on the file you downloaded, so adjust the commands above to
match.

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
