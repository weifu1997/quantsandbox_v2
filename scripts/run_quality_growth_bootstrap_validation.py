from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.dataset_service import build_research_dataset
from app.domain.factors.registry import build_default_factor_registry
from app.adapters.fundamental_data_adapter import InMemoryFundamentalDataAdapter
from app.adapters.market_data_adapter import InMemoryMarketDataAdapter

OUT = Path('data/reports/quality_growth_bootstrap_validation_20260517.json')


def main() -> None:
    tickers = ['sh600519', 'sz000858', 'sh600036', 'sz000001', 'sh600000']
    factors = ['roe', 'roa', 'gross_margin', 'revenue_growth', 'profit_growth']
    dataset, summary, _ = build_research_dataset(
        tickers=tickers,
        start_date='20240101',
        end_date='20241231',
        factor_names=factors,
        horizons=[20],
        experiment_id=None,
        market_adapter=InMemoryMarketDataAdapter(),
        fundamental_adapter=InMemoryFundamentalDataAdapter(),
    )
    registry = build_default_factor_registry()
    out = {
        'tickers': tickers,
        'factors': factors,
        'registry_factor_names': sorted(registry.list_names()),
        'dataset_columns': sorted(dataset.columns.tolist()),
        'dataset_summary': summary,
        'head_sample': dataset[[c for c in dataset.columns if c.startswith('factor:')][:5]].head(5).to_dict(orient='records'),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print(OUT)


if __name__ == '__main__':
    main()
