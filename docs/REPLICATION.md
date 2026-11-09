# Processing and comparing your subjects

## Process your subject

```bash
bash code/replication_tool/run_public_pipeline.sh <ID> [--tracer FTP|FDG]
```

Requirements: Docker (`freesurfer/freesurfer:7.4.1`), a FreeSurfer license (not distributed) and
`progress_helpers.sh` next to the script. Input: `<PETPIPELINE_BASE>/mri_data/<ID>/<ID>_T1.nii` and the PET
(`PETPIPELINE_BASE` defaults to the `pet_pipeline/` folder already shipped in this repo -- no export needed unless you want your data elsewhere). Output: `<PETPIPELINE_BASE>/output/<ID>/output.csv` (Tau; with PVC
also `gtmpvc_T1space_mask.output/gtm.stats.dat`) or `output_fdg.csv` + `output_brainstem_fdg.csv` (FDG).

Input file names: `<ID>_T1.nii[.gz]` and the PET as `<ID>_FTP.nii` or `<ID>_AV1451.nii` (Tau) or `<ID>_FDG.nii`
(FDG); alternatively set `PET_GLOB_FTP` / `PET_GLOB_FDG`. Files with other names (for example original ADNI or
LEADS files) must be renamed or copied with these names. FDG also needs the MATLAB Runtime R2019b (MCRv97) in
`$PETPIPELINE_BASE/MCRv97`; the container mounts it and FreeSurfer's `segmentBS.sh` uses it to obtain the
pons mask. Centiloid: `code/centiloid/centiloid_pipeline_tracers.py` (DICOM to SUVR) -- see the main
README's Centiloid section.

### Resuming from any step

Every step writes its own output file inside `<PETPIPELINE_BASE>/output/<ID>/`, and the script checks for
that file before running the step again. Re-running the *exact same command* does not start over: it skips
every step whose output already exists and continues from the first one that is still missing.

For example, if `recon-all` (STEP 0) already finished for a subject -- `mri/aparc+aseg.mgz` exists -- running

```bash
bash code/replication_tool/run_public_pipeline.sh <ID> [--tracer FTP|FDG]
```

again skips `recon-all` entirely and goes straight to PET processing (STEP 1, "Extract frames"), instead of
spending another 3-4 hours re-running FreeSurfer. The same applies to every later step (coregistration,
frame summing, segstats, PVC, ...): whichever already has output is skipped.

To force a given step -- and everything after it -- to run again, use `--rewrite <N>` with the step number
printed at the start of that step (for example `--rewrite 1` redoes PET processing but not `recon-all`),
`--rewrite 0b` (`talairach.m3z` / `segmentBS.sh`), or `--rewrite all` to start over from `recon-all`.

### Several subjects

`code/replication_tool/run_cohort.sh` runs `run_public_pipeline.sh` once per subject (auto-discovered under
`MRI_DATA_DIR`), in turn, with one log file per subject:

```bash
nohup bash code/replication_tool/run_cohort.sh [--tracer FTP|FDG] > logs/cohort.out 2>&1 &
tail -f logs/cohort.out
```

Any flags you pass (for example `--tracer FDG`) are forwarded to `run_public_pipeline.sh` for every
subject. One subject failing does not stop the rest; see its own log under `logs/<SUBJECT>.log`.
Re-running the same command later continues where it left off instead of redoing finished subjects.

## Compare with the published values

If `PUBLIC_PACKAGE` (this folder, or the `resolved` folder if your data is a coded release), `FS_LUT`
(`FreeSurferColorLUT.txt`) and `FSROI_LIST` (`fsroi_list_FTP.csv` for Tau; FDG uses
`data/fsroi_list_FDG.csv`) are defined, the pipeline script does this at the end. You can also run it
yourself:

```bash
python3 code/replication_tool/evaluate_subject.py --type tau --package . \
    --output_dir <PETPIPELINE_BASE>/output --subject <ID> \
    --fsroi-list fsroi_list_FTP.csv --lut FreeSurferColorLUT.txt
```

`--output_dir` is the folder containing `<subject>/output.csv` (Tau) or `<subject>/output_fdg.csv` +
`output_brainstem_fdg.csv` (FDG) -- the same folder `run_public_pipeline.sh` writes into. It defaults to
`PETPIPELINE_BASE/output`, so it can be omitted if you used that default.

`--type fdg` works the same way with `--fsroi-list data/fsroi_list_FDG.csv`; `--type centiloid` takes
`--results <CSV written by centiloid_pipeline_tracers.py>`. If the subject is in `data/`, your values are
compared with the published ones; if it is not, only your own output is returned and nothing is compared.
Use `--all` for every subject with output. `fsroi_list_FTP.csv` (Tau) must be obtained from its original
source. `FreeSurferColorLUT.txt` is not distributed either, but it ships inside the FreeSurfer Docker
image already required above; copy it out once:

```bash
docker run --rm -v ~/freesurfer:/out freesurfer/freesurfer:7.4.1 \
    cp "$FREESURFER_HOME/FreeSurferColorLUT.txt" /out/FreeSurferColorLUT.txt
```

That matches the `--lut` default (`~/freesurfer/FreeSurferColorLUT.txt`), so once copied it does not
need to be passed by hand either.

## Three or more subjects

`code/replication_tool/compare_with_published.py` computes N, bias, SD, MAE, RMSE, MAPE, slope/intercept,
R² and ICC(2,1) against the published values. `evaluate_subject.py` writes `values_<type>.csv` in the
format it reads.

## Bilateral regions

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
# coded release: use resolved/data/... instead of data/...
```

For one subject it lists the regions with the largest differences; for several subjects it reports the MAPE per
region. `--output` saves the per-row comparison.
