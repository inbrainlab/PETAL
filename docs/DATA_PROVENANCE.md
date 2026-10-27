# Data provenance (FDG cohort)

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

## Dynamic frames (from the NIfTI headers)

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

## Structural MRI (T1), read from the NIfTI headers

| Cohort (tracers) | T1 files | Matrix (most common) | Voxel size, mm | Scanner information |
|---|---|---|---|---|
| A4 (Tau and amyloid; the same T1 serves both) | 196 participants | 176x240x256 (132), 196x256x256 (40), 170x256x256 (22), 2 others | 1.20x1.05x1.05 (195), 1.20x1.09x1.09 (1) | not available (no JSON sidecars) |
| ADNI (FDG) | 489 | 176x240x256 (167), 196x256x256 (119), 208x240x256 (93), 211x256x256 (40), 170x256x256 (37), 166x256x256 (9), others | 1.0x1.0x1.0 (215), 1.20x1.05x1.05 (115), 1.20x1.00x1.00 (93), 1.20x1.02x1.02 (34), 1.20x0.94x0.94 (14), 1.20x1.25x1.25 (9), others | field strength 3 T (459) and 1.5 T (28), 2 invalid values; Siemens 271, GE 136, Philips 82 (Prisma_fit, Skyra, TrioTim, Ingenia, DISCOVERY MR750, among others) |

The ADNI table counts the T1 files found for the FDG participants, which is more than the 472 participants in
this repository (some participants may have more than one T1, or may be outside the final cohort). The A4 T1 images
share an almost uniform voxel size, whereas the ADNI T1 images differ in voxel size, matrix, scanner
manufacturer and field strength.

## Voxel size ranges (mm, from the NIfTI headers)

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
