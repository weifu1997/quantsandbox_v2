from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "growth_deployability_remediation.json"


def load_growth_remediation_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    return json.loads(config_path.read_text(encoding="utf-8"))


def default_retry_round(config: dict[str, Any], round_no: int | None = None) -> dict[str, Any]:
    rounds = list(config.get("retry_rounds", []))
    if not rounds:
        raise ValueError("growth remediation config missing retry_rounds")
    if round_no is None:
        round_no = int(config.get("default_round", 1))
    for item in rounds:
        if int(item.get("round", 0)) == int(round_no):
            return dict(item)
    raise ValueError(f"retry round not found: {round_no}")
