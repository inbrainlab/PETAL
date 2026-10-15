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
data/   Values produced by the authors' pipelines (one CSV per analysis) - see the data dictionary below
code/
  replication_tool/   process your subject and compare it with the published values; check_install.sh verifies the setup; resolve_subjects.py restores IDs if a release ships coded tables
  centiloid/          Centiloid pipeline (DICOM -> SUVR) and comparison with the A4 reference
  tau_fdg/            cohort-level comparison scripts for Tau and FDG (they need the reference data)
  gaain_validation/   validation of a Centiloid pipeline against the GAAIN Centiloid Project
  dicom_to_nifti/     DICOM -> NIfTI conversion and organisation of downloaded ADNI scans (no MATLAB)
MANIFEST.csv, SHA256SUMS.txt   integrity:  sha256sum -c SHA256SUMS.txt
requirements.txt
```

## Participant codes (only if your data/ tables are coded)

In this release the participant column of the tables in `data/` (`subject` or `subject_id`) holds the real ADNI
or A4 identifier directly -- no decoding step is needed to use them as they are.

Some releases of this repository instead ship these tables with a coded participant column, so that only people
with approved ADNI/A4 access can recover the real identifiers. If you are working from one of those releases, each
code looks like:

```
ADNI:<n>:<check>     A4:<n>:<check>        e.g.  ADNI:23:627e
```

`<n>` is the row where that participant first appears in a file that only approved ADNI / A4 users can download:
`ROSTER.csv` (ADNI, column `PTID`) or `A4_PTDEMOG*.csv` (A4, column `BID`); row 1 is the first data row. `<check>` is
a 4-character code that detects a different version of that file. A coded release also ships `data/INDEX_FILES.csv`,
listing the file names and sha256 of the index versions used.

To restore the IDs in a coded release, with your own copies of the index files:

```bash
python3 code/replication_tool/resolve_subjects.py --data data --out resolved/data \
    --adni-index ROSTER.csv --a4-index A4_PTDEMOG.csv
```

Then use `resolved` as the package folder (`--package resolved`, or `PUBLIC_PACKAGE=resolved`) and
`resolved/data/...` in place of `data/...`. You can give only one index; the other source stays coded. The tools in
`code/replication_tool/` stop with this instruction if they find coded tables. The restored files contain participant
identifiers: keep them inside your approved storage and do not redistribute them.

## Quick start: process and compare one subject

1. **Process your subject** (Tau or FDG PET, from the images):

   ```bash
   bash code/replication_tool/run_public_pipeline.sh <ID> [--tracer FTP|FDG]
   ```

   Requirements: Docker (`freesurfer/freesurfer:7.4.1`), a FreeSurfer license (not distributed) and
   `progress_helpers.sh` next to the script. Input: `<FASTSURFER_BASE>/mri_data/<ID>/<ID>_T1.nii` and the PET
   (`FASTSURFER_BASE` defaults to `~/Downloads/pet_pipeline` -- no edit needed if you download the repo and run it from `~/Downloads`). Output: `<FASTSURFER_BASE>/output/<ID>/output.csv` (Tau; with PVC
   also `gtmpvc_T1space_mask.output/gtm.stats.dat`) or `output_fdg.csv` + `output_brainstem_fdg.csv` (FDG).

   Input file names: `<ID>_T1.nii[.gz]` and the PET as `<ID>_FTP.nii` or `<ID>_AV1451.nii` (Tau) or `<ID>_FDG.nii`
   (FDG); alternatively set `PET_GLOB_FTP` / `PET_GLOB_FDG`. Files with other names (for example original ADNI or
   LEADS files) must be renamed or copied with these names. FDG also needs the MATLAB Runtime R2019b (MCRv97) in
   `$FASTSURFER_BASE/MCRv97`; the container mounts it and FreeSurfer's `segmentBS.sh` uses it to obtain the
   pons mask. Centiloid: `code/centiloid/centiloid_pipeline_tracers.py` (DICOM to SUVR).

2. **Compare with the published values.** If `PUBLIC_PACKAGE` (this folder, or the `resolved` folder if your data
   is a coded release -- see [Participant codes](#participant-codes-only-if-your-data-tables-are-coded)), `FS_LUT`
   (`FreeSurferColorLUT.txt`) and
   `FSROI_LIST` (`fsroi_list_FTP.csv` for Tau; FDG uses `data/fdg_config_rois.csv`) are defined, the pipeline script
   does this at the end. You can also run it yourself:

   ```bash
   python3 code/replication_tool/evaluate_subject.py --type tau --package . \
       --fastsurfer-base <output folder> --subject <ID> \
       --fsroi-list fsroi_list_FTP.csv --lut FreeSurferColorLUT.txt
   ```

   `--type fdg` works the same way with `--fsroi-list data/fdg_config_rois.csv`; `--type centiloid` takes
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
| `values_fdg_bilateral.csv` | FDG without PVC: bilateral regions of `data/fdg_config_rois.csv`, weighted by volume (mm³); reference = pons |

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

## How to read the differences

One subject compares one value with one value: it shows whether your installation resembles ours, not agreement.
No pass/fail threshold is applied, and the paper's figures (this work vs the reference) are shown only as context.

Whether an error below 1% is small enough depends on the variability that the measurement already carries. For
flortaucipir, the standard deviation of the test–retest change in cortical SUVR ranged from 1.5% to 5.0% across regions
(Devous et al., 2018), and the longitudinal measurement error of a temporal meta-ROI referenced to the cerebellum
without PVC, the configuration reproduced here, has been estimated at about 2–3% (Schwarz et al., 2021). The global and
meta-temporal reproduction errors obtained for tau (0.45% and 0.25%) are therefore an order of magnitude below the
variability between two scans of the same participant, so that regenerating the reference values from their
documentation adds little to the uncertainty already inherent in the measurement.

The same comparison shows where reproduction does matter: **PVC-corrected values in small structures**, with mean
errors of 2–3% and individual errors of up to 25% (Section 4.2 of the paper), reach or exceed that variability. The
tools print this note after each comparison.

**Processing note.** The published Tau/FDG values were produced from a FreeSurfer 7.4.1 run done beforehand with the
same container image (`freesurfer/freesurfer:7.4.1`) and then processed with this script; the script itself runs
`recon-all` with that same image. Small differences are therefore expected if you run `recon-all` from scratch.

## Data dictionary (`data/`)

| File | Content |
|---|---|
| `tau_values.csv` | Tau PET: participant × composite region, 196 × 7 = 1,372 rows |
| `fdg_values.csv` | FDG PET: 472 participants; 3,301 rows = 472 × 7 − 3 (N = 471 for entorhinal, parahippocampal and meta_temporal: one participant lacks labels) |
| `tau_bilateral_published.csv` | Tau PET without PVC: 196 participants × 44 bilateral regions = 8,624 rows (`subject, region, suvr, nvoxels, volume_mm3`); volume-weighted |
| `tau_bilateral_pvc_published.csv` | Tau PET with PVC (`mri_gtmpvc`): 196 × 44 = 8,624 rows; voxel-weighted |
| `fdg_bilateral_published.csv` | FDG PET without PVC: 472 participants, 22,654 rows (46–48 bilateral regions per participant; one participant lacks entorhinal and parahippocampal); volume-weighted |
| `centiloid_avid.csv` | Florbetapir: 182 processed; 164 ok, 18 error (17 of them reoriented) |
| `centiloid_voi_values.csv` | 164 participants × 7 VOIs, own values only |
| `centiloid_gm_6vois.csv` | Gray-matter values for the 6 VOIs, n = 164 |
| `centiloid_gaain_validation.csv` | GAAIN Centiloid Project validation: 46 subjects, 45 ok, 1 error; own values only |
| `klunk_composite.csv` | Parietal and precuneus from the Klunk zones; the other four from the Avid VOIs |
| `fdg_config_rois.csv` | ROI configuration (label lists) used for FDG |
| `tau_composites.csv`, `fdg_composites.csv`, `fdg_by_region.csv`, `centiloid_voi_agreement.csv`, `tau_summary.csv`, `fdg_summary.csv` | Agreement summaries of this work against the reference; the reference values themselves are not distributed |

Rows are keyed by the participant identifiers of the source studies (A4/LEARN and the FDG cohort), so that the values
can be merged with the data obtained from the original providers and the analyses replicated.

## From DICOM to NIfTI

The images used in this work were downloaded from ADNI as DICOM and converted to NIfTI with `dcm2niix`
v1.0.20240202. `code/dicom_to_nifti/dicom_to_nifti.py` runs this conversion in plain Python (no MATLAB):

```bash
python3 code/dicom_to_nifti/dicom_to_nifti.py all --newdata <downloaded zips / DICOM folders> \
    --raw <output folder>
```

Steps (also available one by one): `unzip`, `convert` (`dcm2niix -d 9 -o <folder> <folder>`, default output names,
only for folders with DICOMs and no NIfTI), `organize` (move to `raw/<subject>/...`) and `index` (writes the
metadata of every converted scan -- subject, scan type, date, image ID and PET resolution -- into a CSV; this is
the only step that actually writes `--out`, which is optional and defaults to `scans_index.csv` in the current
directory, so pass it only if you want a different name or location). `code/dicom_to_nifti/compare_nifti.py`
compares data, affine and header of two folders of NIfTI files by name, if you want to check a conversion against
another one.

The script calls the `dcm2niix` command directly, so if it is already on your `PATH` no extra flag is needed.
Only pass `--dcm2niix <path to dcm2niix>` if the binary is not on your `PATH` (the script otherwise defaults to
plain `dcm2niix` and fails with a clear message if it cannot find it).

## Data provenance (FDG cohort)

The 472 FDG participants carry ADNI identifiers (`NNN_S_NNNN`). Their FDG scans were acquired between
2007-10-26 and 2023-03-23. Assigning each scan to the ADNI phase that was running on its acquisition date (approximate
boundaries, since phases overlap in practice) gives:

| ADNI period (by scan date) | Participants |
|---|---|
| ADNI1 (before 2009-10) | 5 |
| ADNI-GO (2009-10 to 2011-08) | 25 |
| ADNI2 (2011-09 to 2016-08) | 202 |
| ADNI3 (2016-09 to 2022-08) | 237 |
| ADNI4 (2022-09 onwards) | 3 |

The cohort is therefore **not** restricted to ADNI3. Each participant contributes one scan. Data used in this work
were obtained from the Alzheimer's Disease Neuroimaging Initiative (ADNI) database (adni.loni.usc.edu); ADNI
investigators contributed to the design and implementation of ADNI and/or provided data but did not participate in
the analysis or writing of this work.

### Dynamic frames (from the NIfTI headers)

| Tracer | Frames | Files inspected |
|---|---|---|
| Flortaucipir (A4) | 6 | 197 (all with 6 frames) |
| Florbetapir (A4) | 4 | 15 (all with 4 frames); the other participants were processed from DICOM and were not inspected |
| FDG (ADNI) | 1 | 489 (all 1 frame, 160 x 160 x 96) |

The number of frames was read from the fourth dimension of the NIfTI header. Frame durations and acquisition
windows were not verified here.

The FDG input is the ADNI preprocessed series *Coreg, Avg, Std Img and Vox Siz, Uniform 6mm Res* (uniform 6 mm
resolution): ADNI had already averaged the frames, so the frame count of the original acquisition is not available
from these data. The acquisition date of each scan is taken from the folder name of the downloaded series.

### Structural MRI (T1), read from the NIfTI headers

| Cohort (tracers) | T1 files | Matrix (most common) | Voxel size, mm | Scanner information |
|---|---|---|---|---|
| A4 (Tau and amyloid; the same T1 serves both) | 196 participants | 176x240x256 (132), 196x256x256 (40), 170x256x256 (22), 2 others | 1.20x1.05x1.05 (195), 1.20x1.09x1.09 (1) | not available (no JSON sidecars) |
| ADNI (FDG) | 489 | 176x240x256 (167), 196x256x256 (119), 208x240x256 (93), 211x256x256 (40), 170x256x256 (37), 166x256x256 (9), others | 1.0x1.0x1.0 (215), 1.20x1.05x1.05 (115), 1.20x1.00x1.00 (93), 1.20x1.02x1.02 (34), 1.20x0.94x0.94 (14), 1.20x1.25x1.25 (9), others | field strength 3 T (459) and 1.5 T (28), 2 invalid values; Siemens 271, GE 136, Philips 82 (Prisma_fit, Skyra, TrioTim, Ingenia, DISCOVERY MR750, among others) |

The ADNI table counts the T1 files found for the FDG participants, which is more than the 472 participants in
this repository (some participants may have more than one T1, or may be outside the final cohort). The A4 T1 images
share an almost uniform voxel size, whereas the ADNI T1 images differ in voxel size, matrix, scanner
manufacturer and field strength.

### Voxel size ranges (mm, from the NIfTI headers)

| Image | Files | Axis 1 | Axis 2 | Axis 3 |
|---|---|---|---|---|
| T1, A4 | 196 | 1.20 | 1.05 - 1.09 | 1.05 - 1.09 |
| T1, ADNI | 489 | 0.94 - 1.20 | 0.94 - 1.25 | 0.94 - 1.25 |
| PET Flortaucipir, A4 | 196 | 2.00 - 3.18 | 2.00 - 3.18 | 1.50 - 4.00 |
| PET Florbetapir, A4 | 14 (NIfTI files only) | 2.53 - 3.18 | 2.53 - 3.18 | 1.50 - 4.00 |
| PET FDG, ADNI (preprocessed) | 489 | 1.50 | 1.50 | 1.50 |

Axes follow the order stored in each file. The FDG voxel size is the grid of the preprocessed series, not its
effective resolution (the series is delivered at uniform 6 mm resolution). The Florbetapir range comes only from the
files available as NIfTI; the remaining participants were processed from DICOM and were not inspected.

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
