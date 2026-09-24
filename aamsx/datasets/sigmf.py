"""SigMF import adapter — bring your own recording.

SigMF (https://sigmf.org) is the interchange format most SDR tooling can emit, so
this is the route by which a user's own capture becomes an AAMS-X environment
without touching a radio.  Two files are expected: a JSON ``*.sigmf-meta``
describing the capture, and a binary ``*.sigmf-data`` holding the samples.

**Everything here treats the input as hostile.**  An uploaded recording is
attacker-controlled data, so:

* the metadata is parsed as JSON into typed fields — never ``eval``, never
  ``pickle``, never a dynamic import;
* declared geometry is checked against the file's actual size before a single
  sample is read, so a lying header cannot make us allocate 40 GB;
* the sample count, channel count and file size are all capped;
* archive members and filenames are never used to build a path — the caller
  supplies the destination station name, and it is slug-checked;
* nothing is executed, and no field of the metadata reaches a shell.

Only *spectral* SigMF recordings are supported: AAMS-X schedules over a
region x time occupancy grid, so it needs a spectrogram, not IQ.  A complex IQ
recording is converted here by an explicit STFT, and that conversion is written
into the provenance ``preprocessing`` list rather than left implicit.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from aamsx.config import Settings, get_settings
from aamsx.contracts.spectrum import Provenance, RawRecording, checksum_array
from aamsx.logging import get_logger

log = get_logger(__name__)

#: Hard ceilings. A cap that is reached is an error, never a silent truncation.
MAX_META_BYTES = 4 * 1024 * 1024
MAX_CHANNELS = 8192
MAX_SAMPLES = 400_000_000
STATION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

#: dtypes SigMF declares that we accept, mapped to NumPy. Anything else is refused
#: rather than guessed — a wrong guess silently produces plausible nonsense.
DTYPES: dict[str, np.dtype] = {
    "cf32_le": np.dtype("<c8"),
    "cf64_le": np.dtype("<c16"),
    "ci16_le": np.dtype("<i2"),
    "ci8": np.dtype("i1"),
    "rf32_le": np.dtype("<f4"),
    "rf64_le": np.dtype("<f8"),
    "ri16_le": np.dtype("<i2"),
    "ri8": np.dtype("i1"),
    "ru8": np.dtype("u1"),
}
COMPLEX_PREFIXES = ("cf", "ci", "cu")

DEFAULT_FFT = 256


class SigMFError(ValueError):
    """The upload is not a SigMF recording AAMS-X can use."""


def safe_station_name(name: str) -> str:
    """Validate a caller-supplied station name before it becomes a directory."""
    candidate = name.strip()
    if not STATION_PATTERN.match(candidate):
        raise SigMFError(
            "station name must be 1-64 characters of letters, digits, dot, dash or "
            f"underscore; got {name!r}"
        )
    return candidate


def _require(meta: dict[str, Any], section: str) -> dict[str, Any]:
    value = meta.get(section)
    if not isinstance(value, dict):
        raise SigMFError(f"metadata is missing the required {section!r} object")
    return value


def read_metadata(meta_path: Path) -> dict[str, Any]:
    """Parse and sanity-check a ``.sigmf-meta`` file."""
    size = meta_path.stat().st_size
    if size > MAX_META_BYTES:
        raise SigMFError(f"metadata is {size} bytes; the cap is {MAX_META_BYTES}")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SigMFError(f"unreadable SigMF metadata: {exc}") from exc
    if not isinstance(meta, dict):
        raise SigMFError("SigMF metadata must be a JSON object")
    _require(meta, "global")
    return meta


def _captures(meta: dict[str, Any]) -> list[dict[str, Any]]:
    captures = meta.get("captures") or []
    if not isinstance(captures, list) or not captures:
        raise SigMFError("metadata declares no captures")
    if not all(isinstance(entry, dict) for entry in captures):
        raise SigMFError("every capture entry must be an object")
    return captures


def _epoch(captures: list[dict[str, Any]]) -> datetime:
    stamp = captures[0].get("core:datetime")
    if isinstance(stamp, str):
        try:
            return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            log.warning("sigmf.bad_datetime", extra={"value": stamp[:64]})
    return datetime.now(UTC)


def _read_samples(data_path: Path, dtype: np.dtype) -> np.ndarray:
    """Memory-map the payload, refusing a size the declared dtype cannot explain."""
    size = data_path.stat().st_size
    if size == 0:
        raise SigMFError("sample file is empty")
    if size % dtype.itemsize:
        raise SigMFError(
            f"sample file is {size} bytes, not a multiple of the declared "
            f"{dtype.itemsize}-byte dtype"
        )
    count = size // dtype.itemsize
    if count > MAX_SAMPLES:
        raise SigMFError(f"{count} samples exceeds the {MAX_SAMPLES} cap")
    return np.memmap(data_path, dtype=dtype, mode="r")


def _spectrogram(samples: np.ndarray, *, is_complex: bool, n_fft: int) -> np.ndarray:
    """Power spectrogram in dB, either reshaped (already spectral) or via STFT."""
    if not is_complex:
        # Real-valued SigMF from a spectrum analyser: rows are already spectra.
        rows = samples.size // n_fft
        if rows < 2:
            raise SigMFError(
                f"{samples.size} real samples cannot form two spectra of {n_fft} bins; "
                "pass n_fft to match the recording's bin count"
            )
        block = np.asarray(samples[: rows * n_fft], dtype=np.float64).reshape(rows, n_fft)
        return block
    frames = samples.size // n_fft
    if frames < 2:
        raise SigMFError(f"{samples.size} IQ samples is fewer than two {n_fft}-point frames")
    block = np.asarray(samples[: frames * n_fft], dtype=np.complex128).reshape(frames, n_fft)
    window = np.hanning(n_fft)
    spectrum = np.fft.fftshift(np.fft.fft(block * window, axis=1), axes=1)
    power = np.abs(spectrum) ** 2 / max(float(np.sum(window**2)), 1e-12)
    return 10.0 * np.log10(power + 1e-20)


def _to_digits(power_db: np.ndarray, db_per_digit: float) -> np.ndarray:
    """Quantise to the uint8 digit scale the cache stores.

    The cache deliberately keeps *uncalibrated* digits so the calibration policy
    stays a config parameter.  An imported recording is therefore re-expressed on
    the same scale rather than being stored pre-thresholded.
    """
    floor = float(np.percentile(power_db, 1.0))
    scaled = (power_db - floor) / max(db_per_digit, 1e-9)
    return np.clip(np.rint(scaled), 0, 255).astype(np.uint8)


def load_sigmf(
    meta_path: Path | str,
    data_path: Path | str | None = None,
    *,
    n_fft: int = DEFAULT_FFT,
    settings: Settings | None = None,
) -> RawRecording:
    """Import a SigMF pair as a :class:`RawRecording`.

    ``n_fft`` is the STFT length for IQ input, or the declared bin count for a
    recording that is already spectral.
    """
    settings = settings or get_settings()
    meta_path = Path(meta_path)
    data_path = Path(data_path) if data_path else meta_path.with_suffix(".sigmf-data")
    if not meta_path.is_file():
        raise SigMFError(f"no SigMF metadata at {meta_path}")
    if not data_path.is_file():
        raise SigMFError(f"no SigMF sample file at {data_path}")
    total = data_path.stat().st_size + meta_path.stat().st_size
    if total > settings.max_upload_bytes:
        raise SigMFError(
            f"upload is {total / 1e6:.1f} MB; the configured cap is "
            f"{settings.max_upload_bytes / 1e6:.1f} MB (AAMSX_MAX_UPLOAD_BYTES)"
        )
    if n_fft < 8 or n_fft > MAX_CHANNELS or n_fft & (n_fft - 1):
        raise SigMFError(f"n_fft must be a power of two in [8, {MAX_CHANNELS}]; got {n_fft}")

    meta = read_metadata(meta_path)
    globals_ = _require(meta, "global")
    captures = _captures(meta)

    declared = str(globals_.get("core:datatype", ""))
    if declared not in DTYPES:
        raise SigMFError(
            f"unsupported core:datatype {declared!r}; accepted: {', '.join(sorted(DTYPES))}"
        )
    dtype = DTYPES[declared]
    is_complex = declared.startswith(COMPLEX_PREFIXES)

    sample_rate = float(globals_.get("core:sample_rate") or 0.0)
    if sample_rate <= 0.0:
        raise SigMFError("core:sample_rate must be a positive number")
    centre_hz = float(captures[0].get("core:frequency") or 0.0)

    samples = _read_samples(data_path, dtype)
    power_db = _spectrogram(samples, is_complex=is_complex, n_fft=n_fft)
    n_times, n_channels = power_db.shape
    if n_channels > MAX_CHANNELS:
        raise SigMFError(f"{n_channels} channels exceeds the {MAX_CHANNELS} cap")

    digits = _to_digits(power_db, settings.db_per_digit)
    cadence = float(n_fft) / sample_rate
    t_sec = np.arange(n_times, dtype=np.float64) * cadence
    offsets = (np.arange(n_channels) - n_channels / 2) * sample_rate / n_channels
    freq_mhz = (centre_hz + offsets) / 1e6
    if freq_mhz[0] >= freq_mhz[-1]:  # zero or unusable centre frequency
        freq_mhz = np.arange(n_channels, dtype=np.float64)

    epoch = _epoch(captures)
    steps = [
        f"SigMF import: core:datatype {declared}, sample_rate {sample_rate:.0f} Hz",
        (
            f"{n_fft}-point Hann STFT, fftshifted, |X|^2 -> dB"
            if is_complex
            else f"already spectral: reshaped to {n_fft} bins per row"
        ),
        f"quantised to uint8 digits at {settings.db_per_digit} dB/digit, P1 as the zero point",
        "occupancy labels are computed later by the shared calibration policy",
    ]
    digest = hashlib.sha256(meta_path.read_bytes()).hexdigest()[:16]
    provenance = Provenance(
        adapter="sigmf",
        source_id=str(globals_.get("core:description") or meta_path.stem)[:200],
        source_url=f"file://{meta_path.name}",
        retrieved_at=datetime.now(UTC),
        observed_from=epoch,
        observed_to=epoch,
        n_source_files=2,
        n_samples=int(digits.size),
        freq_resolution_khz=float(sample_rate / n_channels / 1e3),
        time_resolution_sec=cadence,
        preprocessing=tuple(steps),
        license=str(globals_.get("core:license") or "declared by the uploader"),
        reference=str(globals_.get("core:author") or "user import"),
        checksum=f"{digest}:{checksum_array(digits)}",
        is_synthetic=False,
        notes=(
            "User-imported recording. AAMS-X did not measure this data and cannot "
            "vouch for its provenance; the fields above are as declared by the "
            "uploader."
        ),
    )
    log.info(
        "sigmf.imported",
        extra={"steps": n_times, "channels": n_channels, "complex": is_complex},
    )
    return RawRecording(
        digits=digits,
        freq_mhz=freq_mhz,
        t_sec=t_sec,
        epoch_utc=epoch,
        available=np.ones(n_times, dtype=bool),
        provenance=provenance,
    )


def import_sigmf(
    meta_path: Path | str,
    data_path: Path | str | None = None,
    *,
    station: str,
    n_fft: int = DEFAULT_FFT,
    settings: Settings | None = None,
) -> Path:
    """Import a SigMF pair straight into the offline cache under ``station``."""
    from aamsx.datasets.store import write_recording

    safe = safe_station_name(station)
    raw = load_sigmf(meta_path, data_path, n_fft=n_fft, settings=settings)
    return write_recording(raw, safe, settings=settings)
