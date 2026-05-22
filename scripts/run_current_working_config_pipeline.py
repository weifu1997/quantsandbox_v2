from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "data" / "reports"
DEFAULT_CONFIG_PATH = REPORTS_DIR / "current_working_strategy_config.json"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_tickers_file(config: dict[str, Any], reports_dir: Path = REPORTS_DIR) -> str | None:
    policy = str(config.get("working_universe_policy", "")).strip()
    if not policy:
        return None
    if policy == "amount_bottom_30pct":
        candidate = reports_dir / "filtered_universe_amount_bottom_30pct_latest.json"
        return str(candidate) if candidate.exists() else None
    if policy == "amount_bottom_20pct":
        candidate = reports_dir / "filtered_universe_amount_bottom_20pct_latest.json"
        return str(candidate) if candidate.exists() else None
    if policy == "growth_amount_bottom_20pct":
        candidate = reports_dir / "filtered_universe_growth_amount_bottom_20pct_latest.json"
        return str(candidate) if candidate.exists() else None
    if policy == "growth_amount_bottom_30pct":
        candidate = reports_dir / "filtered_universe_growth_amount_bottom_30pct_latest.json"
        return str(candidate) if candidate.exists() else None
    if policy == "growth_amount_bottom_40pct":
        candidate = reports_dir / "filtered_universe_growth_amount_bottom_40pct_latest.json"
        return str(candidate) if candidate.exists() else None
    if policy == "growth_amount_bottom_50pct":
        candidate = reports_dir / "filtered_universe_growth_amount_bottom_50pct_latest.json"
        return str(candidate) if candidate.exists() else None
    return None


def build_pipeline_steps(config_path: Path, reports_dir: Path = REPORTS_DIR) -> list[dict[str, Any]]:
    config = load_json(config_path)
    tickers_file = resolve_tickers_file(config, reports_dir)

    review_id_suffix = config.get("as_of") or "adhoc"
    review_id_suffix = str(review_id_suffix).replace("-", "")
    window_label = f"working_config_{review_id_suffix}"
    start_date = str(config.get("review_start_date", "20250701"))
    end_date = str(config.get("review_end_date", "20251231"))

    py = sys.executable
    steps: list[dict[str, Any]] = []

    def add(name: str, args: list[str]) -> None:
        steps.append({"name": name, "command": [py, *args]})

    growth_args = [
        "scripts/run_revgrowth_candidate_review.py",
        "--review-id", f"pipeline_growth_{review_id_suffix}",
        "--window-label", window_label,
        "--start-date", start_date,
        "--end-date", end_date,
        "--sample-name", "current_working_config",
    ]
    value_args = [
        "scripts/run_pbindlow_candidate_review.py",
        "--review-id", f"pipeline_value_{review_id_suffix}",
        "--window-label", window_label,
        "--start-date", start_date,
        "--end-date", end_date,
        "--sample-name", "current_working_config",
    ]
    if tickers_file:
        growth_args += ["--tickers-file", tickers_file]
        value_args += ["--tickers-file", tickers_file]

    add("growth_review", growth_args)
    add("value_review", value_args)

    realism_args = ["scripts/build_research_realism_stress.py", "--label", "base"]
    capacity_args = ["scripts/build_research_capacity_constraints.py", "--label", "base"]
    scale_stress_args = ["scripts/run_strategy_scale_stress_summary.py"]
    if tickers_file:
        realism_args += ["--tickers-file", tickers_file]
        capacity_args += ["--tickers-file", tickers_file]
        scale_stress_args += ["--tickers-file", tickers_file]

    add("realism", realism_args)
    add("capacity", capacity_args)
    add("scale_stress", scale_stress_args)
    add("decision_summary", ["scripts/build_research_decision_summary.py"])
    add("strategy_line_allocator", ["scripts/run_strategy_line_allocator.py"])
    add("sync_working_config", ["scripts/sync_current_working_config.py", "--config-path", str(config_path), "--summary-path", str(reports_dir / "research_decision_summary_latest.json")])
    return steps


def run_pipeline(steps: list[dict[str, Any]], workdir: Path = PROJECT_ROOT) -> list[dict[str, Any]]:
    executed = []
    for step in steps:
        proc = subprocess.run(step["command"], cwd=workdir, capture_output=True, text=True)
        record = {
            "name": step["name"],
            "command": step["command"],
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
        executed.append(record)
        if proc.returncode != 0:
            raise RuntimeError(json.dumps(record, ensure_ascii=False, indent=2))
    return executed


def build_result(config_path: Path, executed_steps: list[dict[str, Any]]) -> dict[str, Any]:
    summary_latest = REPORTS_DIR / "research_decision_summary_latest.json"
    return {
        "status": "ok",
        "config_path": str(config_path),
        "executed_steps": [
            {"name": x["name"], "returncode": x["returncode"]} for x in executed_steps
        ],
        "latest_summary": str(summary_latest),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the current working strategy pipeline")
    parser.add_argument("--config-path", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config_path = Path(args.config_path)
    steps = build_pipeline_steps(config_path)
    if args.dry_run:
        print(json.dumps({"status": "dry_run", "config_path": str(config_path), "steps": steps}, ensure_ascii=False, indent=2))
        return

    executed = run_pipeline(steps)
    print(json.dumps(build_result(config_path, executed), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
