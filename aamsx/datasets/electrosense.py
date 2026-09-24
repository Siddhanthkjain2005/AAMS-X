"""ElectroSense adapter — implemented, currently unreachable.

ElectroSense was a crowdsourced spectrum-monitoring network whose API served
per-sensor power-spectral-density time series.  It is the natural second real
source for AAMS-X, so the adapter exists and is wired into the dataset catalogue.

As of the last check the upstream API is gone:

* ``api.electrosense.org`` — no DNS record at all
* ``electrosense.org`` — resolves, but the host answering it presents a TLS
  certificate for a different name, i.e. the domain is parked rather than serving
  the project
* the IMDEA mirror serves only the single-page web app, not the API

So every fetch here fails with :class:`~aamsx.datasets.callisto.AdapterUnavailable`
and a message that says *why*.  This is deliberate and is the honest state of the
world: the code path is real, the network is gone.  Nothing in this module will
ever substitute generated data for a failed fetch — a missing source is reported,
not filled in.  :func:`status` reports what was actually checked and distinguishes
"not verified" from "verified unreachable" instead of guessing.

Credentials are optional.  ``AAMSX_ELECTROSENSE_USER`` / ``_PASSWORD`` are read
from settings if present, used only in the HTTP Basic header, and never logged,
never echoed in an error message and never placed in provenance.
"""

from __future__ import annotations

import socket
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from urllib.parse import urlparse

import httpx
import numpy as np

from aamsx.config import Settings, get_settings
from aamsx.contracts.spectrum import Provenance, RawRecording, checksum_array
from aamsx.datasets.callisto import AdapterUnavailable
from aamsx.logging import get_logger

log = get_logger(__name__)

ELECTROSENSE_LICENSE = "ElectroSense open data (CC BY-NC-SA 4.0 as published)"
ELECTROSENSE_REFERENCE = (
    "Rajendran et al., 'ElectroSense: Open and Big Spectrum Data', "
    "IEEE Communications Magazine 56(1), 2018"
)
#: Documented aggregation levels of the PSD endpoint, in seconds per row.
AGGREGATIONS = (60, 300, 3600)


@dataclass(frozen=True, slots=True)
class Sensor:
    """One ElectroSense sensor as the ``/sensor/list`` endpoint described it."""

    sensor_id: str
    name: str
    latitude: float | None
    longitude: float | None
    freq_min_mhz: float
    freq_max_mhz: float

    def to_dict(self) -> dict[str, object]:
        return {
            "sensor_id": self.sensor_id,
            "name": self.name,
            # Coarse position only, and only as the network published it. AAMS-X
            # does not geolocate emitters; a receiver's own site is metadata.
            "latitude": self.latitude,
            "longitude": self.longitude,
            "freq_min_mhz": self.freq_min_mhz,
            "freq_max_mhz": self.freq_max_mhz,
        }


def _auth(settings: Settings) -> httpx.BasicAuth | None:
    """Build optional HTTP Basic auth. Values are never logged."""
    user, password = settings.electrosense_user, settings.electrosense_password
    if user and password:
        return httpx.BasicAuth(user, password)
    return None


def host_resolves(url: str, *, timeout: float = 3.0) -> bool:
    """Does the API host have a DNS record? Cheap first gate, no traffic sent."""
    host = urlparse(url).hostname or ""
    if not host:
        return False
    socket.setdefaulttimeout(timeout)
    try:
        socket.getaddrinfo(host, None)
    except OSError:
        return False
    return True


@lru_cache(maxsize=8)
def _probe(api: str, timeout: float) -> tuple[bool, str]:
    """One real request, cached per process so a catalogue render stays cheap."""
    host = urlparse(api).hostname or api
    if not host_resolves(api, timeout=timeout):
        return False, f"{host} has no DNS record; the ElectroSense API was retired"
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(f"{api.rstrip('/')}/sensor/list/")
    except httpx.ConnectError as exc:
        # A parked domain typically fails here: the name resolves, but the host
        # answering it is not the service (wrong TLS certificate, refused port).
        return False, f"{host} resolves but does not serve the API ({_reason(exc)})"
    except httpx.HTTPError as exc:
        return False, f"{host} did not answer ({type(exc).__name__})"
    if response.status_code >= 400:
        return False, f"{host} answered HTTP {response.status_code} for /sensor/list/"
    if "json" not in response.headers.get("content-type", ""):
        return False, f"{host} answered with {response.headers.get('content-type')}, not JSON"
    return True, f"{host} served a JSON sensor list"


def _reason(exc: Exception) -> str:
    """First line of a connection failure, with no URL credentials in it."""
    text = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
    return text[:160]


def status(settings: Settings | None = None, *, probe: bool = False) -> dict[str, object]:
    """Report adapter availability without pretending to have data.

    ``probe=False`` (the default) checks DNS only, so the dataset catalogue can
    call it on every request.  ``probe=True`` makes one cached HTTP request and
    can therefore say *verified* unreachable rather than *unverified*.
    """
    settings = settings or get_settings()
    verified = False
    if not settings.allow_network:
        reachable = False
        detail = "network access disabled (AAMSX_ALLOW_NETWORK=0)"
        verified = True
    elif probe:
        reachable, detail = _probe(settings.electrosense_api, settings.http_timeout_sec)
        verified = True
    elif not host_resolves(settings.electrosense_api):
        host = urlparse(settings.electrosense_api).hostname
        reachable = False
        detail = f"{host} has no DNS record; the ElectroSense API was retired"
        verified = True
    else:
        reachable = False
        detail = (
            f"{urlparse(settings.electrosense_api).hostname} resolves, but the API was "
            "not contacted (pass probe=true to verify)"
        )
    return {
        "adapter": "electrosense",
        "status": "available" if reachable else "unavailable",
        "detail": detail,
        "verified": verified,
        "api": settings.electrosense_api,
        "credentials_configured": bool(_auth(settings)),
        "license": ELECTROSENSE_LICENSE,
        "reference": ELECTROSENSE_REFERENCE,
    }


def _client(settings: Settings) -> httpx.Client:
    if not settings.allow_network:
        raise AdapterUnavailable("network access disabled (AAMSX_ALLOW_NETWORK=0)")
    reachable, detail = _probe(settings.electrosense_api, settings.http_timeout_sec)
    if not reachable:
        raise AdapterUnavailable(detail)
    return httpx.Client(
        base_url=settings.electrosense_api,
        timeout=settings.http_timeout_sec,
        auth=_auth(settings),
        follow_redirects=True,
    )


def _get(settings: Settings, path: str, params: Mapping[str, str | int | float]) -> object:
    try:
        with _client(settings) as client:
            response = client.get(path, params=params)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        # Report the status, never the request headers: they carry the credential.
        raise AdapterUnavailable(
            f"ElectroSense {path} returned HTTP {exc.response.status_code}"
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise AdapterUnavailable(f"ElectroSense {path} unreachable: {type(exc).__name__}") from exc


def list_sensors(settings: Settings | None = None) -> list[Sensor]:
    """List sensors. Raises :class:`AdapterUnavailable` while the API is down."""
    settings = settings or get_settings()
    payload = _get(settings, "/sensor/list/", {})
    rows = payload if isinstance(payload, list) else []
    sensors: list[Sensor] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        position = row.get("sensor_position") or {}
        sensors.append(
            Sensor(
                sensor_id=str(row.get("serial") or row.get("sensorId") or ""),
                name=str(row.get("name") or "unnamed"),
                latitude=_maybe_float(position.get("latitude")),
                longitude=_maybe_float(position.get("longitude")),
                freq_min_mhz=float(row.get("freqMin", 0.0) or 0.0) / 1e6,
                freq_max_mhz=float(row.get("freqMax", 0.0) or 0.0) / 1e6,
            )
        )
    return sensors


def _maybe_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def fetch_raw(
    sensor_id: str,
    start: datetime,
    end: datetime,
    *,
    freq_min_mhz: float,
    freq_max_mhz: float,
    aggregation_sec: int = 60,
    settings: Settings | None = None,
) -> RawRecording:
    """Fetch one sensor's PSD window as a :class:`RawRecording`.

    Mirrors :func:`aamsx.datasets.callisto.fetch_raw` so a recording from either
    source lands in the same cache with the same shape.  Raises
    :class:`AdapterUnavailable` for as long as the upstream API stays offline.
    """
    settings = settings or get_settings()
    if aggregation_sec not in AGGREGATIONS:
        raise ValueError(f"aggregation_sec must be one of {AGGREGATIONS}; got {aggregation_sec}")
    if end <= start:
        raise ValueError("end must be after start")
    if freq_max_mhz <= freq_min_mhz:
        raise ValueError("freq_max_mhz must exceed freq_min_mhz")

    payload = _get(
        settings,
        f"/spectrum/{sensor_id}",
        {
            "timeBegin": int(start.astimezone(UTC).timestamp()),
            "timeEnd": int(end.astimezone(UTC).timestamp()),
            "freqMin": int(freq_min_mhz * 1e6),
            "freqMax": int(freq_max_mhz * 1e6),
            "aggFreq": aggregation_sec,
            "aggFun": "AVG",
        },
    )
    return _to_recording(
        payload,
        sensor_id=sensor_id,
        start=start,
        end=end,
        freq_min_mhz=freq_min_mhz,
        freq_max_mhz=freq_max_mhz,
        aggregation_sec=aggregation_sec,
        settings=settings,
    )


def _to_recording(
    payload: object,
    *,
    sensor_id: str,
    start: datetime,
    end: datetime,
    freq_min_mhz: float,
    freq_max_mhz: float,
    aggregation_sec: int,
    settings: Settings,
) -> RawRecording:
    """Normalise the documented ``{"values": [[t, [dBm...]], ...]}`` response.

    Kept separate from the HTTP call so the parser is testable from a stored
    fixture without a network and without inventing data.
    """
    rows = payload.get("values") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        raise AdapterUnavailable(f"ElectroSense returned no samples for sensor {sensor_id}")
    stamps: list[float] = []
    spectra: list[list[float]] = []
    for row in rows:
        if not isinstance(row, list | tuple) or len(row) != 2:
            continue
        stamp, spectrum = row
        if not isinstance(spectrum, list) or not spectrum:
            continue
        stamps.append(float(stamp))
        spectra.append([float(v) for v in spectrum])
    if not spectra:
        raise AdapterUnavailable(f"ElectroSense payload for {sensor_id} held no usable spectra")
    widths = {len(row) for row in spectra}
    if len(widths) != 1:
        raise AdapterUnavailable(
            f"ElectroSense returned ragged spectra ({sorted(widths)} bins); refusing to pad"
        )

    power_dbm = np.asarray(spectra, dtype=np.float64)
    n_times, n_channels = power_dbm.shape
    floor = float(np.percentile(power_dbm, 1.0))
    digits = np.clip(
        np.rint((power_dbm - floor) / max(settings.db_per_digit, 1e-9)), 0, 255
    ).astype(np.uint8)
    epoch = datetime.fromtimestamp(min(stamps), tz=UTC)
    t_sec = np.asarray([stamp - min(stamps) for stamp in stamps], dtype=np.float64)
    freq_mhz = np.linspace(freq_min_mhz, freq_max_mhz, n_channels, dtype=np.float64)
    provenance = Provenance(
        adapter="electrosense",
        source_id=f"electrosense/{sensor_id}",
        source_url=f"{settings.electrosense_api}/spectrum/{sensor_id}",
        retrieved_at=datetime.now(UTC),
        observed_from=epoch,
        observed_to=datetime.fromtimestamp(max(stamps), tz=UTC),
        n_source_files=1,
        n_samples=int(digits.size),
        freq_resolution_khz=(freq_max_mhz - freq_min_mhz) * 1e3 / max(n_channels, 1),
        time_resolution_sec=float(aggregation_sec),
        preprocessing=(
            f"ElectroSense PSD, AVG aggregation at {aggregation_sec} s",
            f"requested {freq_min_mhz:.3f}-{freq_max_mhz:.3f} MHz over "
            f"{start.isoformat()}..{end.isoformat()}",
            f"dBm quantised to uint8 digits at {settings.db_per_digit} dB/digit, P1 zero point",
            "occupancy labels computed later by the shared calibration policy",
        ),
        license=ELECTROSENSE_LICENSE,
        reference=ELECTROSENSE_REFERENCE,
        checksum=checksum_array(digits, freq_mhz),
        is_synthetic=False,
        notes="Crowdsourced receiver; sensor hardware and siting vary between nodes.",
    )
    log.info(
        "electrosense.fetched",
        extra={"sensor": sensor_id, "steps": n_times, "channels": n_channels},
    )
    return RawRecording(
        digits=digits,
        freq_mhz=freq_mhz,
        t_sec=t_sec,
        epoch_utc=epoch,
        available=np.ones(n_times, dtype=bool),
        provenance=provenance,
    )


def fetch_day(
    sensor_id: str,
    day: datetime,
    *,
    freq_min_mhz: float,
    freq_max_mhz: float,
    hours: float = 12.0,
    settings: Settings | None = None,
) -> RawRecording:
    """Convenience wrapper matching the e-CALLISTO fetch signature."""
    start = day.astimezone(UTC)
    return fetch_raw(
        sensor_id,
        start,
        start + timedelta(hours=hours),
        freq_min_mhz=freq_min_mhz,
        freq_max_mhz=freq_max_mhz,
        settings=settings,
    )
