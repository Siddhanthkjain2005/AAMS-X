"""Restore bundled public measured artifacts without network access."""

import json
import shutil

from .catalog import PROCESSED, ROOT, sha256


def restore_bundled():
    bundled = ROOT / "data" / "demo" / "datasets"
    if not bundled.exists():
        return
    PROCESSED.mkdir(parents=True, exist_ok=True)
    raw = ROOT / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    for path in bundled.glob("*.json"):
        manifest = json.loads(path.read_text())
        for suffix, expected in [(".npz", manifest["artifact_sha256"]), (".parquet", manifest.get("parquet_sha256"))]:
            source = bundled / f"{manifest['id']}{suffix}"
            if source.exists() and expected and sha256(source) != expected:
                raise ValueError(f"Bundled dataset checksum mismatch: {source.name}")
            destination = PROCESSED / source.name
            if source.exists() and not destination.exists():
                shutil.copy2(source, destination)
        destination = PROCESSED / path.name
        if not destination.exists():
            shutil.copy2(path, destination)
        source = bundled / manifest["source_file"]
        destination = raw / source.name
        if source.exists() and not destination.exists():
            if sha256(source) != manifest["source_sha256"]:
                raise ValueError("Bundled original source checksum mismatch")
            shutil.copy2(source, destination)


if __name__ == "__main__":
    restore_bundled()
    print("Local public-data bundle restored; no network access required.")
