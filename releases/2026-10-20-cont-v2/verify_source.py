"""Verify the published text snapshot after a Git checkout; no network/devices."""
from pathlib import Path
import ast
import hashlib
import json

HERE = Path(__file__).resolve().parent
data = json.loads((HERE / "SOURCE_MANIFEST.json").read_text(encoding="utf-8-sig"))
count = 0
for item in data["files"]:
    if not item["included"]:
        continue
    path = HERE / "source" / item["path"]
    text = path.read_text(encoding="utf-8")
    actual = hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()
    if actual != item["lf_sha256"]:
        raise SystemExit("Source fingerprint mismatch: " + item["path"])
    if path.suffix == ".py":
        ast.parse(text, filename=item["path"], feature_version=(3, 10))
    count += 1
print(f"Verified {count} source files; Python 3.10 syntax valid; no hardware accessed.")
