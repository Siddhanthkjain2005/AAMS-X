"""System status and the scheduler catalogue."""

from __future__ import annotations

from fastapi import APIRouter

from aamsx.api.schemas import StatusResponse
from aamsx.config import get_settings
from aamsx.datasets.store import list_recordings
from aamsx.datasets.windows import index_path
from aamsx.environment.scenarios import list_presets
from aamsx.experiments.engine import get_engine
from aamsx.schedulers import ARENA_ORDER, deep_rl_available, describe_all
from aamsx.version import CODE_VERSION, SCHEDULER_VERSION

router = APIRouter(tags=["system"])


def _neural_available() -> bool:
    try:
        import torch  # noqa: F401
    except ImportError:
        return False
    return True


def _index_rows() -> int:
    path = index_path()
    if not path.exists():
        return 0
    import pyarrow.parquet as pq

    return int(pq.ParquetFile(path).metadata.num_rows)


@router.get("/status", response_model=StatusResponse)
def status() -> StatusResponse:
    """Everything the UI needs to render an honest header on first paint."""
    settings = get_settings()
    recordings = list_recordings(settings=settings)
    rows = _index_rows()
    presets = list_presets()
    warnings: list[str] = []
    if not recordings:
        warnings.append(
            "The offline cache is empty. Run scripts/fetch_real_data.py to download "
            "real e-CALLISTO recordings; nothing in AAMS-X is synthetic, so there is "
            "no fallback that would still be honest."
        )
    if rows == 0:
        warnings.append(
            "The window index is missing. Run scripts/build_index.py so scenarios can "
            "be selected by measured behaviour."
        )
    if len(presets) < 7:
        warnings.append(
            f"Only {len(presets)} of 7 presets can be built from the cached recordings."
        )
    cache_mb = (
        sum(path.stat().st_size for path in settings.cache_dir.rglob("*") if path.is_file()) / 1e6
        if settings.cache_dir.exists()
        else 0.0
    )
    ordered = {entry["name"]: entry for entry in describe_all()}
    schedulers = [ordered[name] for name in ARENA_ORDER if name in ordered]
    schedulers += [entry for name, entry in ordered.items() if name not in ARENA_ORDER]
    return StatusResponse(
        version=CODE_VERSION,
        scheduler_version=SCHEDULER_VERSION,
        data_mode="REAL PUBLIC SPECTRUM REPLAY (e-CALLISTO, cached)",
        network_allowed=settings.allow_network,
        recordings=len(recordings),
        windows_indexed=rows,
        presets=len(presets),
        schedulers=schedulers,
        neural_available=_neural_available(),
        deep_rl_available=deep_rl_available(),
        experiments=get_engine().registry.stats(),
        cache_mb=round(cache_mb, 1),
        warnings=warnings,
    )


@router.get("/schedulers")
def schedulers() -> dict[str, object]:
    """The policy catalogue, in Algorithm Arena display order."""
    ordered = {entry["name"]: entry for entry in describe_all()}
    arena = [ordered[name] for name in ARENA_ORDER if name in ordered]
    extra = [entry for name, entry in ordered.items() if name not in ARENA_ORDER]
    return {
        "arena_order": list(ARENA_ORDER),
        "schedulers": arena + extra,
        "deep_rl_available": deep_rl_available(),
    }
