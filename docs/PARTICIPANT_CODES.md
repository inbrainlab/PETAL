# Participant codes

The `data/` tables in this release ship the participant column (`subject` or `subject_id`) with a **code**,
not the ADNI or A4 identifier, so that only people with approved ADNI / A4 access can recover the real
identifiers. Each code looks like:

```
ADNI:<n>:<check>     A4:<n>:<check>        e.g.  ADNI:23:627e
```

`<n>` is the row where that participant first appears in a file that only approved ADNI / A4 users can
download: `ROSTER.csv` (ADNI, column `PTID`) or `A4_PTDEMOG*.csv` (A4, column `BID`); row 1 is the first data
row. `<check>` is a 4-character code that detects a different version of that file. `data/INDEX_FILES.csv`
lists the file names and sha256 of the index versions we used. If your file is a different version,
`resolve_subjects.py` stops without writing anything.

To restore the IDs, with your own copies of the index files:

```bash
python3 code/replication_tool/resolve_subjects.py --data data --out resolved/data \
    --adni-index ROSTER.csv --a4-index A4_PTDEMOG.csv
```

Then use `resolved` as the package folder (`--package resolved`, or `PUBLIC_PACKAGE=resolved`) and
`resolved/data/...` in place of `data/...`. You can give only one index; the other source stays coded. The
tools in `code/replication_tool/` stop with this instruction if they find coded tables. The restored files
contain participant identifiers: keep them inside your approved storage and do not redistribute them.

A code can also appear embedded inside another column (for example `wpet_file` in
`data/centiloid_avid.csv`, a filename that includes the subject ID); `resolve_subjects.py` restores those
too, not just the `subject`/`subject_id` column itself.

A GAAIN Centiloid Project subject ID (in `data/centiloid_gaain_validation.csv`) is not coded: it is public
reference data, not ADNI/A4 controlled-access data.
