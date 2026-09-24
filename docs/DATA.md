# Data sources, ingestion and provenance

## Categories are part of the experiment identity

`CONTROLLED_SIMULATION`, `OFFICIAL_SYNTHETIC_RADAR`, and `REAL_MEASURED_RF` are carried through the catalog, environment metadata, experiment registry, UI, and exports. A missing dataset is never replaced under a different provenance badge.

## Turing Synthetic Radar Dataset

- Publisher: **The Alan Turing Institute**.
- Dataset: https://huggingface.co/datasets/alan-turing-institute/turing-synthetic-radar-dataset
- Reference implementation and schema: https://github.com/alan-turing-institute/turing-deinterleaving-challenge
- Paper: Gunn, Hosford, Jones, Zeitler, Groves & Nockles (2026), *The Turing Synthetic Radar Dataset: A dataset for pulse deinterleaving*, https://arxiv.org/abs/2602.03856
- License: Apache-2.0, according to the publisher's dataset card.
- Download access: publisher-gated. The account holder must accept the publisher's conditions. **No authorized TSRD file was available in this build environment.**

The importer supports the publisher's HDF5 `/data` N×5 array, optional `/labels`, and `/metadata/feature_names`. It maps verified feature names to:

| Field | Unit |
|---|---|
| `toa_us` | microseconds |
| `frequency_mhz` | MHz |
| `pulse_width_us` | microseconds |
| `aoa_deg` | degrees |
| `amplitude_db` | publisher amplitude in dB |

If feature names are absent, specify a verified column order explicitly, e.g. `--column-order ToA CF PW AoA Amplitude`. The importer rejects unidentified features rather than guessing. Emitter IDs are retained and are local to a pulse train, not universal identities.

```bash
.venv/bin/python -m backend.datasets.ingest turing data/raw/config_0.h5 \
  --receiver-mode stare --max-pulses 1000000 --slots 512 --bands 64
```

The reader processes 100,000-row chunks and keeps a bounded prefix. It records original and retained pulse counts, truncation, time origin/span, column mapping and frequency bounds. Time-frequency occupancy is “at least one retained pulse in a cell”; source PDWs and labels stay in Parquet. Maximum amplitude per occupied cell is retained in the NPZ inspector artifact.

The receiver evaluation reconstructs an energy/noise model over that **source-derived occupancy**. It does not pretend the modeled receiver energy is a measured waveform. A short prefix can require a shorter horizon or lower retune/dwell costs to fit the recording's physical time span; incompatible timing is rejected.

**Stare mode** can supply retained-pulse occupancy truth across the source grid. Missing/dropped source pulses still limit what this means. **Scan mode** is already receiver-censored: absent pulses do not justify full-spectrum negative labels, so truth-dependent metrics are disabled.

To download the pinned validation file after publisher approval:

```bash
# Set HF_TOKEN in your local shell; it is not written to any manifest.
.venv/bin/python -m backend.datasets.fetch turing
```

Pinned publisher revision: `68a07b0e0189c5b4ec748c4b66dedfe26f8f1c51`; file: `stare/val_stare/config_0.h5`. Authorized local imports also work independently of this convenience downloader.

## e-CALLISTO measured recording

- Network information: https://www.e-callisto.org/
- Archive: https://soleil.i4ds.ch/solarradio/
- Included source: https://soleil.i4ds.ch/solarradio/data/2002-20yy_Callisto/2024/05/10/ALASKA-ANCHORAGE_20240510_160000_01.fit.gz
- Station: `ALASKA-ANCHORAGE`.
- FITS observation timestamp: `2024-05-10T16:00:00.815000+00:00`.
- Source SHA-256: `7ae33ddb2f697f7ef1623ef8f5d5e3610660f4facd3600cc8c823de5337b1a3a`.
- Original image: 200 channels × 3,600 time samples.
- Standardized array: 3,600 time samples × 196 distinct frequencies, **705,600 values**.
- Frequency coordinates: **5.0–65.875 MHz**, as supplied in this recording's frequency table; do not replace station coordinates with the instrument's nominal tuning range.
- Time step: 0.25 s; recorded coordinate interval: 0–899.75 s.
- Original intensity unit: **digits**, not calibrated dBm.

The archive is publicly accessible. Retain the station, e-CALLISTO network and FHNW archive attribution; consult publisher terms for intended redistribution. A content hash establishes byte integrity, not independent authentication of the publisher.

The importer requires explicit frequency coordinates, validates the time axis, sorts physical axes, averages duplicate frequency channels, preserves missing values as NaN, and never fills empty channels with zero. It writes:

```text
callisto-<source-hash-prefix>.npz
  intensity[T, F]         float32, original instrument units
  time_ms[T]              float64, relative time
  frequency_mhz[F]        float64, actual coordinates

callisto-<source-hash-prefix>.parquet
  timestamp_ms, timestamp_utc, frequency_mhz, intensity,
  station, source_file

callisto-<source-hash-prefix>.json
  category, organization, source URL/file/hash, artifact/hash,
  ingestion timestamp, original UTC time, shape, sample counts,
  physical ranges, units, preprocessing version and lineage
```

Import a local file or reproduce the included download:

```bash
.venv/bin/python -m backend.datasets.ingest callisto data/raw/recording.fit.gz \
  --source-url 'https://publisher.example/recording.fit.gz'
.venv/bin/python -m backend.datasets.fetch callisto
```

The example URL is a placeholder; use the actual source URL when importing your file.

### Causal calibration for scheduler replay

The recording is aggregated into uniform physical time/frequency bins. Empty bins remain missing. The first 8–24 regridded slots form a calibration prefix; that prefix is **excluded from the evaluated horizon**. Per-band median and MAD are computed from that prefix only. Later intensities are standardized with those frozen values before the receiver's energy response is applied.

The reference floor and threshold in this mode are standardized-intensity model parameters, not a conversion to calibrated RF power. No future recording samples are used in calibration. This is checked by a counterfactual preprocessing test.

The scheduler still sees only its chosen window. It can be evaluated for band coverage, missing-channel handling, confidence and observed energy-event behavior. **Pd, Pfa, labelled interception, truth-based reward and emitter timing remain N/A.**

## Controlled simulation

Ten presets cover sparse/dense spectra, sudden appearance, periodic activity, agility, high noise, changing behavior, multiple sources, unknown patterns and randomized stress cases. Advanced mode accepts bounded source JSON with activation/deactivation, frequency, duration, period, duty and relative SNR parameters.

All random draws use NumPy generators initialized from stored seeds. Truth, energy, detector draws and physical coordinates are read-only and fingerprinted. Worlds are regenerated by configuration, while saved trace playback reproduces the exact recorded events.

## Rebuilding the offline bundle

```bash
.venv/bin/python scripts/prepare_demo.py --benchmark
```

This computes new demo runs and the full 30-world benchmark, writes actual compressed traces, copies installed public artifacts, and generates a manifest. It does not invent an official-data subset if access is missing.

```bash
# Package existing benchmark traces without recomputing results
.venv/bin/python scripts/prepare_demo.py --bundle-existing

# Restore bundled measured data on a fresh machine, without internet
.venv/bin/python -m backend.datasets.bootstrap
```

On application startup, missing bundled runs and benchmark reports are restored into the local registry. Existing local data is retained. Artifact and trace hashes are checked on load/export. Preview matrices are downsampled for inspection; they must not be mistaken for the complete source or used as an evaluation shortcut.
