# `/score` Endpoint
## Why Rule-Based and Not ML

The EveriScore directly influences whether a human lender gives Mama Ngozi a
loan. Nigerian financial regulation expects credit scoring systems to be
explainable. If a loan officer asks "why did this trader score 0.63 instead
of 0.71?", you need a traceable answer: "because her revenue volatility
coefficient increased from 0.18 to 0.31, which reduced her volatility score
by 0.08."

A neural network or Random Forest cannot give that answer cleanly. The fraud
detection endpoint uses Isolation Forest because anomaly detection does not
need to explain itself — you just need to know something is wrong. The score
endpoint is different because it determines a trader's financial opportunities,
and that decision must be explainable to both the trader and the lender.

Rule-based NumPy scoring is the architecturally correct choice here, not a
compromise. It is deterministic, auditable, and regulator-friendly.

---

## Request Payload

```json
{
  "trader_id": "uuid-string",
  "daily_revenues": [45000, 48000, 52000, 43000, 47000, 50000, 44000],
  "total_revenue": 850000,
  "total_cogs": 420000,
  "total_expenses": 580000,
  "consistency_ratio": 0.78,
  "days_tracked": 34
}
```

`consistency_ratio` is computed on the Node.js side — unique upload days
divided by calendar span from first to last upload. A trader who uploaded on
21 of 34 days has a ratio of 0.618.

```javascript
async function buildScorePayload(traderId) {
  const [revenueRows, totals, uploadDates] = await Promise.all([
    db.query(`
      SELECT transaction_date, SUM(amount) as daily_total
      FROM transactions
      WHERE trader_id = $1 AND type = 'SALE'
      GROUP BY transaction_date
      ORDER BY transaction_date ASC
    `, [traderId]),
    db.query(`
      SELECT
        SUM(CASE WHEN type = 'SALE'              THEN amount ELSE 0 END) AS total_revenue,
        SUM(CASE WHEN category = 'COST_OF_GOODS' THEN amount ELSE 0 END) AS total_cogs,
        SUM(CASE WHEN type = 'EXPENSE'           THEN amount ELSE 0 END) AS total_expenses
      FROM transactions WHERE trader_id = $1
    `, [traderId]),
    db.query(`
      SELECT DISTINCT transaction_date FROM uploads
      WHERE trader_id = $1 ORDER BY transaction_date ASC
    `, [traderId])
  ]);

  const dates    = uploadDates.rows.map(r => new Date(r.transaction_date));
  // +1 because both first and last day count as part of the span.
  // Without it, a trader uploading every single day scores slightly above 1.0.
  const spanDays = Math.ceil(
    (dates[dates.length - 1] - dates[0]) / (1000 * 60 * 60 * 24)
  ) + 1;

  return {
    trader_id:         traderId,
    daily_revenues:    revenueRows.rows.map(r => parseFloat(r.daily_total)),
    total_revenue:     parseFloat(totals.rows[0].total_revenue  || 0),
    total_cogs:        parseFloat(totals.rows[0].total_cogs      || 0),
    total_expenses:    parseFloat(totals.rows[0].total_expenses  || 0),
    consistency_ratio: parseFloat((uploadDates.rows.length / spanDays).toFixed(4)),
    days_tracked:      spanDays
  };
}
```

---

## Response

```json
{
  "trader_id": "uuid-string",
  "everiscore": 0.673,
  "tier": "YELLOW",
  "tax_status": "NANO_EXEMPT",
  "annualised_turnover": 9125000,
  "eligible": true,
  "ineligible_reason": null,
  "signals": {
    "volatility_score": 0.71,
    "trend_score": 0.58,
    "consistency_score": 0.78,
    "gross_margin_score": 0.42
  }
}
```

`tier` is the **pre-fraud** tier. Always recompute from the final adjusted
score after applying the penalty multiplier. Never display this directly.

`eligible` is false when `days_tracked` is below 30. Skip `/fraud-check`
entirely and show the trader a progress indicator instead.

---

## The Four Signals

### Signal 1 — Revenue Volatility (35%)

Coefficient of variation — standard deviation divided by mean. Lower
volatility relative to the trader's own scale means higher score.

```python
def compute_volatility_score(daily_revenues: list) -> float:
    arr  = np.array(daily_revenues)
    mean = np.mean(arr)
    if mean == 0:
        return 0.0
    coeff_variation  = np.std(arr) / mean
    volatility_score = 1.0 - min(coeff_variation, 1.0)
    return round(volatility_score, 4)
```

### Signal 2 — Income Trend (25%)

Linear regression on weekly averages. Weekly averages smooth out day-of-week
effects — many traders do more business on market days.

```python
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
    return round(0.5 + float(np.clip(normalised_slope, -0.5, 0.5)), 4)
```

### Signal 3 — Consistency Score (20%)

The `consistency_ratio` passed in the request body. Used directly as the
signal score. No additional computation needed.

### Signal 4 — Gross Margin Score (20%)

How much revenue remains after paying for goods sold.

```python
def compute_gross_margin_score(total_revenue: float, total_cogs: float) -> float:
    if total_revenue == 0:
        return 0.0
    gross_margin = 1.0 - (total_cogs / total_revenue)
    return round(max(0.0, min(1.0, gross_margin)), 4)
```

---

## Complete Pipeline

```python
import numpy as np

def compute_everiscore(
    trader_id: str, daily_revenues: list,
    total_revenue: float, total_cogs: float,
    total_expenses: float, consistency_ratio: float,
    days_tracked: int
) -> dict:

    if days_tracked < 30:
        return {
            "trader_id": trader_id, "eligible": False,
            "ineligible_reason": f"Need {30 - days_tracked} more days of records",
            "everiscore": None, "tier": "INELIGIBLE", "tax_status": None
        }

    volatility_score   = compute_volatility_score(daily_revenues)
    trend_score        = compute_trend_score(daily_revenues)
    consistency_score  = consistency_ratio
    gross_margin_score = compute_gross_margin_score(total_revenue, total_cogs)

    base_score = (
        volatility_score   * 0.35 +
        trend_score        * 0.25 +
        consistency_score  * 0.20 +
        gross_margin_score * 0.20
    )

    annualised_turnover = np.mean(daily_revenues) * 365
    tax_status = "NANO_EXEMPT" if annualised_turnover <= 12_000_000 else "TAXABLE_1PCT"
    tier = "GREEN" if base_score >= 0.70 else "YELLOW" if base_score >= 0.40 else "RED"

    return {
        "trader_id": trader_id, "everiscore": round(base_score, 3),
        "tier": tier, "tax_status": tax_status,
        "annualised_turnover": round(annualised_turnover, 2),
        "eligible": True, "ineligible_reason": None,
        "signals": {
            "volatility_score": volatility_score,
            "trend_score": trend_score,
            "consistency_score": round(consistency_score, 4),
            "gross_margin_score": gross_margin_score
        }
    }
```
