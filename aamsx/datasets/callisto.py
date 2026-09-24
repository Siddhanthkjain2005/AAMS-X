"""e-CALLISTO adapter: discovery, download and normalisation of real spectrograms.

The e-CALLISTO network publishes ~5000 FITS files per day at
``<archive>/<YYYY>/<MM>/<DD>/<STATION>_<YYYYMMDD>_<HHMMSS>_<focus>.fit.gz``.
Each file is a 15-minute observation.  This adapter turns a station plus a UTC
time range into a single :class:`~aamsx.contracts.spectrum.MeasurementCube`,
recording every archive gap it encountered instead of interpolating over it.
"""

from __future__ import annotations

import concurrent.futures as futures
import gzip
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import httpx
import numpy as np

from aamsx.config import Settings, get_settings
from aamsx.contracts.spectrum import MeasurementCube, Provenance, RawRecording, checksum_array
from aamsx.datasets.calibration import compute_calibration
from aamsx.datasets.fits import CallistoSpectrogram, FitsFormatError, read_callisto
from aamsx.datasets.stations import CALLISTO_LICENSE, CALLISTO_REFERENCE, Station, get_station
from aamsx.logging import get_logger

log = get_logger(__name__)

_FILE_RE = re.compile(
    r"^(?P<station>.+)_(?P<date>\d{8})_(?P<time>\d{6})_(?P<focus>\d{2})\.fit\.gz$"
)
_HREF_RE = re.compile(r'href="([A-Za-z0-9_.\-]+\.fit\.gz)"')


class AdapterUnavailable(RuntimeError):
    """Raised when a remote source cannot be reached and no cache can serve the request."""


@dataclass(frozen=True, slots=True)
class ArchiveFile:
    station: str
    start: datetime
    focus: str
    filename: str
    url: str


def _day_url(settings: Settings, day: date) -> str:
    return f"{settings.callisto_archive}/{day:%Y/%m/%d}/"


def list_day(
    station: str, day: date, *, focus: str | None = None, settings: Settings | None = None
) -> list[ArchiveFile]:
    """List the archive files a station published on ``day`` (UTC).

    ``focus`` pins one interleaved sweep. One physical station publishes several
    focus codes covering different sub-bands; mixing them would silently corrupt
    the frequency axis, so callers should always pin one.
    """
    settings = settings or get_settings()
    if not settings.allow_network:
        raise AdapterUnavailable("network access disabled (AAMSX_ALLOW_NETWORK=0)")
    url = _day_url(settings, day)
    try:
        response = httpx.get(url, timeout=settings.http_timeout_sec, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise AdapterUnavailable(f"cannot list e-CALLISTO archive at {url}: {exc}") from exc

    found: list[ArchiveFile] = []
    for filename in dict.fromkeys(_HREF_RE.findall(response.text)):
        match = _FILE_RE.match(filename)
        if match is None or match.group("station") != station:
            continue
        if focus is not None and match.group("focus") != focus:
            continue
        stamp = datetime.strptime(
            f"{match.group('date')}{match.group('time')}", "%Y%m%d%H%M%S"
        ).replace(tzinfo=UTC)
        found.append(ArchiveFile(station, stamp, match.group("focus"), filename, url + filename))
    found.sort(key=lambda item: (item.start, item.focus))
    return found


def list_range(
    station: str,
    start: datetime,
    end: datetime,
    *,
    focus: str | None = None,
    settings: Settings | None = None,
) -> list[ArchiveFile]:
    """List archive files overlapping ``[start, end)``, crossing UTC day boundaries."""
    settings = settings or get_settings()
    files: list[ArchiveFile] = []
    day = start.date()
    while day <= end.date():
        files.extend(list_day(station, day, focus=focus, settings=settings))
        day += timedelta(days=1)
    window = timedelta(minutes=15)
    return [f for f in files if f.start + window > start and f.start < end]


def fetch_one(file: ArchiveFile, *, settings: Settings | None = None) -> CallistoSpectrogram:
    settings = settings or get_settings()
    try:
        response = httpx.get(file.url, timeout=settings.http_timeout_sec, follow_redirects=True)
        response.raise_for_status()
        raw = gzip.decompress(response.content)
    except (httpx.HTTPError, OSError, EOFError) as exc:
        raise AdapterUnavailable(f"cannot download {file.filename}: {exc}") from exc
    return read_callisto(raw)


def fetch_many(
    files: list[ArchiveFile], *, settings: Settings | None = None
) -> list[tuple[ArchiveFile, CallistoSpectrogram | None]]:
    """Download files concurrently; failures come back as ``None`` rather than exceptions."""
    settings = settings or get_settings()

    def _load(file: ArchiveFile) -> tuple[ArchiveFile, CallistoSpectrogram | None]:
        try:
            return file, fetch_one(file, settings=settings)
        except (AdapterUnavailable, FitsFormatError) as exc:
            log.warning("callisto.file_skipped", extra={"file": file.filename, "error": str(exc)})
            return file, None

    with futures.ThreadPoolExecutor(max_workers=settings.fetch_concurrency) as pool:
        results = list(pool.map(_load, files))
    return results


# --------------------------------------------------------------------------- #
# normalisation: raw receiver digits -> calibrated excess-power cube
# --------------------------------------------------------------------------- #

BASELINE_PERCENTILE = 10.0
"""Default quiet-time baseline quantile.

The median is the conventional choice, but the busiest stations in the network
are occupied for a third of the time, which biases a median baseline upward and
buries real activity.  P10 stays stable at every occupancy level we cache.
"""


def _stack_digits(
    results: list[tuple[ArchiveFile, CallistoSpectrogram | None]],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[tuple[str, str]], int]:
    """Concatenate per-file spectrograms along time, dropping shape-incompatible files."""
    usable = [(f, s) for f, s in results if s is not None]
    if not usable:
        raise AdapterUnavailable("no usable e-CALLISTO files in the requested range")

    channel_counts = np.array([s.n_channels for _, s in usable])
    modal_channels = int(np.bincount(channel_counts).argmax())
    reference = next(s for _, s in usable if s.n_channels == modal_channels)

    blocks: list[np.ndarray] = []
    stamps: list[np.ndarray] = []
    gaps: list[tuple[str, str]] = []
    dropped = 0
    previous_end: float | None = None

    for file, spec in usable:
        if spec.n_channels != modal_channels:
            dropped += 1
            continue
        epoch = file.start.timestamp()
        absolute = epoch + spec.time_sec
        if previous_end is not None and absolute[0] - previous_end > 2.0:
            gaps.append(
                (
                    datetime.fromtimestamp(previous_end, UTC).isoformat(),
                    datetime.fromtimestamp(float(absolute[0]), UTC).isoformat(),
                )
            )
        previous_end = float(absolute[-1])
        blocks.append(spec.digits)
        stamps.append(absolute)

    digits = np.concatenate(blocks, axis=1).T  # -> (T, C)
    absolute_sec = np.concatenate(stamps)
    order = np.argsort(absolute_sec, kind="stable")
    return (
        digits[order],
        absolute_sec[order],
        reference.freq_mhz.astype(np.float64),
        np.ones(order.size, dtype=bool),
        gaps,
        dropped,
    )


def fetch_raw(
    station: str | Station,
    start: datetime,
    end: datetime,
    *,
    settings: Settings | None = None,
    time_decimation: int = 1,
) -> RawRecording:
    """Download and assemble a real observation window as uncalibrated digits."""
    settings = settings or get_settings()
    meta = station if isinstance(station, Station) else get_station(station)
    files = list_range(meta.name, start, end, focus=meta.focus, settings=settings)
    if not files:
        raise AdapterUnavailable(
            f"e-CALLISTO published no {meta.key} files between {start:%Y-%m-%d %H:%M} "
            f"and {end:%Y-%m-%d %H:%M} UTC"
        )
    log.info(
        "callisto.fetch", extra={"station": meta.key, "files": len(files), "start": str(start)}
    )
    results = fetch_many(files, settings=settings)
    digits, absolute_sec, freq_mhz, available, gaps, dropped = _stack_digits(results)

    keep = (absolute_sec >= start.timestamp()) & (absolute_sec < end.timestamp())
    digits, absolute_sec, available = digits[keep], absolute_sec[keep], available[keep]
    if time_decimation > 1:
        digits = digits[::time_decimation]
        absolute_sec = absolute_sec[::time_decimation]
        available = available[::time_decimation]
    if digits.size == 0:
        raise AdapterUnavailable("requested window contains no samples after trimming")

    calibration = compute_calibration(
        digits,
        db_per_digit=settings.db_per_digit,
        percentile=settings.baseline_percentile,
        k_mad=settings.occupancy_k_mad,
        min_excess_db=settings.occupancy_threshold_db,
    )
    dead = (digits.max(axis=0).astype(np.int16) - digits.min(axis=0).astype(np.int16)) <= 1
    cadence = float(np.median(np.diff(absolute_sec))) if absolute_sec.size > 1 else meta.cadence_sec
    steps = [
        f"digits->dB using {settings.db_per_digit} dB/digit (e-CALLISTO nominal scale)",
        f"drift-tracking baseline = P{settings.baseline_percentile:.0f} inside "
        f"{calibration.block_size} sample blocks, interpolated between block centres",
        "excess power = measured - baseline (receiver-independent units)",
        "per-sample noise scale = 1.4826 * MAD(diff(power)) / sqrt(2)",
        f"occupancy label = excess > max({settings.occupancy_threshold_db} dB, "
        f"{settings.occupancy_k_mad} * noise) -- reference label, not absolute truth",
        f"focus code {meta.focus} pinned (station publishes interleaved sweeps)",
    ]
    if time_decimation > 1:
        steps.append(f"time decimation x{time_decimation} (nearest sample)")
    if dropped:
        steps.append(f"dropped {dropped} file(s) with a non-modal channel count")
    if int(dead.sum()):
        steps.append(f"flagged {int(dead.sum())} constant (dead) receiver channels")

    provenance = Provenance(
        adapter="e-callisto",
        source_id=f"{meta.key}@{start:%Y-%m-%dT%H:%MZ}",
        source_url=_day_url(settings, start.date()),
        retrieved_at=datetime.now(UTC),
        observed_from=datetime.fromtimestamp(float(absolute_sec[0]), UTC),
        observed_to=datetime.fromtimestamp(float(absolute_sec[-1]), UTC),
        n_source_files=len(files),
        n_samples=int(digits.size),
        freq_resolution_khz=(
            float(abs(np.median(np.diff(freq_mhz))) * 1000.0) if freq_mhz.size > 1 else None
        ),
        time_resolution_sec=cadence,
        preprocessing=tuple(steps),
        license=CALLISTO_LICENSE,
        reference=CALLISTO_REFERENCE,
        checksum=checksum_array(digits, freq_mhz),
        is_synthetic=False,
        notes=f"{meta.label}, {meta.country} ({meta.continent}) — {meta.band}. {meta.notes}",
        gaps=tuple(gaps),
    )
    return RawRecording(
        digits=np.ascontiguousarray(digits),
        freq_mhz=freq_mhz,
        t_sec=absolute_sec - absolute_sec[0],
        epoch_utc=datetime.fromtimestamp(float(absolute_sec[0]), UTC),
        available=available,
        provenance=provenance,
        calibration=calibration,
        start_step=0,
    )


def build_cube(
    station: str | Station,
    start: datetime,
    end: datetime,
    *,
    settings: Settings | None = None,
    time_decimation: int = 1,
) -> MeasurementCube:
    """Convenience wrapper: fetch then calibrate in one call."""
    settings = settings or get_settings()
    raw = fetch_raw(station, start, end, settings=settings, time_decimation=time_decimation)
    return raw.to_cube(
        db_per_digit=settings.db_per_digit,
        occupancy_threshold_db=settings.occupancy_threshold_db,
        baseline_percentile=settings.baseline_percentile,
        k_mad=settings.occupancy_k_mad,
    )
