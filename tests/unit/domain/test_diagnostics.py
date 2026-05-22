from app.domain.research.diagnostics import diagnose_factor


def test_diagnose_factor_promising_case() -> None:
    result = diagnose_factor(
        'factor:momentum_20d',
        {
            'ic_mean': 0.06,
            'rank_ic_mean': 0.05,
            'sample_count': 24,
            'positive_ic_ratio': 0.75,
        },
        {
            'group_returns': {'Q1': -0.01, 'Q2': 0.0, 'Q3': 0.01, 'Q4': 0.02, 'Q5': 0.03},
            'monotonicity_score': 1.0,
        },
    )
    assert result['verdict'] == 'promising'
    assert 'ic_mean_is_material' in result['strengths']
    assert result['summary']['top_bottom_spread'] > 0


def test_diagnose_factor_weak_case() -> None:
    result = diagnose_factor(
        'factor:pe',
        {
            'ic_mean': 0.0,
            'rank_ic_mean': 0.01,
            'sample_count': 4,
            'positive_ic_ratio': 0.25,
        },
        {
            'group_returns': {'Q1': 0.02, 'Q2': 0.01, 'Q3': 0.0, 'Q4': -0.01, 'Q5': -0.02},
            'monotonicity_score': 0.0,
        },
    )
    assert result['verdict'] == 'weak'
    assert 'sample_count_is_small' in result['warnings']
    assert 'top_group_does_not_outperform_bottom_group' in result['warnings']
