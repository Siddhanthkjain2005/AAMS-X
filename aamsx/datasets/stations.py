"""Curated catalogue of e-CALLISTO recordings used by AAMS-X.

Nothing here is guessed.  ``scripts/survey_stations.py`` downloads real
observations from every station in the network and measures, per *(station,
focus-code)* pair, the achieved frequency span, the fraction of occupied
time-frequency cells under the AAMS-X labelling policy, and the number of
*live* channels — channels that are neither permanently silent nor permanently
saturated.  Live-channel count is the property that matters: a scheduling
problem is only interesting when regions genuinely differ from one another.

The focus code matters more than it looks.  One physical station publishes
several interleaved sweeps (``MRO`` publishes four), each covering a different
sub-band.  Mixing them would silently corrupt the frequency axis, so every
catalogue entry pins exactly one.

``role`` defines the leakage-free generalisation split: a scheduler tuned on
``train`` recordings is finally tested on ``unseen`` recordings that differ in
band, receiver hardware, continent and occupancy density.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

SplitRole = Literal["train", "validation", "unseen"]

CALLISTO_ARCHIVE = "http://soleil.i4ds.ch/solarradio/data/2002-20yy_Callisto"
CALLISTO_REFERENCE = (
    "Benz, Monstein & Meyer (2005), 'CALLISTO — A New Concept for Solar Radio "
    "Spectrometers', Solar Physics 226, 143; e-CALLISTO network, e-callisto.org"
)
CALLISTO_LICENSE = "Public scientific data — free use with attribution (e-callisto.org)"


@dataclass(frozen=True, slots=True)
class Station:
    """One e-CALLISTO instrument sweep, pinned to a single focus code."""

    name: str
    focus: str
    label: str
    country: str
    continent: str
    band: str
    freq_min_mhz: float
    freq_max_mhz: float
    n_channels: int
    cadence_sec: float
    role: SplitRole
    archetype: str
    measured_occupancy: float
    live_channels: int
    files_per_day: int
    notes: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def key(self) -> str:
        return f"{self.name}/{self.focus}"

    @property
    def bandwidth_mhz(self) -> float:
        return self.freq_max_mhz - self.freq_min_mhz

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "name": self.name,
            "focus": self.focus,
            "label": self.label,
            "country": self.country,
            "continent": self.continent,
            "band": self.band,
            "freq_min_mhz": self.freq_min_mhz,
            "freq_max_mhz": self.freq_max_mhz,
            "bandwidth_mhz": round(self.bandwidth_mhz, 2),
            "n_channels": self.n_channels,
            "cadence_sec": self.cadence_sec,
            "role": self.role,
            "archetype": self.archetype,
            "measured_occupancy": self.measured_occupancy,
            "live_channels": self.live_channels,
            "files_per_day": self.files_per_day,
            "notes": self.notes,
            "tags": list(self.tags),
        }


#: Recordings shipped in the offline cache, ordered by demonstration value.
STATIONS: tuple[Station, ...] = (
    Station(
        name="INDIA-GAURI",
        focus="02",
        label="Gauribidanur",
        country="India",
        continent="Asia",
        band="low VHF",
        freq_min_mhz=30.0,
        freq_max_mhz=89.9,
        n_channels=200,
        cadence_sec=0.25,
        role="train",
        archetype="dense-intermittent",
        measured_occupancy=0.0619,
        live_channels=134,
        files_per_day=96,
        notes="The only station publishing a full 24 h, so it is the source for "
        "long-horizon and diurnal experiments. Persistent carriers, intermittent "
        "utility traffic and quiet guard bands coexist in one recording.",
        tags=("vhf", "dense", "24h"),
    ),
    Station(
        name="SWISS-Landschlacht",
        focus="63",
        label="Landschlacht",
        country="Switzerland",
        continent="Europe",
        band="VHF incl. FM broadcast",
        freq_min_mhz=45.0,
        freq_max_mhz=174.6,
        n_channels=200,
        cadence_sec=0.25,
        role="train",
        archetype="mixed-persistent",
        measured_occupancy=0.0989,
        live_channels=82,
        files_per_day=55,
        notes="Dense European VHF: strong persistent broadcast carriers with "
        "intermittent activity between them — the clearest 'some regions are "
        "always worth watching, most are not' example.",
        tags=("vhf", "fm-broadcast", "europe"),
    ),
    Station(
        name="EGYPT-Alexandria",
        focus="01",
        label="Alexandria",
        country="Egypt",
        continent="Africa",
        band="VHF",
        freq_min_mhz=45.0,
        freq_max_mhz=164.9,
        n_channels=200,
        cadence_sec=0.25,
        role="validation",
        archetype="intermittent",
        measured_occupancy=0.1215,
        live_channels=160,
        files_per_day=57,
        notes="Same nominal band as the training stations but a different "
        "receiver, sky and interference population — a fair validation split "
        "for tuning without touching the unseen test set.",
        tags=("vhf", "africa"),
    ),
    Station(
        name="MRO",
        focus="60",
        label="Murchison Radio Observatory",
        country="Australia",
        continent="Oceania",
        band="VHF+UHF wideband",
        freq_min_mhz=50.0,
        freq_max_mhz=846.2,
        n_channels=200,
        cadence_sec=0.25,
        role="unseen",
        archetype="wideband-mixed",
        measured_occupancy=0.1116,
        live_channels=194,
        files_per_day=61,
        notes="A 796 MHz span inside a legally protected radio-quiet reserve, "
        "and still the densest live-channel count in the cache: wide, highly "
        "structured, dominated by a handful of strongly active regions.",
        tags=("uhf", "wideband", "radio-quiet"),
    ),
    Station(
        name="AUSTRIA-OE3FLB",
        focus="55",
        label="Litschau",
        country="Austria",
        continent="Europe",
        band="VHF+UHF wideband",
        freq_min_mhz=112.0,
        freq_max_mhz=747.2,
        n_channels=200,
        cadence_sec=0.25,
        role="unseen",
        archetype="sparse-bursty",
        measured_occupancy=0.0419,
        live_channels=57,
        files_per_day=54,
        notes="Sparsest recording in the cache: 4% occupancy spread across a "
        "635 MHz span with only 57 live channels. Uninformed scanning finds "
        "very little here, which is exactly the point.",
        tags=("uhf", "wideband", "sparse", "hard"),
    ),
    Station(
        name="SSRT",
        focus="59",
        label="Badary (SSRT)",
        country="Russia",
        continent="Asia",
        band="VHF+UHF",
        freq_min_mhz=45.1,
        freq_max_mhz=441.2,
        n_channels=200,
        cadence_sec=0.25,
        role="unseen",
        archetype="broad-lowcontrast",
        measured_occupancy=0.0369,
        live_channels=85,
        files_per_day=40,
        notes="Low-contrast site: many weakly active channels close to the "
        "decision boundary, which stresses uncertainty estimation rather than "
        "raw detection strength.",
        tags=("uhf", "low-contrast"),
    ),
    Station(
        name="SWISS-MUHEN",
        focus="62",
        label="Muhen",
        country="Switzerland",
        continent="Europe",
        band="HF/low VHF",
        freq_min_mhz=15.0,
        freq_max_mhz=86.9,
        n_channels=200,
        cadence_sec=0.25,
        role="unseen",
        archetype="hf-diurnal",
        measured_occupancy=0.0947,
        live_channels=167,
        files_per_day=53,
        notes="Reaches down into the HF band, where ionospheric propagation "
        "imposes slow diurnal structure on top of fast local activity — the "
        "cache's best source of genuine multi-scale periodicity.",
        tags=("hf", "diurnal", "periodic"),
    ),
)

STATIONS_BY_KEY: dict[str, Station] = {station.key: station for station in STATIONS}
STATIONS_BY_NAME: dict[str, Station] = {station.name: station for station in STATIONS}


def get_station(key: str) -> Station:
    """Look a station up by ``NAME/FOCUS`` key, or by bare name when unambiguous."""
    if key in STATIONS_BY_KEY:
        return STATIONS_BY_KEY[key]
    if key in STATIONS_BY_NAME:
        return STATIONS_BY_NAME[key]
    known = ", ".join(sorted(STATIONS_BY_KEY))
    raise KeyError(f"unknown station {key!r}; catalogued recordings are: {known}")


def stations_for_role(role: SplitRole) -> tuple[Station, ...]:
    return tuple(station for station in STATIONS if station.role == role)
