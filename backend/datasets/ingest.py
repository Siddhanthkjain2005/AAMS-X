"""Reproducible CLI importers. Raw units and labels remain in Parquet samples."""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
from astropy.io import fits

from .catalog import MEASURED_NOTICE, PROCESSED, TSRD_URL, sha256, write_artifact


def ingest_callisto(path: Path, source_url: str | None = None, directory: Path = PROCESSED, category: str = "REAL_MEASURED_RF") -> dict:
    with fits.open(path, memmap=False) as hdus:
        image = np.array(hdus[0].data, dtype=np.float32)
        header = hdus[0].header
        if image.ndim != 2 or image.size > 4_000_000:
            raise ValueError("Expected a bounded, two-dimensional CALLISTO primary image")
        frequency = time_s = None
        for hdu in hdus[1:]:
            if isinstance(hdu, (fits.BinTableHDU, fits.TableHDU)):
                names = {n.upper(): n for n in hdu.columns.names}
                if "FREQUENCY" in names:
                    frequency = np.asarray(hdu.data[names["FREQUENCY"]][0], dtype=float).ravel()
                if "TIME" in names:
                    time_s = np.asarray(hdu.data[names["TIME"]][0], dtype=float).ravel()
        if frequency is None:
            raise ValueError("FITS must include an explicit FREQUENCY coordinate table; channel indices are not MHz")
        if time_s is None:
            if "CDELT1" not in header or "TIME" not in str(header.get("CTYPE1", "")).upper():
                raise ValueError("FITS time axis is unavailable or unsupported")
            time_s = (np.arange(image.shape[1]) + 1 - header.get("CRPIX1", 1)) * header["CDELT1"] + header.get("CRVAL1", 0)
        if image.shape == (len(frequency), len(time_s)):
            intensity = image.T
        elif image.shape == (len(time_s), len(frequency)):
            intensity = image
        else:
            raise ValueError("FITS coordinate lengths do not match the primary image")
        if not np.isfinite(frequency).all() or not np.isfinite(time_s).all():
            raise ValueError("Nonfinite frequency or time coordinates are not valid")
        if len(np.unique(time_s)) != len(time_s):
            raise ValueError("Duplicate time coordinates require explicit station-specific handling")
        order_t, order_f = np.argsort(time_s), np.argsort(frequency)
        time_s, frequency = time_s[order_t], frequency[order_f]
        intensity = intensity[np.ix_(order_t, order_f)]
        if len(np.unique(frequency)) != len(frequency):
            # Preserve physical coordinates and aggregate repeated channel readings.
            unique = np.unique(frequency)
            merged = []
            for value in unique:
                channel = intensity[:, frequency == value]
                valid = np.isfinite(channel).sum(axis=1)
                merged.append(np.divide(np.nansum(channel, axis=1), valid, out=np.full(len(time_s), np.nan), where=valid > 0))
            intensity = np.stack(merged, axis=1).astype(np.float32)
            frequency = unique
        date = str(header.get("DATE-OBS", "")).replace("/", "-")
        clock = str(header.get("TIME-OBS", "00:00:00"))
        try:
            timestamp = datetime.fromisoformat(date if "T" in date else f"{date}T{clock}").replace(tzinfo=timezone.utc)
            start_utc = timestamp.isoformat()
        except ValueError:
            start_utc = None
        station = str(header.get("INSTRUME", header.get("OBSERVAT", path.name.split("_")[0]))).strip()
        unit = str(header.get("BUNIT", "uncalibrated instrument intensity")).strip()
        source_sha = sha256(path)
        dataset_id = f"callisto-{source_sha[:12]}"
        relative_ms = (time_s - time_s[0]) * 1000
        timestamps = np.repeat(relative_ms, len(frequency))
        samples = pd.DataFrame({"timestamp_ms": timestamps, "frequency_mhz": np.tile(frequency, len(time_s)), "intensity": intensity.ravel(), "station": station, "source_file": path.name})
        if start_utc:
            samples["timestamp_utc"] = pd.Timestamp(start_utc) + pd.to_timedelta(timestamps, unit="ms")
        manifest = {"id": dataset_id, "name": f"e-CALLISTO · {station}", "organization": "e-CALLISTO / FHNW public archive", "category": category, "station": station, "original_format": "FITS", "source_file": path.name, "source_url": source_url, "source_sha256": source_sha, "time_start_utc": start_utc, "raw_time_origin_s": float(time_s[0]), "energy_unit": unit, "note": MEASURED_NOTICE if category == "REAL_MEASURED_RF" else "Explicit synthetic FITS test fixture; not measured RF.", "license": "Public archive; retain station and e-CALLISTO attribution. See publisher terms.", "lineage": ["Original FITS + SHA-256", "Primary image + FREQUENCY / TIME tables", "Sort physical axes; merge duplicate channels", "Retain NaN and irregular coordinates", "Standardized sample Parquet", "NPZ recording + provenance manifest"], "preprocessing": {"missing_values": "Preserved as NaN; never filled with zero", "frequency_unit": "MHz (CALLISTO archive convention)", "time_unit": "seconds in FITS → relative milliseconds", "aggregation": "Duplicate frequencies averaged; no interpolation", "raw_shape": list(image.shape)}}
    return write_artifact(intensity, relative_ms, frequency, manifest, samples=samples, directory=directory)


ALIASES = {
    "toa_us": {"toa", "timeofarrival", "toa us", "timeofarrivalus", "toaus"},
    "frequency_mhz": {"cf", "frequency", "centrefrequency", "centerfrequency", "frequencymhz", "cfmhz"},
    "pulse_width_us": {"pw", "pulsewidth", "pulsewidthus", "pwus"},
    "aoa_deg": {"aoa", "angleofarrival", "aoadeg", "angleofarrivaldeg"},
    "amplitude_db": {"amplitude", "amp", "amplitudedb", "power", "powerdb"},
}


def feature_order(names: list[str]) -> list[int]:
    clean = [re.sub(r"[^a-z0-9]", "", n.lower()) for n in names]
    order = []
    for canonical, aliases in ALIASES.items():
        candidates = [i for i, name in enumerate(clean) if name in aliases or name == canonical.replace("_", "")]
        if len(candidates) != 1:
            raise ValueError(f"Cannot identify {canonical} in HDF5 feature_names; supply --column-order explicitly")
        order.append(candidates[0])
    return order


def ingest_turing(path: Path, receiver_mode: str, directory: Path = PROCESSED, column_order: list[str] | None = None, max_pulses: int = 1_000_000, slots: int = 512, bands: int = 64, category: str = "OFFICIAL_SYNTHETIC_RADAR") -> dict:
    if receiver_mode not in {"stare", "scan"}:
        raise ValueError("Receiver mode must be explicit: stare or scan")
    if not 24 <= slots <= 2000 or not 8 <= bands <= 128 or not 1 <= max_pulses <= 5_000_000:
        raise ValueError("Invalid preprocessing size limits")
    frames, source_metadata = [], {}
    with h5py.File(path, "r") as file:
        if "data" not in file or file["data"].ndim != 2 or file["data"].shape[1] != 5:
            raise ValueError("TSRD requires the publisher's /data N×5 PDW dataset")
        names = column_order
        if "metadata" in file:
            group = file["metadata"]
            for key, value in group.attrs.items():
                if isinstance(value, bytes):
                    value = value.decode()
                if np.ndim(value) == 0:
                    source_metadata[key] = value.item() if isinstance(value, np.generic) else value
            if names is None and "feature_names" in group:
                names = [v.decode() if isinstance(v, bytes) else str(v) for v in group["feature_names"][:]]
        if names is None:
            raise ValueError("HDF5 lacks feature_names; supply the verified --column-order. Units must be ToA/PW µs, CF MHz, AoA degrees, amplitude dB.")
        order = feature_order(names)
        total = len(file["data"])
        count = min(total, max_pulses)
        if count < 2:
            raise ValueError("At least two PDWs are needed for a time-frequency artifact")
        for start in range(0, count, 100_000):
            stop = min(count, start + 100_000)
            data = np.asarray(file["data"][start:stop], dtype=float)[:, order]
            frame = pd.DataFrame(data, columns=list(ALIASES))
            if "labels" in file:
                frame["emitter_id"] = np.asarray(file["labels"][start:stop]).reshape(-1)
            frames.append(frame)
    samples = pd.concat(frames, ignore_index=True)
    if not np.isfinite(samples[list(ALIASES)].to_numpy()).all():
        raise ValueError("Nonfinite PDW features require source-specific correction")
    samples = samples.sort_values("toa_us", kind="stable")
    if samples.toa_us.iloc[-1] <= samples.toa_us.iloc[0]:
        raise ValueError("PDW time span must be positive")
    if (samples.frequency_mhz < 0).any() or (samples.frequency_mhz > 18000).any() or (samples.pulse_width_us < 0).any():
        raise ValueError("PDW values conflict with documented TSRD units/range")
    t_min, t_max = float(samples.toa_us.min()), float(samples.toa_us.max())
    duration_us = t_max - t_min + 1
    ti = np.minimum(slots - 1, ((samples.toa_us.to_numpy() - t_min) / duration_us * slots).astype(int))
    fi = np.minimum(bands - 1, (samples.frequency_mhz.to_numpy() / 18000 * bands).astype(int))
    counts = np.zeros((slots, bands), dtype=np.int32)
    amplitude = np.full((slots, bands), -np.inf, dtype=np.float32)
    np.add.at(counts, (ti, fi), 1)
    np.maximum.at(amplitude, (ti, fi), samples.amplitude_db.to_numpy())
    amplitude[~np.isfinite(amplitude)] = np.nan
    samples["time_slot"] = ti
    samples["frequency_band"] = fi
    source_sha = sha256(path)
    manifest = {"id": f"tsrd-{receiver_mode}-{source_sha[:12]}", "name": f"TSRD · {receiver_mode} · {path.stem}", "organization": "The Alan Turing Institute" if category == "OFFICIAL_SYNTHETIC_RADAR" else "AAMS-X test fixture", "category": category, "original_format": "HDF5 Pulse Descriptor Words", "source_url": TSRD_URL, "source_file": path.name, "source_sha256": source_sha, "receiver_mode": receiver_mode, "source_metadata": source_metadata, "energy_unit": "PDW amplitude (dB)", "emitter_labels_available": "emitter_id" in samples.columns, "pulse_count": len(samples), "original_pulse_count": total, "truncated": count < total, "license": "Apache-2.0 (publisher dataset card)", "note": "Official synthetic radar benchmark. Evaluation truth is occupancy of retained stare-mode pulses, not a claim of uncensored physical transmissions." if receiver_mode == "stare" else "Scan-mode PDWs are already receiver-censored. Empty bins are not ground-truth negatives; full-spectrum truth metrics are unavailable.", "lineage": ["Authorized publisher HDF5 + SHA-256", "Validate feature order / documented units", "Chunked PDW reads (100k rows)", "Sort ToA; bounded prefix with explicit time range", "Time-slot × frequency-band occupancy", "Retain PDW features / emitter labels in Parquet", "NPZ + provenance manifest"], "preprocessing": {"slots": slots, "bands": bands, "max_pulses": max_pulses, "column_order": names, "time_origin_us": t_min, "time_duration_us": duration_us, "frequency_bounds_mhz": [0, 18000], "occupancy": "At least one retained pulse in a time-frequency cell", "amplitude": "Maximum pulse amplitude per cell", "labels": "Emitter IDs are local to this pulse train only", "energy_for_receiver": "Synthetic energy/noise model over PDW occupancy; original amplitude retained for inspection"}}
    return write_artifact(amplitude, np.arange(slots) * duration_us / slots / 1000, (np.arange(bands) + 0.5) * 18000 / bands, manifest, truth=counts > 0 if receiver_mode == "stare" else None, samples=samples, directory=directory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="kind", required=True)
    callisto = sub.add_parser("callisto")
    callisto.add_argument("path", type=Path)
    callisto.add_argument("--source-url")
    turing = sub.add_parser("turing")
    turing.add_argument("path", type=Path)
    turing.add_argument("--receiver-mode", required=True, choices=["stare", "scan"])
    turing.add_argument("--column-order", nargs=5)
    turing.add_argument("--max-pulses", type=int, default=1_000_000)
    turing.add_argument("--slots", type=int, default=512)
    turing.add_argument("--bands", type=int, default=64)
    args = parser.parse_args()
    if args.kind == "callisto":
        result = ingest_callisto(args.path, args.source_url)
    else:
        result = ingest_turing(args.path, args.receiver_mode, column_order=args.column_order, max_pulses=args.max_pulses, slots=args.slots, bands=args.bands)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
