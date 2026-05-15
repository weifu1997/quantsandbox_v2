from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.domain.models import ExperimentConfig
from app.services.experiment_service import submit_experiment
from app.services.report_service import get_report, resolve_report_content
from app.services.task_service import get_task


def main() -> None:
    parser = argparse.ArgumentParser(description="Submit a minimal QuantSandbox v2 experiment")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--factors", nargs="*", default=[])
    parser.add_argument("--tickers", nargs="*", default=[])
    parser.add_argument("--universe", default=None)
    parser.add_argument("--wait", action="store_true", help="wait until background task completes")
    parser.add_argument("--poll-seconds", type=float, default=0.2)
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    args = parser.parse_args()

    result = submit_experiment(
        ExperimentConfig(
            start_date=args.start_date,
            end_date=args.end_date,
            factors=args.factors,
            tickers=args.tickers,
            universe=args.universe,
        )
    )

    output = {
        "experiment": result["experiment"],
        "task": result["task"],
    }

    if args.wait:
        task_id = result["task"]["task_id"]
        deadline = time.time() + args.timeout_seconds
        while time.time() < deadline:
            task = get_task(task_id)
            if task and task["status"] in {"completed", "failed", "interrupted"}:
                output["task"] = task
                if task.get("result_ref"):
                    report = get_report(task["result_ref"])
                    if report:
                        output["report"] = report
                        output["report_content"] = resolve_report_content(report)
                break
            time.sleep(args.poll_seconds)

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
