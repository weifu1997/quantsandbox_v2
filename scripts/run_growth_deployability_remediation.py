from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "data" / "reports"
PY = sys.executable


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def run_step(name: str, args: list[str]) -> dict[str, Any]:
    proc = subprocess.run([PY, *args], cwd=PROJECT_ROOT, capture_output=True, text=True)
    record = {
        "name": name,
        "command": [PY, *args],
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
    if proc.returncode != 0:
        raise RuntimeError(json.dumps(record, ensure_ascii=False, indent=2))
    return record


def summary_growth_state(summary_path: Path) -> dict[str, Any]:
    summary = load_json(summary_path)
    deploy = ((summary.get("deployability") or {}).get("growth") or {})
    return {
        "deployment_blocked": deploy.get("deployment_blocked"),
        "recommended_max_aum": deploy.get("recommended_max_aum"),
        "working_config_recommendation": ((summary.get("working_config_recommendation") or {}).get("status")),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="One-shot growth deployability remediation")
    parser.add_argument("--max-rounds", type=int, default=3)
    args = parser.parse_args()

    attempts = []
    for round_no in range(1, args.max_rounds + 1):
        round_steps = []
        round_steps.append(run_step("apply_growth_remediation_round", ["scripts/apply_growth_remediation_round.py", "--round", str(round_no)]))
        round_steps.append(run_step("run_current_working_config_pipeline", ["scripts/run_current_working_config_pipeline.py"]))
        state = summary_growth_state(REPORTS_DIR / "research_decision_summary_latest.json")
        attempts.append({"round": round_no, "steps": round_steps, "growth_state": state})
        if state.get("deployment_blocked") is False and state.get("recommended_max_aum") is not None:
            out = {
                "status": "success",
                "successful_round": round_no,
                "attempts": attempts,
            }
            out_path = REPORTS_DIR / "growth_deployability_remediation_result_latest.json"
            out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return

    diagnostic = {
        "status": "paused_for_manual_intervention",
        "attempts": attempts,
        "diagnostic": "Growth remained deployment_blocked after 3 configured remediation rounds. Manual factor/universe redesign is required.",
    }
    out_path = REPORTS_DIR / "growth_deployability_remediation_result_latest.json"
    out_path.write_text(json.dumps(diagnostic, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(diagnostic, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
