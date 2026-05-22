#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str], env: dict[str, str]) -> None:
    subprocess.run(cmd, cwd=PROJECT_ROOT, env=env, check=True)


def main() -> None:
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    end_date = env.get("END_DATE", "20260520")

    run([sys.executable, "scripts/build_filtered_universe_growth_amount_bottom.py"], env)
    filtered_latest = PROJECT_ROOT / "data/reports/filtered_universe_growth_amount_bottom_50pct_latest.json"
    if not filtered_latest.exists():
        raise SystemExit(f"missing filtered universe report: {filtered_latest}")

    env["TICKERS_FILE"] = str(filtered_latest)
    env["END_DATE"] = end_date
    run([sys.executable, "scripts/run_growth_personal_100k_2024_2026_boardlot_engine.py"], env)


if __name__ == "__main__":
    main()
