"""Prepare the pinned REopt large-office reference load, online or from a saved CSV."""
import argparse
import base64
import hashlib
import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

if __package__:
    from .fetch_eia import save_dataset
else:
    from fetch_eia import save_dataset


REPO = "NatLabRockies/REopt.jl"
REVISION = "35abb019e29532ef45d4a61c8dcecd2b8cdb74da"
BLOB = "1376130a194518a286b3be267b9176973d062fb7"
PATH = "test/data/loads_kw_largeoffice_sanfran.csv"
SOURCE = f"https://github.com/{REPO}/blob/{REVISION}/{PATH}"
CALENDAR = "Illustrative fixed-hour calendar anchored at Sunday 2017-01-01. Source contains no timestamps."


def convert(raw):
    if hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest() != BLOB:
        raise ValueError("File differs from the pinned REopt Git blob")
    kw = [float(line) for line in raw.decode("ascii").splitlines()]
    if len(kw) != 8760 or not all(math.isfinite(x) and x >= 0 for x in kw):
        raise ValueError("Expected 8760 consecutive nonnegative hourly load values")
    anchor = datetime(2017, 1, 1)
    return [((anchor + timedelta(hours=i)).strftime("%Y-%m-%dT%H:00Z"), value / 1000)
            for i, value in enumerate(kw)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path, help="New directory for normalized CSV and provenance")
    parser.add_argument("--input", type=Path, help="Use a local copy of the pinned CSV")
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error("Please choose a new output directory")
    if args.input:
        raw = args.input.read_bytes()
    else:
        request = Request(f"https://api.github.com/repos/{REPO}/git/blobs/{BLOB}",
                          headers={"Accept": "application/vnd.github+json", "User-Agent": "energy-demand-replay"})
        with urlopen(request, timeout=30) as response:
            raw = base64.b64decode(json.load(response)["content"])
    hourly = convert(raw)
    provenance = {"kind": "public modeled reference profile", "source": SOURCE,
                  "scope": "REopt San Francisco large-office reference load, converted from kW to MW.",
                  "hour_basis": CALENDAR, "source_sha256": hashlib.sha256(raw).hexdigest(),
                  "git_blob": BLOB, "revision": REVISION, "attribution": REPO,
                  "transformation": "One value per hour in source order, kW divided by 1000. Calendar assigned for replay."}
    save_dataset(args.output_dir, hourly, provenance)
    print(f"Saved {len(hourly)} hours to {args.output_dir}")


if __name__ == "__main__":
    main()
