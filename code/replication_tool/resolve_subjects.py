#!/usr/bin/env python3
"""
resolve_subjects.py -- restore participant IDs in the data/ tables of this repository.

In this release the participant column holds a code instead of the ADNI / A4 identifier:
    ADNI:<n>:<check>   or   A4:<n>:<check>
<n> is the row where that participant FIRST appears in the roster file you download yourself from
ADNI (ROSTER.csv, column PTID) or A4 (A4_PTDEMOG*.csv, column BID). <check> is a 4-character code that detects a
different version of the file. Only people with access to those files can restore the identifiers.

Usage:
  python3 resolve_subjects.py --data data --out resolved/data --adni-index ROSTER.csv --a4-index A4_PTDEMOG.csv
Then use --package resolved with the tools in code/replication_tool/ (resolved/ contains data/).
Use only the index you have; tables of the other source stay coded.
"""
import argparse
import csv
import hashlib
import os
import re
import shutil
import sys

ID_COLUMNS = ("subject", "subject_id")
CODE = re.compile(r"^(ADNI|A4):(\d+):([0-9a-f]{4})$")
ID_PATTERNS = {"A4": re.compile(r"^B\d{8}$"), "ADNI": re.compile(r"^\d{3}_S_\d{4,5}$")}
INDEX_COLUMNS = {"ADNI": "PTID", "A4": "BID"}


def check_code(source, pid):
    return hashlib.sha256(f"{source}:{pid}".encode()).hexdigest()[:4]


def first_appearance(path, column):
    """{id: row number (1-based, data rows)} using the first row where each id appears."""
    first = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for i, r in enumerate(csv.DictReader(f), 1):
            v = (r.get(column) or "").strip()
            if v and v not in first:
                first[v] = i
    return first


def classify(value):
    for src, rx in ID_PATTERNS.items():
        if rx.match(value):
            return src
    return None


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", required=True, help="folder with the coded CSV tables")
    p.add_argument("--out", required=True, help="output folder (must not exist)")
    p.add_argument("--adni-index", help="ROSTER.csv from ADNI (column PTID)")
    p.add_argument("--a4-index", help="A4_PTDEMOG*.csv from A4 (column BID)")
    a = p.parse_args()
    if not (a.adni_index or a.a4_index):
        p.error("give at least one of --adni-index / --a4-index")
    if os.path.exists(a.out):
        sys.exit(f"ERROR: {a.out} already exists (not overwritten)")

    rev = {}
    for src, path in (("ADNI", a.adni_index), ("A4", a.a4_index)):
        if path:
            fa = first_appearance(path, INDEX_COLUMNS[src])
            rev[src] = {n: pid for pid, n in fa.items()}
            print(f"{src}: {len(fa)} participants in {os.path.basename(path)}")

    os.makedirs(a.out)
    bad, kept_coded, restored = [], 0, 0
    for fn in sorted(os.listdir(a.data)):
        src_path = os.path.join(a.data, fn)
        if not fn.endswith(".csv"):
            shutil.copy2(src_path, os.path.join(a.out, fn))
            continue
        with open(src_path, encoding="utf-8-sig", newline="") as fi:
            rd = csv.reader(fi)
            header = next(rd)
            col = next((header.index(c) for c in ID_COLUMNS if c in header), None)
            rows = []
            for row in rd:
                if col is not None:
                    m = CODE.match(row[col])
                    if m:
                        s, n, ck = m.group(1), int(m.group(2)), m.group(3)
                        if s in rev:
                            pid = rev[s].get(n)
                            if pid is None or check_code(s, pid) != ck:
                                bad.append((fn, row[col]))
                            else:
                                row[col] = pid
                                restored += 1
                        else:
                            kept_coded += 1
                rows.append(row)
        with open(os.path.join(a.out, fn), "w", newline="") as fo:
            w = csv.writer(fo)
            w.writerow(header)
            w.writerows(rows)
    if bad:
        shutil.rmtree(a.out)
        files = sorted({b[0] for b in bad})
        sys.exit(f"ERROR: {len(bad)} codes do not match your index file (different version?). "
                 f"First: {bad[0][1]} in {bad[0][0]}. Files: {files}. Nothing written. "
                 f"Compare your file's checksum with INDEX_FILES.csv.")
    print(f"IDs restored: {restored} | still coded (index not given): {kept_coded}")
    print(f"Written: {a.out}  (use --package {os.path.dirname(os.path.abspath(a.out))})")


if __name__ == "__main__":
    main()
