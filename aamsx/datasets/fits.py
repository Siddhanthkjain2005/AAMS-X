"""Minimal, dependency-free FITS reader for e-CALLISTO spectrogram files.

CALLISTO products are deliberately simple FITS files:

* a primary HDU holding an ``uint8`` image of shape ``(n_channels, n_times)``
  in "digits" (the raw ADC scale of the receiver), and
* a single ``BINTABLE`` extension whose two fields carry the physical time
  axis (seconds since the start of the observation) and the frequency axis
  (MHz, normally in descending order).

``astropy`` would read this too, but it is a heavy dependency for a format
that is 30 lines of parsing, and AAMS-X must install quickly on a laptop.
The reader is intentionally strict: anything unexpected raises
:class:`FitsFormatError` rather than silently producing a wrong cube.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

BLOCK = 2880
CARD = 80

_TFORM_RE = re.compile(r"^\s*(\d*)\s*([A-Z])")


class FitsFormatError(ValueError):
    """Raised when a byte stream does not conform to the FITS subset we accept."""


@dataclass(frozen=True, slots=True)
class CallistoSpectrogram:
    """A decoded CALLISTO observation."""

    digits: np.ndarray  # uint8, shape (n_channels, n_times)
    freq_mhz: np.ndarray  # float64, shape (n_channels,)
    time_sec: np.ndarray  # float64, shape (n_times,), seconds from obs start
    header: dict[str, str]

    @property
    def n_channels(self) -> int:
        return int(self.digits.shape[0])

    @property
    def n_times(self) -> int:
        return int(self.digits.shape[1])


def _parse_header(buf: bytes, offset: int) -> tuple[dict[str, str], int]:
    header: dict[str, str] = {}
    while True:
        block = buf[offset : offset + BLOCK]
        if len(block) < BLOCK:
            raise FitsFormatError("truncated FITS header block")
        offset += BLOCK
        for i in range(0, BLOCK, CARD):
            card = block[i : i + CARD].decode("ascii", "replace")
            key = card[:8].strip()
            if key == "END":
                return header, offset
            if card[8:10].strip() == "=":
                value = card[10:].split("/")[0].strip()
                header[key] = value.strip().strip("'").strip()


def _tform_count_and_code(tform: str) -> tuple[int, str]:
    match = _TFORM_RE.match(tform)
    if match is None:
        raise FitsFormatError(f"unparsable TFORM {tform!r}")
    count = int(match.group(1) or "1")
    return count, match.group(2)


_TFORM_DTYPE = {"D": ">f8", "E": ">f4", "J": ">i4", "I": ">i2", "B": "u1"}


def read_callisto(buf: bytes) -> CallistoSpectrogram:
    """Decode a CALLISTO ``.fit`` byte string (already gunzipped)."""
    if not buf.startswith(b"SIMPLE"):
        raise FitsFormatError("not a FITS file (missing SIMPLE keyword)")
    header, offset = _parse_header(buf, 0)
    try:
        naxis1 = int(header["NAXIS1"])
        naxis2 = int(header["NAXIS2"])
        bitpix = int(header["BITPIX"])
    except (KeyError, ValueError) as exc:  # pragma: no cover - malformed input
        raise FitsFormatError(f"missing/invalid primary axes: {exc}") from exc
    if bitpix != 8:
        raise FitsFormatError(f"expected 8-bit CALLISTO image, got BITPIX={bitpix}")

    n_bytes = naxis1 * naxis2
    payload = buf[offset : offset + n_bytes]
    if len(payload) < n_bytes:
        raise FitsFormatError("truncated CALLISTO image data")
    digits = np.frombuffer(payload, dtype=np.uint8).reshape(naxis2, naxis1)

    ext_offset = offset + ((n_bytes + BLOCK - 1) // BLOCK) * BLOCK
    freq_mhz, time_sec = _read_axes(buf, ext_offset, naxis1, naxis2, header)
    return CallistoSpectrogram(digits=digits, freq_mhz=freq_mhz, time_sec=time_sec, header=header)


def _synthetic_axes(
    n_times: int, n_channels: int, header: dict[str, str]
) -> tuple[np.ndarray, np.ndarray]:
    """Fall back to the linear WCS keywords when the BINTABLE is unusable."""
    cdelt1 = float(header.get("CDELT1", 0.25) or 0.25)
    crval2 = float(header.get("CRVAL2", 0.0) or 0.0)
    cdelt2 = float(header.get("CDELT2", -1.0) or -1.0)
    time_sec = np.arange(n_times, dtype=np.float64) * cdelt1
    freq_mhz = crval2 + np.arange(n_channels, dtype=np.float64) * cdelt2
    return freq_mhz, time_sec


def _read_axes(
    buf: bytes, offset: int, n_times: int, n_channels: int, primary: dict[str, str]
) -> tuple[np.ndarray, np.ndarray]:
    if offset >= len(buf):
        return _synthetic_axes(n_times, n_channels, primary)
    try:
        header, data_offset = _parse_header(buf, offset)
    except FitsFormatError:
        return _synthetic_axes(n_times, n_channels, primary)
    if header.get("XTENSION") != "BINTABLE" or int(header.get("TFIELDS", 0)) < 2:
        return _synthetic_axes(n_times, n_channels, primary)

    row_bytes = int(header["NAXIS1"])
    raw = buf[data_offset : data_offset + row_bytes]
    if len(raw) < row_bytes:
        return _synthetic_axes(n_times, n_channels, primary)

    cursor = 0
    fields: list[np.ndarray] = []
    for index in (1, 2):
        count, code = _tform_count_and_code(header[f"TFORM{index}"])
        dtype = _TFORM_DTYPE.get(code)
        if dtype is None:
            return _synthetic_axes(n_times, n_channels, primary)
        width = np.dtype(dtype).itemsize * count
        fields.append(np.frombuffer(raw[cursor : cursor + width], dtype=dtype).astype(np.float64))
        cursor += width

    time_sec, freq_mhz = fields[0], fields[1]
    if time_sec.size != n_times or freq_mhz.size != n_channels:
        return _synthetic_axes(n_times, n_channels, primary)
    if not np.all(np.isfinite(freq_mhz)) or float(np.ptp(freq_mhz)) <= 0.0:
        return _synthetic_axes(n_times, n_channels, primary)
    return freq_mhz, time_sec
