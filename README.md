<p align="center">
  <img src="docs/assets/PETAL_logo.jpeg" alt="PETAL logo" width="220">
  <br>
  <em>PETAL -- PET Automated and Local</em>
</p>

# PETAL: published values and replication tools

This repository contains the derived values and the code that accompany the paper (reference to be added on
publication). Its purpose is to let you **process your own PET images with the same pipeline and compare your
numbers with the values we obtained**.

* **Tau (flortaucipir)**: SUVR per composite and per bilateral region, with and without partial-volume correction (PVC).
* **FDG**: SUVR per composite and per bilateral region (pons reference, no PVC).
* **Centiloid (florbetapir)**: SUVR / Centiloid for the six Avid VOIs, plus a validation against the GAAIN
  Centiloid Project data.

The reference data (A4/LEARN, LEADS) and the volume-of-interest masks are **not** distributed here; see
[What is not included](#what-is-not-included).

## Installation

**New here?** Start with [docs/INSTALL.md](docs/INSTALL.md) before anything below -- the Quick start
commands assume Docker, a FreeSurfer license, SPM12, `dcm2niix` and the Python requirements are already in
place.

## Repository layout

```
data/   Values produced by the authors' pipelines (one CSV per analysis) - see docs/DATA_REFERENCE.md
code/
  replication_tool/   process your subject and compare it with the published values; check_install.sh verifies the setup; resolve_subjects.py restores IDs if a release ships coded tables
  centiloid/          Centiloid pipeline (DICOM -> SUVR) and comparison with the A4 reference
  tau_fdg/            cohort-level comparison scripts for Tau and FDG (they need the reference data)
  gaain_validation/   validation of a Centiloid pipeline against the GAAIN Centiloid Project
  dicom_to_nifti/     DICOM -> NIfTI conversion and organisation of downloaded ADNI scans (no MATLAB)
docs/   detailed reference docs kept out of this README -- INSTALL.md, REPLICATION.md, PIPELINE_STEPS.md,
        DATA_REFERENCE.md, DATA_PROVENANCE.md, PARTICIPANT_CODES.md
INDEX_FILES.csv (inside data/)  name and sha256 of the index files used to code the participants
pet_pipeline/   ready-made, empty PETPIPELINE_BASE -- see "Working folder" below
MANIFEST.csv, SHA256SUMS.txt   integrity:  sha256sum -c SHA256SUMS.txt
requirements.txt
```

## Participant codes (read this first)

The participant column of every table in `data/` (`subject` or `subject_id`) holds a **code**, not the ADNI
or A4 identifier -- see [docs/PARTICIPANT_CODES.md](docs/PARTICIPANT_CODES.md) for the coding scheme and
how to restore the real IDs with `code/replication_tool/resolve_subjects.py` if you have approved ADNI/A4
access.

## Working folder

Every script above reads and writes under one folder, `PETPIPELINE_BASE`. You do not need to set
anything: if the variable is not exported, it defaults to [`pet_pipeline/`](pet_pipeline/), the folder
this repository already ships, empty, right next to this README. Download the repo, drop your data
straight into its subfolders, and run the commands below -- no `--output_dir`, `--base_dir` or
`export` needed:

```
pet_pipeline/
  mri_data/             <ID>/<ID>_T1.nii + the PET, for run_public_pipeline.sh / run_cohort.sh
  output/                written by run_public_pipeline.sh; read by evaluate_subject.py / compare_fdg_leads.py
  centiloid_input/       for centiloid_pipeline_tracers.py (--base_dir)
  A4_pipeline_input/     for run_all_A4_florbetapir.sh (input: your original data, never written to)
  A4_pipeline_output/    for run_all_A4_florbetapir.sh (output: everything the pipeline generates)
  subject_evaluation/    written by evaluate_subject.py
  leads_data/             LEADS reference data, for compare_fdg_leads.py (--leads-base)
  fs_license/             FreeSurfer license file, for run_public_pipeline.sh
  MCRv97/                 MATLAB Runtime R2019b, for FDG processing
```

Only export `PETPIPELINE_BASE` if you want your data somewhere else entirely:

```bash
export PETPIPELINE_BASE=/path/to/your/own/folder
```

## Quick start: process and compare one subject

Process your subject (Tau or FDG PET, from the images):

```bash
bash code/replication_tool/run_public_pipeline.sh <ID> [--tracer FTP|FDG]
```

Every shell script in `code/replication_tool/` (`run_public_pipeline.sh`, `run_cohort.sh`,
`check_install.sh`) understands `--help` / `-h` and prints its own full usage without running anything,
for example `bash code/replication_tool/run_public_pipeline.sh --help`.

Several subjects: `code/replication_tool/run_cohort.sh` runs the command above once per subject,
auto-discovered under `MRI_DATA_DIR`:

```bash
nohup bash code/replication_tool/run_cohort.sh [--tracer FTP|FDG] > logs/cohort.out 2>&1 &
```

Compare with the published values:

```bash
python3 code/replication_tool/evaluate_subject.py --type tau --package . \
    --output_dir <PETPIPELINE_BASE>/output --subject <ID> \
    --fsroi-list data/rois_ftp.csv --lut FreeSurferColorLUT.txt
```

`--output_dir` defaults to `PETPIPELINE_BASE/output` and can be omitted if you used that default.

See [docs/REPLICATION.md](docs/REPLICATION.md) for requirements, input file names, FDG/Centiloid,
`run_cohort.sh` usage, comparing three or more subjects, and bilateral regions.

## Resuming after an interruption

**The pipeline is not all-or-nothing.** If a run dies partway through -- the container is killed, the
machine reboots, you `Ctrl-C` it -- nothing already written is lost. Re-running the *exact same command*
checks each step's own output file first and skips anything already there; it never redoes finished work.

```
 bash code/replication_tool/run_public_pipeline.sh <ID> --tracer FDG        <- run #1, interrupted

 STEP  0  recon-all (~3-4h)  ................................  (killed mid-run)
 STEP  1  Extract frames  ...................................  never reached
 STEP  2  Initial mean  ......................................  never reached
   ...

 bash code/replication_tool/run_public_pipeline.sh <ID> --tracer FDG        <- run #2, same command

 STEP  0  recon-all  .........................................  re-runs (no output yet from run #1)
 STEP  1  Extract frames  ....................................  runs
 STEP  2  Initial mean  ......................................  runs
   ...
```

Concrete example that actually saves time: `recon-all` is the slow step (hours); everything after it is
minutes. If run #1 is interrupted *after* `recon-all` already finished (`mri/aparc+aseg.mgz` exists under
`<PETPIPELINE_BASE>/output/<ID>/`), run #2 looks like this instead:

```
 bash code/replication_tool/run_public_pipeline.sh <ID> --tracer FDG        <- run #2, same command

 STEP  0  recon-all  .........................................  ⏭  skipped -- mri/aparc+aseg.mgz already exists
 STEP  1  Extract frames  ....................................  ▶  runs  <- PET processing starts here
 STEP  2  Initial mean  ......................................  ▶  runs
   ...
```

No flag, no special "resume" command -- it is the *same* `run_public_pipeline.sh <ID> --tracer FDG` both
times. To force a step (and everything after it) to redo anyway, use `--rewrite <N>` with the step number
printed at the start of that step, `--rewrite 0b`, or `--rewrite all`; see
[Resuming from any step](docs/REPLICATION.md#resuming-from-any-step) for the full list of steps and flags.

### Already have your own recon-all? Skip straight to PET processing

The same skip-if-output-exists check works even if `recon-all` never ran inside this pipeline at all. If
you already reconstructed the subject yourself (your own `recon-all`, or FastSurfer, or a HPC cluster run),
drop that FreeSurfer subject folder where this pipeline expects to find its own output --
`<PETPIPELINE_BASE>/output/<ID>/` -- and the script will treat it exactly as if STEP 0 had already run here:

```
<PETPIPELINE_BASE>/output/<ID>/
  mri/aparc+aseg.mgz                              <- required: makes STEP 0  (recon-all)   skip
  mri/transforms/talairach.m3z                     <- required: makes STEP 0b (talairach.m3z) skip
  mri/brainstemSsLabels.v13.FSvoxelSpace.mgz       <- required for --tracer FDG only: makes STEP 0c (segmentBS.sh) skip
```

If your own reconstruction doesn't have `brainstemSsLabels.v13.FSvoxelSpace.mgz` (classic `recon-all`
doesn't generate it by default) and you need FDG, run `segmentBS.sh <ID>` once yourself, or just let
STEP 0c run on its own the first time -- it only needs `talairach.m3z`, which you already have.

```
 bash code/replication_tool/run_public_pipeline.sh <ID> --tracer FDG        <- first run ever, own recon-all already placed

 STEP  0  recon-all  .........................................  ⏭  skipped -- mri/aparc+aseg.mgz already exists (yours)
 STEP  0b talairach.m3z  .....................................  ⏭  skipped -- already exists (yours)
 STEP  0c segmentBS.sh  ......................................  ▶  runs (FDG only, needs talairach.m3z -- just produced/verified above)
 STEP  1  Extract frames  ....................................  ▶  runs  <- PET processing starts here
   ...
```

In other words: nothing about STEPs 1 onward cares whether `recon-all` was run by this pipeline or brought
in from elsewhere -- only the output files matter.

### Centiloid (florbetapir)

**This section is for GAAIN-style data** -- numeric subject IDs (6 digits, e.g. `105858`) under
`Elder_subject_florbetapir/` / `Young_Control_florbetapir/`, the layout `--all` below auto-discovers. If
your subject IDs are alphanumeric (A4-style, e.g. `B10693248`), skip straight to
[Centiloid for the A4 cohort](#centiloid-for-the-a4-cohort-alphanumeric-ids-already-nifti) below instead --
`--all` will not find them (it only recognizes 6-digit numeric IDs) and will report "0 subjects".

**Uses the same virtualenv as Tau/FDG, plus a few extra packages** (`pandas`/`scipy`/`matplotlib`) -- see
[docs/INSTALL.md](docs/INSTALL.md) section 5. You don't need to activate anything: the plain `python3`
commands below detect that virtualenv themselves and use it automatically, as long as you created it at
the default path (or exported `PYTHON` to point at a different one).

`code/centiloid/centiloid_pipeline_tracers.py` goes straight from DICOM to SUVR/Centiloid (it does its own
DICOM-to-NIfTI conversion, so you don't need `dicom_to_nifti.py` for this tracer). Three ways to run it:

```bash
# one subject, to try it out or debug
python3 code/centiloid/centiloid_pipeline_tracers.py --test <SUBJECT_ID>

# every subject, writing one CSV with one row each (under results/ by default)
python3 code/centiloid/centiloid_pipeline_tracers.py --all

# every subject, also auto-reorienting PET/MRI towards the MNI origin before SPM Coregister --
# rescues subjects whose center of mass is far off, without affecting the ones that were already fine
python3 code/centiloid/centiloid_pipeline_tracers.py --all --auto_reorient
```

Without `--auto_reorient`, a subject whose images are far from the MNI origin can fail or come out
misaligned at the SPM Coregister step. `--auto_reorient` is recommended as the default; only skip it if you
already know your data is well-centered.

It looks for everything under `--base_dir`, which defaults to `PETPIPELINE_BASE/centiloid_input` (i.e.
``pet_pipeline/centiloid_input` unless you export `PETPIPELINE_BASE`) -- put your data there and
none of the commands above need `--base_dir` at all. Pass `--base_dir <folder>` only if you keep your data
somewhere else:

```
<base_dir>/
  *MRI*/<SUBJECT_ID>*/...dcm              T1 DICOMs (any folder with "MRI" in its name)
  florbetapir/
    Elder_subject_florbetapir/<SUBJECT_ID>*/...dcm   PET DICOMs
    Young_Control_florbetapir/<SUBJECT_ID>*/...dcm
  Avid_Centiloid_standard_method.xlsx     GAAIN reference spreadsheet
  VOIs_klunk/                              VOI masks (VOIs_2mm/ if --voi_method avid)
```

`--all` discovers every `<SUBJECT_ID>` by scanning the subfolder names directly under the two
`florbetapir/.../` folders above -- not the MRI folder. It reads a 6-digit ID at the start of the name
(`105858_...` or `231642` -> `105858`, `231642`), or, for PiB, a 6-digit ID after `PiB-` (`PiB-105858` ->
`105858`). A folder name that matches neither pattern is skipped.

### Validate your Centiloid pipeline against GAAIN (optional)

Compares your own Centiloid results (the CSV from `--all` above) against the published GAAIN calibration
values. See [docs/DATA_REFERENCE.md](docs/DATA_REFERENCE.md) for what the input CSV needs and our own
reference result.

```bash
python3 code/gaain_validation/klunk_gaain_validation_plot.py --centiloid_results <your CSV> \
    --gaain_xlsx Avid_Centiloid_standard_method.xlsx --out validation.png
```

### Centiloid for the A4 cohort (alphanumeric IDs, already NIfTI)

A4 subjects (IDs like `B99999999`) don't fit `--all` above: their IDs and folder layout don't match the
pattern `centiloid_pipeline_tracers.py` expects. `code/centiloid/run_all_A4_florbetapir.sh` works around
this without changing that script: it lists the subject subfolders itself and calls `--test` once per
subject (so it goes through the same pipeline, just told about subjects a different way).

**Two separate folders, input and output** -- `A4_DATA_DIR` only ever holds your original data (never
written to by this pipeline), and `A4_OUT_DIR` only ever holds what the pipeline generates (per-subject
work files, `centiloid_results.csv`). Both default to folders already inside `pet_pipeline/` (see the
layout at the top of this README), so if you put your data at the default `A4_DATA_DIR` path below, running
it is just:

```bash
# every subject found under A4_DATA_DIR
bash code/centiloid/run_all_A4_florbetapir.sh

# one subject only, to try it out or debug
bash code/centiloid/run_all_A4_florbetapir.sh B99999999
```

Only set `A4_DATA_DIR`/`A4_OUT_DIR` yourself if you want your data somewhere other than the defaults:

```bash
A4_DATA_DIR=<folder from the layout below> A4_OUT_DIR=<where results should go> bash code/centiloid/run_all_A4_florbetapir.sh
```

`run_all_A4_florbetapir.sh` passes `--skip_dcm2niix --input_dir "$A4_DATA_DIR"`, so
`centiloid_pipeline_tracers.py` does not look for DICOM or `base_dir` at all for these subjects -- it reads
the T1 and PET directly from each subject's own folder under `A4_DATA_DIR` (the PET already summed if it
had multiple frames -- not split into separate frame files).

**The files must be renamed to exactly `<SUBJECT_ID>_t1.nii` and `<SUBJECT_ID>_pet.nii` -- the original
filenames from an A4/ADNI download (e.g. `A4_B10693248_MR_T1__GradWarp_DeFaced_Br_..._I1363261.nii`) will
not be found and the run will fail with "T1 not found".** Rename them yourself before running:

```bash
cd <A4_DATA_DIR>/<SUBJECT_ID>
mv *MR_T1*.nii <SUBJECT_ID>_t1.nii
mv *Florbetapir*.nii <SUBJECT_ID>_pet.nii
```

```
<A4_DATA_DIR>/
  B99999999/
    B99999999_t1.nii            T1 (already converted)
    B99999999_pet.nii           PET (already converted and summed)
  B88888888/
    B88888888_t1.nii
    B88888888_pet.nii
  ...
```

## From DICOM to NIfTI

`code/dicom_to_nifti/dicom_to_nifti.py` converts DICOM downloads to NIfTI and organizes them under `--outdir`.
Add `--rename` to also rename each file to the exact names `run_public_pipeline.sh` expects -- no manual
renaming needed. See [docs/INSTALL.md](docs/INSTALL.md) section 7 for installing `dcm2niix` and the full
details (duplicate-file handling, etc.).

```bash
# organize only, keeping dcm2niix's own file names
python3 code/dicom_to_nifti/dicom_to_nifti.py --indir <downloaded zips / DICOM folders> --outdir <folder for the organized NIfTI files>

# also rename, ready for run_public_pipeline.sh, into the folder it expects (e.g. mri_data)
python3 code/dicom_to_nifti/dicom_to_nifti.py --indir <downloaded zips / DICOM folders> --outdir <folder for the organized NIfTI files> --rename <folder renamed NIfTI files>
```

## Data provenance (FDG cohort)

The 472 FDG participants carry ADNI identifiers, with scans acquired between 2007 and 2023 across ADNI1 through
ADNI4 (not restricted to ADNI3). See [docs/DATA_PROVENANCE.md](docs/DATA_PROVENANCE.md) for the full breakdown by
ADNI period, frame counts, and T1/PET image dimensions.

## What is not included

* A4/LEARN reference values, imaging data and participant-level data. Controlled access:
  <https://www.a4studydata.org/> (see Jimenez-Maggiora et al., Aperture Neuro 2026).
* LEADS reference data and code: <https://github.com/dschonhaut/leads_processing>.
* Volume-of-interest (VOI) masks: GAAIN.
* Any per-participant difference or error with respect to the reference (it would allow recovering the reference
  values). The tools in `code/replication_tool/` do not use the reference data: they compare your values with the
  published values of this work. The scripts in `code/centiloid/` and `code/tau_fdg/` that reproduce this work's
  comparisons with the reference (`compare_*_a4.py`, `compare_fdg_leads.py`, `nrmse_cohort.py` and the Avid/A4 plots)
  need the reference data, which must be obtained from the original providers.
* `FreeSurferColorLUT.txt`: not distributed either, but it ships inside the FreeSurfer Docker image
  already required above -- copy it out once with
  `docker run --rm -v ~/freesurfer:/out freesurfer/freesurfer:7.4.1 cp "$FREESURFER_HOME/FreeSurferColorLUT.txt" /out/FreeSurferColorLUT.txt`
  (matches the `--lut` default, `~/freesurfer/FreeSurferColorLUT.txt`).

## Integrity

```bash
sha256sum -c SHA256SUMS.txt
```

## References

* Devous MD Sr, et al. Test–retest reproducibility for the tau PET imaging agent flortaucipir F 18. *J Nucl Med.* 2018;59(6). PMID 29284675.
* Schwarz AJ, et al. Optimizing software methods for measuring flortaucipir SUVR change over time. *Alzheimer's & Dementia.* 2021 (abstract).
* Klunk WE, et al. The Centiloid Project: standardizing quantitative amyloid plaque estimation by PET. *Alzheimer's & Dementia.* 2015.
* Shrout PE, Fleiss JL. Intraclass correlations: uses in assessing rater reliability. *Psychol Bull.* 1979.
* Jack CR Jr, et al. Defining imaging biomarker cut points for brain aging and Alzheimer's disease. *Alzheimer's & Dementia.* 2017.

## License and citation

See `LICENSE` and, once the paper is published, `CITATION.cff`.
