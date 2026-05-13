import pytest
from services.score_service import (
    compute_volatility_score,
    compute_trend_score,
    compute_gross_margin_score,
    compute_everiscore
)

def test_compute_volatility_score_constant():
    # Mean is 100, std is 0 -> coeff is 0 -> score is 1.0
    assert compute_volatility_score([100, 100, 100, 100]) == 1.0

def test_compute_volatility_score_zero_mean():
    assert compute_volatility_score([0, 0, 0]) == 0.0

def test_compute_volatility_score_high_variance():
    # mean = 50, std = 50. coeff = 1.0 -> score = 0.0
    score = compute_volatility_score([0, 100])
    assert score == 0.0

def test_compute_trend_score_not_enough_data():
    # less than 2 weeks
    assert compute_trend_score([100] * 10) == 0.5

def test_compute_trend_score_increasing():
    # week 1 avg: 100, week 2 avg: 200, week 3 avg: 300
    daily_revenues = [100]*7 + [200]*7 + [300]*7
    score = compute_trend_score(daily_revenues)
    # The score should be > 0.5
    assert score > 0.5

def test_compute_gross_margin_score():
    assert compute_gross_margin_score(1000, 400) == 0.6
    assert compute_gross_margin_score(0, 100) == 0.0
    assert compute_gross_margin_score(100, 150) == 0.0 # negative margin clamped to 0

def test_compute_everiscore_ineligible():
    result = compute_everiscore(
        trader_id="T1",
        daily_revenues=[100]*29,
        total_revenue=2900,
        total_cogs=1000,
        total_expenses=500,
        consistency_ratio=0.8,
        days_tracked=29
    )
    assert not result["eligible"]
    assert result["tier"] == "INELIGIBLE"
    assert result["ineligible_reason"] == "Need 1 more days of records"

def test_compute_everiscore_eligible():
    result = compute_everiscore(
        trader_id="T2",
        daily_revenues=[100]*30,
        total_revenue=3000,
        total_cogs=1000,
        total_expenses=500,
        consistency_ratio=1.0,
        days_tracked=30
    )
    assert result["eligible"]
    assert result["tier"] in ["GREEN", "YELLOW", "RED"]
    assert result["everiscore"] is not None
    assert "volatility_score" in result["signals"]
