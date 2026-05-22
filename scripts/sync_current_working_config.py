from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def sync_config(config_path: Path, summary_path: Path) -> dict[str, Any]:
    config = load_json(config_path)
    summary = load_json(summary_path)
    wc = summary.get("working_configuration") or {}
    wcr = summary.get("working_config_recommendation") or {}
    source_artifacts = summary.get("source_artifacts") or {}
    deployability = summary.get("deployability") or {}

    config["keep_rule_status"] = wcr.get("status", config.get("keep_rule_status"))
    config["decision_basis"] = "data/reports/research_decision_summary_latest.json"
    if source_artifacts.get("realism_report"):
        config["realism_basis"] = "data/reports/research_realism_stress_latest.json"
    if source_artifacts.get("capacity_report"):
        config["capacity_basis"] = "data/reports/research_capacity_constraints_latest.json"
    if source_artifacts.get("scale_stress_report"):
        config["scale_stress_basis"] = "data/reports/strategy_scale_stress_summary_latest.json"
    if deployability:
        config["deployability"] = deployability
    wc_review = (wc.get("working_config_review") or {})
    if wc_review.get("status"):
        config["keep_rule_status"] = wc_review.get("status")
    if wc_review.get("status") in {"needs_revision", "stop_using"}:
        config["operating_mode"] = f"governance_{wc_review.get('status')}"
    elif wcr.get("status") in {"needs_revision", "stop_using"}:
        config["operating_mode"] = f"governance_{wcr.get('status')}"
    notes = list(config.get("notes", []))
    sync_note = f"governance_synced_from={summary_path.name}"
    if sync_note not in notes:
        notes.append(sync_note)
    config["notes"] = notes
    write_json(config_path, config)
    return {
        "status": "ok",
        "config_path": str(config_path),
        "summary_path": str(summary_path),
        "keep_rule_status": config.get("keep_rule_status"),
        "operating_mode": config.get("operating_mode"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync current working config from decision summary")
    parser.add_argument("--config-path", required=True)
    parser.add_argument("--summary-path", required=True)
    args = parser.parse_args()
    result = sync_config(Path(args.config_path), Path(args.summary_path))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
