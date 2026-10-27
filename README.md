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
docs/   detailed reference docs kept out of this README -- INSTALL.md, PIPELINE_STEPS.md, DATA_REFERENCE.md,
        DATA_PROVENANCE.md, PARTICIPANT_CODES.md
MANIFEST.csv, SHA256SUMS.txt   integrity:  sha256sum -c SHA256SUMS.txt
requirements.txt
```

## Participant codes (only if your data/ tables are coded)

In this release the participant column of the tables in `data/` (`subject` or `subject_id`) holds the real ADNI
or A4 identifier directly -- no decoding step is needed to use them as they are. If you are instead working from a
release that ships these tables with a coded participant column, see
[docs/PARTICIPANT_CODES.md](docs/PARTICIPANT_CODES.md) for how to restore the real IDs.

## Quick start: process and compare one subject

1. **Process your subject** (Tau or FDG PET, from the images):

   ```bash
   bash code/replication_tool/run_public_pipeline.sh <ID> [--tracer FTP|FDG]
   ```

   Requirements: Docker (`freesurfer/freesurfer:7.4.1`), a FreeSurfer license (not distributed) and
   `progress_helpers.sh` next to the script. Input: `<PETPIPELINE_BASE>/mri_data/<ID>/<ID>_T1.nii` and the PET
   (`PETPIPELINE_BASE` defaults to `~/Downloads/pet_pipeline` -- no edit needed if you download the repo and run it from `~/Downloads`). Output: `<PETPIPELINE_BASE>/output/<ID>/output.csv` (Tau; with PVC
   also `gtmpvc_T1space_mask.output/gtm.stats.dat`) or `output_fdg.csv` + `output_brainstem_fdg.csv` (FDG).

   Input file names: `<ID>_T1.nii[.gz]` and the PET as `<ID>_FTP.nii` or `<ID>_AV1451.nii` (Tau) or `<ID>_FDG.nii`
   (FDG); alternatively set `PET_GLOB_FTP` / `PET_GLOB_FDG`. Files with other names (for example original ADNI or
   LEADS files) must be renamed or copied with these names. FDG also needs the MATLAB Runtime R2019b (MCRv97) in
   `$PETPIPELINE_BASE/MCRv97`; the container mounts it and FreeSurfer's `segmentBS.sh` uses it to obtain the
   pons mask. Centiloid: `code/centiloid/centiloid_pipeline_tracers.py` (DICOM to SUVR).

   **Several subjects:** `code/replication_tool/run_cohort.sh` runs `run_public_pipeline.sh` once per
   subject (auto-discovered under `MRI_DATA_DIR`), in turn, with one log file per subject:

   ```bash
   nohup bash code/replication_tool/run_cohort.sh [--tracer FTP|FDG] > logs/cohort.out 2>&1 &
   tail -f logs/cohort.out
   ```

   Any flags you pass (for example `--tracer FDG`) are forwarded to `run_public_pipeline.sh` for every
   subject. One subject failing does not stop the rest; see its own log under `logs/<SUBJECT>.log`.
   Re-running the same command later continues where it left off instead of redoing finished subjects.

2. **Compare with the published values.** If `PUBLIC_PACKAGE` (this folder, or the `resolved` folder if your data
   is a coded release -- see [Participant codes](#participant-codes-only-if-your-data-tables-are-coded)), `FS_LUT`
   (`FreeSurferColorLUT.txt`) and
   `FSROI_LIST` (`fsroi_list_FTP.csv` for Tau; FDG uses `data/fsroi_list_FDG.csv`) are defined, the pipeline script
   does this at the end. You can also run it yourself:

   ```bash
   python3 code/replication_tool/evaluate_subject.py --type tau --package . \
       --fastsurfer-base <output folder> --subject <ID> \
       --fsroi-list fsroi_list_FTP.csv --lut FreeSurferColorLUT.txt
   ```

   `--type fdg` works the same way with `--fsroi-list data/fsroi_list_FDG.csv`; `--type centiloid` takes
   `--results <CSV written by centiloid_pipeline_tracers.py>`. If the subject is in `data/`, your values are compared
   with the published ones; if it is not, only your own output is returned and nothing is compared. Use `--all` for
   every subject with output. `fsroi_list_FTP.csv` (Tau) must be obtained from its original source.

3. **Three or more subjects**: `code/replication_tool/compare_with_published.py` computes N, bias, SD, MAE, RMSE,
   MAPE, slope/intercept, R² and ICC(2,1) against the published values. `evaluate_subject.py` writes
   `values_<type>.csv` in the format it reads.

### Bilateral regions

Besides the composites, `evaluate_subject.py` writes the SUVR of every bilateral region (left + right hemisphere):

| File | Content |
|---|---|
| `values_tau_bilateral.csv` | Tau without PVC: 44 regions, hemispheres averaged weighted by volume (mm³); reference = whole cerebellar cortex |
| `values_tau_bilateral_pvc.csv` | Tau with PVC (`mri_gtmpvc`, values already rescaled to the cerebellar cortex): same 44 regions, weighted by number of voxels. Written only if `gtm.stats.dat` exists |
| `values_fdg_bilateral.csv` | FDG without PVC: bilateral regions of `data/fsroi_list_FDG.csv`, weighted by volume (mm³); reference = pons |

Columns: `subject, region, suvr, nvoxels, volume_mm3` (empty for PVC). A region is reported only when both
hemispheres are present in your segmentation. The published counterparts are
`data/tau_bilateral_published.csv`, `data/tau_bilateral_pvc_published.csv` and `data/fdg_bilateral_published.csv`
(same columns). `evaluate_subject.py` does not compare the bilateral tables by itself; use
`code/replication_tool/compare_bilateral.py`, which matches rows on `(subject, region)`:

```bash
python3 code/replication_tool/compare_bilateral.py --mine values_tau_bilateral.csv \
    --published data/tau_bilateral_published.csv
# with PVC:  --mine values_tau_bilateral_pvc.csv --published data/tau_bilateral_pvc_published.csv --pvc
# FDG:       --mine values_fdg_bilateral.csv --published data/fdg_bilateral_published.csv --type fdg
# coded release: use resolved/data/... instead of data/... (see Participant codes)
```

For one subject it lists the regions with the largest differences; for several subjects it reports the MAPE per
region. `--output` saves the per-row comparison.

### Validate your Centiloid pipeline against GAAIN (optional)

`data/centiloid_gaain_validation.csv` holds **our** Centiloid values (Klunk VOIs, standard method, florbetapir) for the
46 GAAIN calibration subjects (45 processed, 1 error: the PET did not overlap the VOI, so the cerebellar reference was
0/NaN). The published GAAIN Centiloid values are not distributed here: download `Avid_Centiloid_standard_method.xlsx`
from GAAIN. To compare your own run:

```bash
python3 code/gaain_validation/klunk_gaain_validation_plot.py --centiloid_results <your CSV> \
    --gaain_xlsx Avid_Centiloid_standard_method.xlsx --out validation.png
```

Your CSV needs the columns `subject_id`, `centiloid_pipeline` and `status` (rows with `ok` are used). Our result:
slope 1.0007, intercept −0.66 CL, R² 0.9925, n = 45/46. The script flags a slope outside 0.98–1.02, an intercept
outside ±2 CL and R² ≤ 0.98 (the criteria set in this script).

See [docs/DATA_REFERENCE.md](docs/DATA_REFERENCE.md) for the data dictionary of every file in `data/`
and for how to interpret the comparison against the published values (what a given % difference does or does not
mean).

## From DICOM to NIfTI

The images used in this work were downloaded from ADNI as DICOM and converted to NIfTI with `dcm2niix`
v1.0.20240202. `code/dicom_to_nifti/dicom_to_nifti.py` runs this conversion in plain Python (no MATLAB); see
[docs/INSTALL.md](docs/INSTALL.md) section 7 for installing `dcm2niix` itself:

```bash
python3 code/dicom_to_nifti/dicom_to_nifti.py all --newdata <downloaded zips / DICOM folders> \
    --raw <output folder>
```

Output: converted NIfTI files organized under `raw/<subject>/...`; `scans_index.csv` (or the name given to
`--out`) with the metadata of every converted scan (subject, scan type, date, image ID and PET resolution);
and, copied straight into `<PETPIPELINE_BASE>/mri_data/<SUBJECT>/<SUBJECT>_T1.nii`, `<SUBJECT>_FTP.nii`,
`<SUBJECT>_FDG.nii`, etc. -- the exact names `run_public_pipeline.sh` expects (see
[Quick start](#quick-start-process-and-compare-one-subject)) -- no manual renaming needed. That last part
uses the same `mri_data` folder `run_public_pipeline.sh` itself defaults to, so you don't need to pass
anything extra for it; pass `--rename <folder>` only to put those renamed files somewhere else. If a subject
has more than one file of the same scan type, the one with the earliest scan date is used.

The script calls the `dcm2niix` command directly, so if it is already on your `PATH` no extra flag is needed.
Only pass `--dcm2niix <path to dcm2niix>` if the binary is not on your `PATH` (the script otherwise defaults to
plain `dcm2niix` and fails with a clear message if it cannot find it).

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
