"""Download SC117 IQ3_XXS + MTP runtime files to C:\\models\\SC117 and verify SHA256 against HF LFS oids."""
import hashlib
import pathlib
import sys
import time

from huggingface_hub import snapshot_download

REPO = "SC117/Qwen3.8-Flash-Next-GSQ-RCO-abliterated-GGUF"
DEST = pathlib.Path(r"C:\models\SC117")
EXPECTED = pathlib.Path(__file__).with_name("sc117-expected-sha256.txt")
PATTERNS = ["IQ3_XXS/*", "mtp-q2_0.gguf", "strata/rt/*"]

t0 = time.time()
snapshot_download(REPO, allow_patterns=PATTERNS, local_dir=str(DEST), max_workers=8)
print(f"download done in {time.time() - t0:.0f}s", flush=True)

bad = 0
for line in EXPECTED.read_text().splitlines():
    oid, size, path = line.split(" ", 2)
    f = DEST / path
    if not f.exists():
        print("MISSING", path, flush=True)
        bad += 1
        continue
    if f.stat().st_size != int(size):
        print("SIZE MISMATCH", path, f.stat().st_size, size, flush=True)
        bad += 1
        continue
    h = hashlib.sha256()
    with open(f, "rb") as fh:
        for chunk in iter(lambda: fh.read(64 << 20), b""):
            h.update(chunk)
    ok = h.hexdigest() == oid
    print("OK " if ok else "BAD", path, h.hexdigest(), flush=True)
    bad += not ok
print("ALL VERIFIED" if bad == 0 else f"{bad} PROBLEMS", flush=True)
sys.exit(1 if bad else 0)
