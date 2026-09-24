"""Explicit one-time downloads; the application itself never needs the internet."""

import argparse
import os
from pathlib import Path

import httpx

from .catalog import ROOT, TSRD_URL
from .ingest import ingest_callisto, ingest_turing

CALLISTO_RECORDING = "https://soleil.i4ds.ch/solarradio/data/2002-20yy_Callisto/2024/05/10/ALASKA-ANCHORAGE_20240510_160000_01.fit.gz"
TSRD_REVISION = "68a07b0e0189c5b4ec748c4b66dedfe26f8f1c51"


def download(url: str, path: Path, token: str | None = None, max_bytes: int = 64_000_000):
    headers = {"User-Agent": "AAMS-X-public-research-prototype/0.1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with httpx.stream("GET", url, headers=headers, follow_redirects=True, timeout=120) as response:
        if response.status_code in {401, 403}:
            raise RuntimeError("Dataset access approval is required. Accept the publisher's conditions using your own account and set HF_TOKEN locally. Tokens are never saved in provenance.")
        response.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(path.suffix + ".part")
        size = 0
        try:
            with partial.open("wb") as stream:
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError("Download exceeds the configured subset size limit")
                    stream.write(chunk)
            partial.replace(path)
        finally:
            partial.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", choices=["callisto", "turing"])
    args = parser.parse_args()
    if args.source == "callisto":
        path = ROOT / "data" / "raw" / CALLISTO_RECORDING.rsplit("/", 1)[-1]
        if not path.exists():
            download(CALLISTO_RECORDING, path, max_bytes=5_000_000)
        result = ingest_callisto(path, CALLISTO_RECORDING)
    else:
        token = os.getenv("HF_TOKEN")
        if not token:
            raise SystemExit(f"TSRD is gated: accept access conditions at {TSRD_URL} and set HF_TOKEN locally, or import an authorized local HDF5. No synthetic fallback will be labelled official.")
        url = f"{TSRD_URL}/resolve/{TSRD_REVISION}/stare/val_stare/config_0.h5"
        path = ROOT / "data" / "raw" / "tsrd_val_stare_config_0.h5"
        if not path.exists():
            download(url, path, token)
        result = ingest_turing(path, "stare")
    print(f"Installed {result['id']}: {result['category']}, {result['sample_count']:,} cells; SHA-256 {result['source_sha256']}")


if __name__ == "__main__":
    main()
