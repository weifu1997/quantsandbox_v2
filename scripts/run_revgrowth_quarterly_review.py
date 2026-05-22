from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REVIEW_SCRIPT = PROJECT_ROOT / 'scripts' / 'run_revgrowth_candidate_review.py'
STATUS_SCRIPT = PROJECT_ROOT / 'scripts' / 'build_revgrowth_candidate_pool_status.py'


def run_cmd(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description='Run growth-line candidate review and rebuild pool status in one command')
    parser.add_argument('--review-id', required=True)
    parser.add_argument('--window-label', required=True)
    parser.add_argument('--start-date', required=True)
    parser.add_argument('--end-date', required=True)
    parser.add_argument('--sample-name', default='expanded_main_board_1000')
    parser.add_argument('--sample-limit', type=int, default=1000)
    args = parser.parse_args()

    py = sys.executable
    run_cmd([
        py,
        str(REVIEW_SCRIPT),
        '--review-id', args.review_id,
        '--window-label', args.window_label,
        '--start-date', args.start_date,
        '--end-date', args.end_date,
        '--sample-name', args.sample_name,
        '--sample-limit', str(args.sample_limit),
    ])
    run_cmd([py, str(STATUS_SCRIPT)])
    print('growth-line candidate review + pool status refresh completed')


if __name__ == '__main__':
    main()
