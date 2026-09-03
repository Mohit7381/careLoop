"""
Shared journey-config loader (contracts v3, Appendix A #2/#7): a journey is
config, not code. `config/journeys/{journey}.yaml` is the single source of
truth for stages, routing categories -> repos, the drill-down whitelist,
and the VoC lexicon. Both the Analyst and Code Scout read it from here.
"""
from functools import lru_cache
from pathlib import Path

import yaml

JOURNEYS_DIR = Path("config/journeys")


@lru_cache
def load_journey(journey: str) -> dict:
    return yaml.safe_load((JOURNEYS_DIR / f"{journey}.yaml").read_text())
