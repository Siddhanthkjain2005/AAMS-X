"""Multi-seed statistics.

A single episode proves nothing: real recordings differ, the receiver adds noise,
and Thompson sampling is stochastic.  Every headline number in AAMS-X is therefore
an average over seeds, reported with a 95% confidence interval, and comparisons
come with a significance test.

Two tests are provided because they answer different questions and disagree in
useful ways.  Welch's t-test compares means without assuming equal variances,
which is the right default for reward-like quantities.  Mann-Whitney U compares
distributions without assuming normality, which matters for delay metrics that are
heavily skewed by the events nobody caught.  Both are reported; a difference is
called significant only when both agree at :data:`ALPHA`, which is the rule stated
in ``docs/EXPERIMENTS.md`` §1 and the reason several visually large differences in
that document are marked *not significant*.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats

#: Significance level for both tests.  With six seeds per arm the smallest
#: two-sided Mann-Whitney p is 0.0022, so the rank test can support a call at this
#: level — but only just, which is why the conjunction is not a formality.
ALPHA = 0.05


@dataclass(frozen=True, slots=True)
class Aggregate:
    """Mean, spread and 95% CI of one metric across seeds."""

    metric: str
    n: int
    mean: float
    std: float
    sem: float
    ci_low: float
    ci_high: float
    minimum: float
    maximum: float
    median: float
    values: tuple[float, ...]

    def to_dict(self, *, include_values: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "metric": self.metric,
            "n": self.n,
            "mean": _round(self.mean),
            "std": _round(self.std),
            "sem": _round(self.sem),
            "ci_low": _round(self.ci_low),
            "ci_high": _round(self.ci_high),
            "min": _round(self.minimum),
            "max": _round(self.maximum),
            "median": _round(self.median),
        }
        if include_values:
            payload["values"] = [_round(v) for v in self.values]
        return payload


def _round(value: float) -> float:
    number = float(value)
    return number if not np.isfinite(number) else round(number, 6)


def aggregate(metric: str, values: list[float] | np.ndarray) -> Aggregate:
    """Summarise repeated measurements of one metric.

    The confidence interval uses the Student-t critical value, which matters at
    the seed counts a laptop demo can afford: with 5 seeds the normal
    approximation understates the interval by roughly 30%.
    """
    array = np.asarray([v for v in np.asarray(values, dtype=np.float64) if np.isfinite(v)])
    if array.size == 0:
        nan = float("nan")
        return Aggregate(metric, 0, nan, nan, nan, nan, nan, nan, nan, nan, ())
    mean = float(array.mean())
    if array.size == 1:
        return Aggregate(metric, 1, mean, 0.0, 0.0, mean, mean, mean, mean, mean, (mean,))
    std = float(array.std(ddof=1))
    sem = std / np.sqrt(array.size)
    half = float(stats.t.ppf(0.975, array.size - 1) * sem)
    return Aggregate(
        metric=metric,
        n=int(array.size),
        mean=mean,
        std=std,
        sem=float(sem),
        ci_low=mean - half,
        ci_high=mean + half,
        minimum=float(array.min()),
        maximum=float(array.max()),
        median=float(np.median(array)),
        values=tuple(float(v) for v in array),
    )


@dataclass(frozen=True, slots=True)
class Comparison:
    """Result of comparing one metric between two policies."""

    metric: str
    treatment: str
    control: str
    difference: float
    relative: float
    welch_t: float
    welch_p: float
    mannwhitney_u: float
    mannwhitney_p: float
    cohens_d: float
    n_treatment: int
    n_control: int

    @property
    def significant(self) -> bool:
        """True only when Welch *and* Mann-Whitney both reject at :data:`ALPHA`.

        Welch alone would flag differences the rank test does not support; at six
        seeds per arm that happens often enough to matter, so the conjunction is
        what the reports and the arena table publish.
        """
        return bool(
            np.isfinite(self.welch_p)
            and self.welch_p < ALPHA
            and np.isfinite(self.mannwhitney_p)
            and self.mannwhitney_p < ALPHA
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "metric": self.metric,
            "treatment": self.treatment,
            "control": self.control,
            "difference": _round(self.difference),
            "relative": _round(self.relative),
            "welch_t": _round(self.welch_t),
            "welch_p": _round(self.welch_p),
            "mannwhitney_u": _round(self.mannwhitney_u),
            "mannwhitney_p": _round(self.mannwhitney_p),
            "cohens_d": _round(self.cohens_d),
            "significant": self.significant,
            "n_treatment": self.n_treatment,
            "n_control": self.n_control,
        }


def compare(
    metric: str,
    treatment: list[float] | np.ndarray,
    control: list[float] | np.ndarray,
    *,
    treatment_name: str = "treatment",
    control_name: str = "control",
) -> Comparison:
    """Compare two samples of the same metric with both tests."""
    a = np.asarray([v for v in np.asarray(treatment, dtype=np.float64) if np.isfinite(v)])
    b = np.asarray([v for v in np.asarray(control, dtype=np.float64) if np.isfinite(v)])
    nan = float("nan")
    if a.size < 2 or b.size < 2:
        return Comparison(
            metric, treatment_name, control_name, nan, nan, nan, nan, nan, nan, nan, a.size, b.size
        )

    difference = float(a.mean() - b.mean())
    denominator = abs(float(b.mean()))
    relative = difference / denominator if denominator > 1e-12 else nan
    welch = stats.ttest_ind(a, b, equal_var=False)
    try:
        mann = stats.mannwhitneyu(a, b, alternative="two-sided")
        mann_u, mann_p = float(mann.statistic), float(mann.pvalue)
    except ValueError:  # identical samples
        mann_u, mann_p = nan, 1.0
    pooled = np.sqrt(
        ((a.size - 1) * a.var(ddof=1) + (b.size - 1) * b.var(ddof=1)) / (a.size + b.size - 2)
    )
    cohens_d = difference / float(pooled) if pooled > 1e-12 else nan
    return Comparison(
        metric=metric,
        treatment=treatment_name,
        control=control_name,
        difference=difference,
        relative=relative,
        welch_t=float(welch.statistic),
        welch_p=float(welch.pvalue),
        mannwhitney_u=mann_u,
        mannwhitney_p=mann_p,
        cohens_d=cohens_d,
        n_treatment=int(a.size),
        n_control=int(b.size),
    )


HEADLINE_METRICS: tuple[str, ...] = (
    "cumulative_reward",
    "cumulative_regret",
    "sustained_detection_probability",
    "event_detection_probability",
    "sustained_detection_delay",
    "time_to_detect_capped",
    "detection_rate",
    "false_alarm_rate",
    "detections_per_cost",
    "information_per_observation",
    "oracle_ratio",
    "band_coverage",
    "sensing_cost",
)


def summarise_runs(
    runs: list[dict[str, object]], *, metrics: tuple[str, ...] = HEADLINE_METRICS
) -> dict[str, dict[str, object]]:
    """Aggregate a list of episode metric dicts, one entry per requested metric."""
    out: dict[str, dict[str, object]] = {}
    for metric in metrics:
        values = [
            float(run[metric])  # type: ignore[arg-type]
            for run in runs
            if metric in run and run[metric] is not None
        ]
        out[metric] = aggregate(metric, values).to_dict()
    return out
