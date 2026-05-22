from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ImpactBucket:
    max_rate: float
    label: str
    impact_bps: float


DEFAULT_BUCKETS: tuple[ImpactBucket, ...] = (
    ImpactBucket(max_rate=0.005, label="very_light", impact_bps=0.0),
    ImpactBucket(max_rate=0.010, label="light", impact_bps=10.0),
    ImpactBucket(max_rate=0.020, label="medium", impact_bps=25.0),
    ImpactBucket(max_rate=0.030, label="heavy", impact_bps=50.0),
    ImpactBucket(max_rate=1.000, label="extreme", impact_bps=100.0),
)


@dataclass(frozen=True)
class ImpactEstimate:
    participation_rate: float
    bucket_label: str
    impact_bps: float


def estimate_dynamic_impact_bps(trade_notional: float, daily_amount: float) -> ImpactEstimate:
    notional = abs(float(trade_notional))
    amount = float(daily_amount)
    if notional <= 0:
        return ImpactEstimate(participation_rate=0.0, bucket_label="very_light", impact_bps=0.0)
    if amount <= 0:
        return ImpactEstimate(participation_rate=1.0, bucket_label="extreme", impact_bps=100.0)
    rate = notional / amount
    for bucket in DEFAULT_BUCKETS:
        if rate <= bucket.max_rate:
            return ImpactEstimate(participation_rate=rate, bucket_label=bucket.label, impact_bps=bucket.impact_bps)
    last = DEFAULT_BUCKETS[-1]
    return ImpactEstimate(participation_rate=rate, bucket_label=last.label, impact_bps=last.impact_bps)
