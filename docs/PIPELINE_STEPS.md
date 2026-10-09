# Pipeline Step Reference

Quick reference for every step in `code/replication_tool/run_public_pipeline.sh`,
its output checkpoint file (used by `should_run` to decide whether to
skip it), which tracer(s) it applies to, and its abort/warning gates.

| Step | Description | Checkpoint file | Tracer | Gate behavior |
|---|---|---|---|---|
| 0a | `recon-all -all` (or FastSurfer) on T1 | `mri/aparc+aseg.mgz` | both | No numeric gate here. |
| 0b | Regenerate `talairach.m3z` | `mri/transforms/talairach.m3z` | both | None. |
| 0c | `segmentBS.sh` (pons/brainstem) | `mri/brainstemSsLabels.v13.FSvoxelSpace.mgz` | FDG only (always attempted, skipped for FTP) | None. |
| — | Read NFRAMES from PET header | n/a | both | Aborts if NFRAMES is not a positive integer. |
| — | Acquisition-window sidecar check | n/a | both | Informative warning only, needs a BIDS JSON sidecar. |
| 1 | Extract PET frames | `.frames_done[_fdg]` | both | Aborts if extracted frame count != NFRAMES. |
| 2 | Initial mean of frames | same flag | both | None. |
| 3 | Iteration 1 coreg (frame→mean) | same flag | both | Aborts if aligned frame count != NFRAMES. |
| 4 | Recompute mean from iter-1 aligned frames | same flag | both | None. |
| 5 | Iteration 2 coreg (frame→mean2) | same flag | both | Aborts if aligned frame count != NFRAMES. |
| 6 | Sum aligned frames | `{tau,fdg}_pet_summed.nii` | both | Warns if intensity scale looks unusual. |
| 7 | Cleanup temp frame files | same flag | both | None. |
| 8 | PET→MRI coreg, best of 5 seeded runs | `template_PET2MRI[_fdg].lta` | both | Aborts if no run produced a valid cost; warns if best cost outside [-1.3, -0.8]. |
| 9 | Manual QC (`tkregisterfv`) | n/a | both | Optional and manual (GUI-based); the pipeline does not wait on it and continues regardless. |
| 10 | Reslice PET into MRI space (nearest interp) | `r{tau,fdg}_pet_summed.nii` | both | None. |
| 11 | Invert PET→MRI transform | `template_MRI2PET[_fdg].lta` | both | None. |
| 12 | Generate `rnu.nii` for visual QC | `mri/rnu[_fdg].nii` | both | None. |
| 13 | Project `aparc+aseg` into PET space | `mri/raparc+aseg[_fdg].nii` | both | None. |
| 13b | Project pons/brainstem mask into PET space | `mri/rbrainstemSsLabels_fdg.nii` | FDG only | None. |
| 14 | `mri_segstats` on target regions (no PVC) | `output[_fdg].csv` | both | Aborts if row count <100; warns if != 107. |
| 14b | `mri_segstats` on pons/brainstem | `output_brainstem[_fdg].csv` | FDG only | Aborts if label 174 (pons) missing from output. |
| 15 | `gtmseg` (PVC segmentation) | `mri/gtmseg.mgz` | FTP only | Aborts if label count <100; warns if != 107. |
| 16 | Reslice `gtmseg` to native res | `mri/gtmseg_256.mgz` | FTP only | None. |
| 17 | Identity LTA for PVC | `PET_T1_identity.lta` | FTP only | None. |
| 18 | Auto-threshold PET brain mask | `rPET_bin.nii` | FTP only | Aborts if `mri_binarize` fails; aborts if mask fraction outside [0.15, 0.40]. |
| 19 | Convert `nu.mgz` → `nu.nii` | `mri/nu.nii` | FTP only | None. |
| 20 | `mri_gtmpvc` (partial volume correction) | `gtmpvc_T1space_mask.output/gtm.stats.dat` | FTP only | Aborts if `mri_gtmpvc` fails or output file empty/missing; aborts if row count <90; warns if != 100. |
| — | Final summary + outputs checklist | n/a | both | Prints `check_file` status for every expected output. |

## Resuming and forcing re-runs

The script is resumable: each step is skipped if its checkpoint file
already exists, unless `--rewrite <N>` sets a lower step number (or
`--rewrite all` / `--rewrite 0b` forces specific stages). This means a
failed or interrupted run can simply be re-invoked with the same
arguments and it will pick up where it left off.

FastSurfer (GPU) is available only as a secondary/optional method
inside `run_public_pipeline.sh` itself (`RECON_METHOD=fastsurfer`), for
one subject at a time — there is no separate cohort/batch runner in
this repository.
