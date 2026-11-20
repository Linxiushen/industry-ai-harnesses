"""Download the public UCI AI4I benchmark to an explicitly chosen directory."""

import argparse
import hashlib
import io
import json
import urllib.request
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from harness import DOI, read_ai4i


URL = "https://archive.ics.uci.edu/static/public/601/ai4i+2020+predictive+maintenance+dataset.zip"
MIRROR = "https://raw.githubusercontent.com/Edoar-do/AI4I-Predictive-Maintenance/279c6d303c98f713e14df001561cc3e80d2b4d22/ai4i2020.csv"
MIRROR_SHA256 = "dc6630cd9b1f0f853922fad78a1b6436570d3f1ec863f1dd5c4340ac56bc8a8e"
LIMIT = 5_000_000


def prepare(directory, mirror=False):
    target = Path(directory) / "ai4i2020.csv"
    if target.exists():
        raise FileExistsError(target)
    url = MIRROR if mirror else URL
    with urllib.request.urlopen(url, timeout=30) as response:
        payload = response.read(LIMIT + 1)
    if len(payload) > LIMIT:
        raise ValueError("Payload exceeds download limit")
    if mirror:
        if hashlib.sha256(payload).hexdigest() != MIRROR_SHA256:
            raise ValueError("Pinned AI4I mirror SHA-256 mismatch")
        content = payload
    else:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            matches = [e for e in archive.infolist() if Path(e.filename).name == target.name]
            if len(matches) != 1 or matches[0].file_size > LIMIT:
                raise ValueError("Expected one size-bounded ai4i2020.csv in the archive")
            content = archive.read(matches[0])
    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=target.parent) as temporary:
        staged = Path(temporary) / target.name
        staged.write_bytes(content)
        records = read_ai4i(staged)
        if len(records) != 10_000:
            raise ValueError("Unexpected row count for the published AI4I dataset")
        with target.open("xb") as f:
            f.write(content)
    return {"source": url, "doi": DOI, "rows": len(records),
            "download_sha256": hashlib.sha256(payload).hexdigest(),
            "csv_sha256": hashlib.sha256(content).hexdigest()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory")
    parser.add_argument("--mirror", action="store_true", help="Use the pinned, SHA-256-checked public CSV mirror")
    args = parser.parse_args()
    print(json.dumps(prepare(args.directory, args.mirror), indent=2))
