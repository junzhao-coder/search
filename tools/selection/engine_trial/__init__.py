"""V18 single-thread engine trial: local fixture, Playwright primary, nodriver backup."""

from __future__ import annotations

from .collector import TrialConfig, run_trial
from .engines import (EngineUnavailable, NodriverDriver, PlaywrightDriver,
                      availability, nodriver_available, playwright_available)
from .extract import EXTRACT_JS, compare_ids, field_summary, ids_of, normalize
from .fixture import build_fixture, ground_truth

__all__ = [
    "EXTRACT_JS", "EngineUnavailable", "NodriverDriver", "PlaywrightDriver",
    "TrialConfig", "availability", "build_fixture", "compare_ids", "field_summary",
    "ground_truth", "ids_of", "nodriver_available", "normalize",
    "playwright_available", "run_trial",
]
