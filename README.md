# PET harmonization: published values and replication tools

This repository contains the derived values and the code that accompany the paper (reference to be added on
publication). Its purpose is to let you **process your own PET images with the same pipeline and compare your
numbers with the values we obtained**.

* **Tau (flortaucipir)**: SUVR per composite and per bilateral region, with and without partial-volume correction (PVC).
* **FDG**: SUVR per composite and per bilateral region (pons reference, no PVC).
* **Centiloid (florbetapir)**: SUVR / Centiloid for the six Avid VOIs, plus a validation against the GAAIN
  Centiloid Project data.

The reference data (A4/LEARN, LEADS) and the volume-of-interest masks are **not** distributed here; see
[What is not included](#what-is-not-included).

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
        DATA_REFERENCE.md, DATA_PROVENANCE.md
MANIFEST.csv, SHA256SUMS.txt   integrity:  sha256sum -c SHA256SUMS.txt
requirements.txt
```

## Quick start: process and compare one subject

Process your subject (Tau or FDG PET, from the images):

```bash
bash code/replication_tool/run_public_pipeline.sh <ID> [--tracer FTP|FDG]
```

Several subjects: `code/replication_tool/run_cohort.sh` runs the command above once per subject,
auto-discovered under `MRI_DATA_DIR`.

Compare with the published values:

```bash
python3 code/replication_tool/evaluate_subject.py --type tau --package . \
    --fastsurfer-base <output folder> --subject <ID> \
    --fsroi-list fsroi_list_FTP.csv --lut FreeSurferColorLUT.txt
```

See [docs/REPLICATION.md](docs/REPLICATION.md) for requirements, input file names, FDG/Centiloid,
`run_cohort.sh` usage, comparing three or more subjects, and bilateral regions.

### Centiloid (florbetapir)

`code/centiloid/centiloid_pipeline_tracers.py` goes straight from DICOM to SUVR/Centiloid (it does its own
DICOM-to-NIfTI conversion, so you don't need `dicom_to_nifti.py` for this tracer). Three ways to run it:

```bash
# one subject, to try it out or debug
python3 code/centiloid/centiloid_pipeline_tracers.py --test <SUBJECT_ID> --base_dir <folder from the layout below>

# every subject, writing one CSV with one row each (under results/ by default)
python3 code/centiloid/centiloid_pipeline_tracers.py --all --base_dir <folder from the layout below>

# every subject, also auto-reorienting PET/MRI towards the MNI origin before SPM Coregister --
# rescues subjects whose center of mass is far off, without affecting the ones that were already fine
python3 code/centiloid/centiloid_pipeline_tracers.py --all --auto_reorient --base_dir <folder from the layout below>
```

Without `--auto_reorient`, a subject whose images are far from the MNI origin can fail or come out
misaligned at the SPM Coregister step. `--auto_reorient` is recommended as the default; only skip it if you
already know your data is well-centered.

`--base_dir` is where it looks for everything (defaults to `.`, the current folder, if you omit it):

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

A4 subjects (IDs like `A4:56:571e`) don't fit `--all` above: their IDs and folder layout don't match the
pattern `centiloid_pipeline_tracers.py` expects. `code/centiloid/run_all_A4_florbetapir.sh` works around
this without changing that script: it lists the subject subfolders itself and calls `--test` once per
subject (so it goes through the same pipeline, just told about subjects a different way).

```bash
A4_DATA_DIR=<folder from the layout below> bash code/centiloid/run_all_A4_florbetapir.sh
```

`run_all_A4_florbetapir.sh` passes `--skip_dcm2niix`, so `centiloid_pipeline_tracers.py` does not look for
DICOM or `base_dir` at all for these subjects -- it reads the T1 and PET directly from each subject's own
folder under `A4_DATA_DIR`, and both must already be NIfTI with these exact names (the PET already summed
if it had multiple frames -- not split into separate frame files):

```
<A4_DATA_DIR>/
  A4:56:571e/
    A4:56:571e_t1.nii            T1 (already converted)
    A4:56:571e_pet.nii           PET (already converted and summed)
  A4:35:7415/
    A4:35:7415_t1.nii
    A4:35:7415_pet.nii
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
* `fsroi_list_FTP.csv` (Tau ROI list) and `FreeSurferColorLUT.txt`: obtain them from their original sources.

## Installation

```bash
pip install -r requirements.txt
```

The pipeline script additionally needs Docker and a FreeSurfer license; the Centiloid pipeline needs SPM12
(standalone/MATLAB) and `dcm2niix`; see the header of each script.

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
