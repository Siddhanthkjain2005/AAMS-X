"""Channel -> region binning.

A scheduler in AAMS-X does not act on individual receiver channels; it acts on
``R`` abstract *sensing regions*.  This is the one abstraction the platform
imposes on the real data, and it exists for two concrete reasons.

1. A receiver retunes to a band, not to a single FFT bin, so a region is the
   honest unit of a sensing action.
2. Splicing two different stations into one scenario is only meaningful if both
   are expressed on a common action space.  Region ``i`` means "the i-th slice
   of whatever band this receiver currently covers", so a station change is a
   genuine, measured change in the joint activity pattern across the same set
   of actions.

Regions are built with equal *channel counts* rather than equal bandwidth: the
e-CALLISTO frequency axis is not perfectly linear, and equal-width bins would
leave some regions with no channels at all.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class RegionGrid:
    """An immutable mapping from a recording's channels onto ``n_regions`` regions."""

    n_regions: int
    channel_index: np.ndarray  # (C_sel,) indices into the source channel axis
    region_of_channel: np.ndarray  # (C_sel,) region id for each selected channel
    edges_mhz: np.ndarray  # (R + 1,) region boundaries, ascending
    centre_mhz: np.ndarray  # (R,) region centre frequency
    width_mhz: np.ndarray  # (R,) region bandwidth
    counts: np.ndarray  # (R,) channels per region
    starts: np.ndarray  # (R,) offset of each region inside ``channel_index``

    @property
    def n_channels(self) -> int:
        return int(self.channel_index.size)

    def to_dict(self) -> dict[str, object]:
        return {
            "n_regions": self.n_regions,
            "n_channels": self.n_channels,
            "edges_mhz": [round(float(v), 4) for v in self.edges_mhz],
            "centre_mhz": [round(float(v), 4) for v in self.centre_mhz],
            "width_mhz": [round(float(v), 4) for v in self.width_mhz],
            "counts": [int(v) for v in self.counts],
        }

    def region_label(self, region: int) -> str:
        """Human-readable name used throughout the UI, e.g. ``R07 · 118.4 MHz``."""
        return f"R{region:02d} · {self.centre_mhz[region]:.1f} MHz"


def build_grid(
    freq_mhz: np.ndarray,
    n_regions: int,
    *,
    freq_range_mhz: tuple[float, float] | None = None,
    drop_duplicate_freqs: bool = True,
) -> RegionGrid:
    """Partition a frequency axis into ``n_regions`` equal-channel-count regions.

    Every e-CALLISTO receiver pads its frequency table with ~8 channels pinned to
    the lower band edge.  Left in place they collapse the first region to zero
    bandwidth, so by default duplicate frequencies are reduced to their first
    occurrence — a documented preprocessing step, not a silent one.
    """
    if n_regions < 2:
        raise ValueError(f"n_regions must be at least 2, got {n_regions}")
    freq = np.asarray(freq_mhz, dtype=np.float64)
    selected = np.arange(freq.size)
    if freq_range_mhz is not None:
        low, high = float(freq_range_mhz[0]), float(freq_range_mhz[1])
        selected = selected[(freq >= low) & (freq <= high)]
        if selected.size < n_regions:
            raise ValueError(
                f"{freq_range_mhz[0]}-{freq_range_mhz[1]} MHz keeps only {selected.size} "
                f"channels, which cannot fill {n_regions} regions"
            )
    # CALLISTO publishes descending frequency; regions must read low -> high.
    order = selected[np.argsort(freq[selected], kind="stable")]
    if drop_duplicate_freqs:
        keep = np.concatenate(([True], np.diff(freq[order]) > 0.0))
        order = order[keep]
        if order.size < n_regions:
            raise ValueError(
                f"only {order.size} distinct frequencies available for {n_regions} regions"
            )
    groups = np.array_split(order, n_regions)

    region_of_channel = np.empty(order.size, dtype=np.int32)
    edges = np.empty(n_regions + 1, dtype=np.float64)
    centre = np.empty(n_regions, dtype=np.float64)
    counts = np.empty(n_regions, dtype=np.int32)

    cursor = 0
    for region, group in enumerate(groups):
        if group.size == 0:  # pragma: no cover - guarded by the check above
            raise ValueError(f"region {region} received no channels")
        region_of_channel[cursor : cursor + group.size] = region
        cursor += group.size
        band = freq[group]
        counts[region] = group.size
        centre[region] = float(band.mean())
        edges[region] = float(band.min())
    edges[-1] = float(freq[groups[-1]].max())
    # Snap interior edges to the midpoint between neighbouring group extremes so
    # the displayed bands tile the axis without gaps or overlaps.
    for region in range(1, n_regions):
        previous_max = float(freq[groups[region - 1]].max())
        current_min = float(freq[groups[region]].min())
        edges[region] = 0.5 * (previous_max + current_min)
    width = np.diff(edges)

    starts = np.concatenate(([0], np.cumsum(counts)[:-1])).astype(np.int64)
    return RegionGrid(
        n_regions=n_regions,
        channel_index=order.astype(np.int64),
        region_of_channel=region_of_channel,
        edges_mhz=edges,
        centre_mhz=centre,
        width_mhz=width,
        counts=counts,
        starts=starts,
    )


def region_margin_db(
    excess_db: np.ndarray, threshold_db: np.ndarray, grid: RegionGrid
) -> np.ndarray:
    """Aggregate channels into per-region *margin above the decision threshold*.

    Margin, not raw power, is the quantity the rest of AAMS-X works in.  Channel
    thresholds differ (each channel is compared against its own measured noise),
    so raw power cannot be pooled across channels without smuggling in a fake
    common threshold.  Margin can: a region is occupied exactly when at least one
    of its channels is, which is ``margin > 0``.
    """
    selected = excess_db[:, grid.channel_index] - threshold_db[grid.channel_index]
    # ``channel_index`` is ordered so each region occupies one contiguous span,
    # which lets a single reduceat replace a scatter-max over every channel.
    return np.maximum.reduceat(selected, grid.starts, axis=1).astype(np.float32)


def bin_time(values: np.ndarray, time_bin: int, *, reduce: str = "max") -> np.ndarray:
    """Aggregate consecutive samples into environment steps, dropping any remainder."""
    if time_bin <= 1:
        return values
    n_steps = values.shape[0] // time_bin
    if n_steps == 0:
        raise ValueError(f"cannot form a single step of {time_bin} samples from {values.shape[0]}")
    trimmed = values[: n_steps * time_bin]
    reshaped = trimmed.reshape(n_steps, time_bin, *values.shape[1:])
    if reduce == "max":
        return reshaped.max(axis=1)
    if reduce == "mean":
        return reshaped.mean(axis=1)
    if reduce == "any":
        return reshaped.any(axis=1)
    raise ValueError(f"unknown reduction {reduce!r}")
