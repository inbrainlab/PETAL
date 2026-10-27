# Participant codes (only if your `data/` tables are coded)

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
