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

## Why this matters for `evaluate_subject.py` / `compare_with_published.py`

These tools match your own subject's real ID against the participant column of `data/` to find whether it
is one of the published subjects. Since that column is coded, your real ID never matches a code, even when
the subject genuinely is in the published set -- you just get your own output back, with nothing compared:

**Case 1 -- `--package .` (`data/` as shipped, still coded):**

```
  your subject: B99999999 (real ID)
       |
       v
  evaluate_subject.py  --looks up B99999999 in-->  data/tau_values.csv
                                                      (has A4:999:aaaa, not B99999999)
       |
       v
  NO MATCH  ->  "not among the published values -> only your own output is returned"
       |
       v
  subject_evaluation/
    values_tau.csv            <- only YOUR values, no comparison
```

**Case 2 -- `--package resolved` (`data/` decoded first):**

```
  data/ (coded)
       |
       |  resolve_subjects.py --adni-index ROSTER.csv --a4-index A4_PTDEMOG.csv
       v
  resolved/data/tau_values.csv   <- now has B99999999 (real), not A4:999:aaaa
       |
  your subject: B99999999
       |
       v
  evaluate_subject.py --package resolved  --looks up B99999999 in-->  resolved/data/tau_values.csv
       |
       v
  MATCH  ->  full comparison against the published value
       |
       v
  subject_evaluation/
    values_tau.csv                    <- YOUR values
    B99999999_centiloid_comparison.csv <- AND the comparison against the published reference
```

So resolving (decoding) `data/` first is not optional if you want a comparison against a subject you know
is in the published set: without it, that subject is silently treated as if it were not published at all.

A GAAIN Centiloid Project subject ID (in `data/centiloid_gaain_validation.csv`) is not coded: it is public
reference data, not ADNI/A4 controlled-access data.
