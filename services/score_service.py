import numpy as np

def compute_volatility_score(daily_revenues: list) -> float:
    arr = np.array(daily_revenues)
    mean = np.mean(arr)

    if mean == 0:
        return 0.0

    coeff_variation = np.std(arr) / mean
    volatility_score = 1.0 - min(coeff_variation, 1.0)

    return round(volatility_score, 4)

def compute_trend_score(daily_revenues: list) -> float:
    weekly_avgs = []
    for i in range(0, len(daily_revenues), 7):
        week = daily_revenues[i:i + 7]
        if len(week) >= 3:
            weekly_avgs.append(np.mean(week))

    if len(weekly_avgs) < 2:
        return 0.5

    x = np.arange(len(weekly_avgs))
    slope, _ = np.polyfit(x, weekly_avgs, 1)

    avg_weekly = np.mean(weekly_avgs)
    if avg_weekly == 0:
        return 0.5

    normalised_slope = slope / avg_weekly
    trend_score = 0.5 + float(np.clip(normalised_slope, -0.5, 0.5))

    return round(trend_score, 4)

def compute_gross_margin_score(total_revenue: float, total_cogs: float) -> float:
    if total_revenue == 0:
        return 0.0

    gross_margin = 1.0 - (total_cogs / total_revenue)
    return round(max(0.0, min(1.0, gross_margin)), 4)

def compute_everiscore(
    trader_id: str,
    daily_revenues: list,
    total_revenue: float,
    total_cogs: float,
    total_expenses: float,
    consistency_ratio: float,
    days_tracked: int
) -> dict:

    if days_tracked < 30:
        return {
            "trader_id": trader_id,
            "eligible": False,
            "ineligible_reason": f"Need {30 - days_tracked} more days of records",
            "everiscore": None,
            "tier": "INELIGIBLE",
            "tax_status": None,
            "annualised_turnover": None,
            "signals": None
        }

    volatility_score = compute_volatility_score(daily_revenues)
    trend_score = compute_trend_score(daily_revenues)
    consistency_score = consistency_ratio
    gross_margin_score = compute_gross_margin_score(total_revenue, total_cogs)

    base_score = (
        volatility_score * 0.35 +
        trend_score * 0.25 +
        consistency_score * 0.20 +
        gross_margin_score * 0.20
    )

    annualised_turnover = np.mean(daily_revenues) * 365
    tax_status = (
        "NANO_EXEMPT" if annualised_turnover <= 12_000_000
        else "TAXABLE_1PCT"
    )

    tier = (
        "GREEN" if base_score >= 0.70
        else "YELLOW" if base_score >= 0.40
        else "RED"
    )

    return {
        "trader_id": trader_id,
        "everiscore": round(base_score, 3),
        "tier": tier,
        "tax_status": tax_status,
        "annualised_turnover": round(annualised_turnover, 2),
        "eligible": True,
        "ineligible_reason": None,
        "signals": {
            "volatility_score": volatility_score,
            "trend_score": trend_score,
            "consistency_score": round(consistency_score, 4),
            "gross_margin_score": gross_margin_score
        }
    }
