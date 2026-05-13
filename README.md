# EveriKobo ML Microservice — README

## What This Service Is

EveriKobo has two backend services that talk to each other over HTTP. The
main Node.js backend handles the mobile app, PostgreSQL, and
Squad API. This Python FastAPI microservice handles all AI
and ML work. The separation is intentional — it means the ML components can be
updated, retrained, and deployed independently without risking the stability of
the main application.

```
React Native App
      |
      v
Node.js Backend ──────> Python ML Microservice
      |                                    |
      |                            POST /extract
      |                            POST /score
      |                            POST /fraud-check
      v
PostgreSQL (Neon)
Squad API
```

The Node.js backend is the orchestrator. It calls this microservice when it needs AI
intelligence, uses the results to make product decisions, and stores the
outcomes in PostgreSQL. It does not need to understand the internals of any
endpoint — it only needs to know what to send and what to do with what comes
back.

---

## Setup

```bash
# Clone and install
pip install fastapi uvicorn numpy scikit-learn river python-dotenv

# Environment variables
cp .env.example .env

# Run locally
uvicorn main:app --reload --port 8000
```

```bash
# .env.example
GEMINI_API_KEY=your_gemini_api_key_here
PORT=8000
```

The Node.js backend needs one environment variable on his Node.js side:

```bash
# In the Node.js .env
ML_SERVICE_URL=http://localhost:8000          # Local development
ML_SERVICE_URL=https://your-app.railway.app  # Production
```

---

## The Three Endpoints at a Glance

The table below gives a quick orientation before reading the detailed
sections. The key column is "Client Action" — that is the only part
the client needs to act on.

| Endpoint | What It Does | Client Action |
|---|---|---|
| `POST /extract` | Reads a ledger photo with Gemini Vision, returns structured JSON | Saves the returned transactions to PostgreSQL |
| `POST /score` | Computes EveriScore from transaction history using NumPy | Multiplies the returned `everiscore` by the fraud penalty to get the final score |
| `POST /fraud-check` | Runs ML anomaly detection on transaction patterns | Takes the returned `penalty_multiplier` and applies it to the base score |

---

## How It All Comes Together

This is an important section to read because it shows how the
three endpoints connect into a single scoring flow. The key engineering insight
is that `/score` and `/fraud-check` run **in parallel** using `Promise.all`
because they use different data and neither depends on the other's result. This
cuts the total response time roughly in half compared to calling them one after
the other.

```javascript
// This is the main function the Node.js backend calls when the trader
// taps "Check My Score" in the mobile app.
// It orchestrates both ML endpoints and returns the final result.
async function computeFinalEveriScore(traderId) {

  // Build the payloads for both endpoints before making any calls.
  // We do this first so both HTTP calls can fire simultaneously.
  const [scorePayload, fraudPayload] = await Promise.all([
    buildScorePayload(traderId),
    buildFraudCheckPayload(traderId)
  ]);

  // Check eligibility before calling the ML service at all.
  // A trader with fewer than 30 days of records cannot be scored —
  // calling the service would just return INELIGIBLE anyway, so we
  // skip the network call entirely and return early.
  if (scorePayload.days_tracked < 30) {
    const daysNeeded = 30 - scorePayload.days_tracked;
    return {
      eligible: false,
      ineligible_reason: `Upload ${daysNeeded} more days of records to unlock your EveriScore`,
      tier: 'INELIGIBLE'
    };
  }

  // Fire both calls simultaneously. Neither depends on the other,
  // so there is no reason to wait for one before starting the other.
  const [scoreResult, fraudResult] = await Promise.all([
    callScoreEndpoint(scorePayload),
    callFraudCheckEndpoint(fraudPayload)
  ]);

  // Apply the fraud penalty to the base score.
  // If no fraud was detected, penalty_multiplier is 1.0 and nothing changes.
  // If fraud was detected, the multiplier is below 1.0 and the score drops.
  const finalScore = scoreResult.everiscore * fraudResult.penalty_multiplier;

  // IMPORTANT: Always recompute the tier from the FINAL adjusted score,
  // never from scoreResult.tier. The fraud penalty may have pushed the score
  // into a different tier — for example, a GREEN score of 0.71 with a 0.50
  // penalty becomes 0.355, which is RED, not GREEN.
  const finalTier = finalScore >= 0.70 ? 'GREEN'
                  : finalScore >= 0.40 ? 'YELLOW'
                  : 'RED';

  // Store the final score in PostgreSQL so it persists across sessions
  await db.query(`
    INSERT INTO everiscores
      (trader_id, score, tier, tax_status, fraud_flag_count, squad_action)
    VALUES ($1, $2, $3, $4, $5, $6)
  `, [
    traderId,
    finalScore,
    finalTier,
    scoreResult.tax_status,
    fraudResult.flag_count,
    finalTier === 'GREEN' ? 'generate_squad_payment_link_loan_referral'
    : finalTier === 'YELLOW' ? 'prompt_savings_behaviour'
    : 'coaching_mode_only'
  ]);

  return {
    trader_id:           traderId,
    base_score:          scoreResult.everiscore,
    penalty_multiplier:  fraudResult.penalty_multiplier,
    final_score:         parseFloat(finalScore.toFixed(3)),
    tier:                finalTier,
    tax_status:          scoreResult.tax_status,
    annualised_turnover: scoreResult.annualised_turnover,
    signals:             scoreResult.signals,
    fraud_flags:         fraudResult.fraud_flags,
    flag_count:          fraudResult.flag_count
  };
}
```

---

## Error Handling Philosophy

Neither endpoint should ever block the trader from getting a response. If this
microservice is temporarily unavailable — because Railway had a cold start, a
network hiccup, or a crash — the Node.js backend should fall back to safe
defaults rather than showing the trader an error screen.

```javascript
// Safe wrapper for the score endpoint
async function callScoreEndpoint(payload) {
  try {
    const response = await fetch(`${process.env.ML_SERVICE_URL}/score`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(payload)
    });
    if (!response.ok) throw new Error(`Score service: ${response.status}`);
    return response.json();
  } catch (error) {
    // Log the error for debugging but do not surface it to the trader
    console.error('Score service unavailable:', error.message);
    // Return a neutral result that lets the flow continue without a score
    return { everiscore: null, tier: 'UNAVAILABLE', eligible: false,
             ineligible_reason: 'Scoring service temporarily unavailable' };
  }
}

// Safe wrapper for the fraud check endpoint
async function callFraudCheckEndpoint(payload) {
  try {
    const response = await fetch(`${process.env.ML_SERVICE_URL}/fraud-check`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(payload)
    });
    if (!response.ok) throw new Error(`Fraud check service: ${response.status}`);
    return response.json();
  } catch (error) {
    console.error('Fraud check service unavailable:', error.message);
    // Default to no penalty rather than blocking the scoring flow.
    // It is better to occasionally miss a fraud flag than to always
    // block legitimate traders from getting their score.
    return { penalty_multiplier: 1.0, flag_count: 0, fraud_flags: [] };
  }
}
```

---

---

# `/score` Endpoint

## Why Rule-Based and Not ML

Before anything else, it is worth understanding why this endpoint deliberately
avoids machine learning despite the rest of the microservice using it.

The EveriScore directly influences whether a human lender gives Mama Ngozi a
loan. In Nigerian financial regulation, credit scoring systems that inform
lending decisions are expected to be explainable. If a loan officer asks "why
did this trader score 0.63 instead of 0.71?", you need a traceable answer:
"because her revenue volatility coefficient increased from 0.18 to 0.31 over
the last two weeks, which reduced her volatility score by 0.08."

A neural network or Random Forest cannot give that answer cleanly. The fraud
detection endpoint uses Isolation Forest because anomaly detection does not
need to explain itself — you just need to know something is wrong. The score
endpoint is different because it determines a trader's financial opportunities,
and that decision must be explainable to both the trader and the lender.

Rule-based NumPy scoring is therefore the architecturally correct choice here,
not a compromise. It is deterministic, auditable, and regulator-friendly.

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

`daily_revenues` is a chronologically ordered array of total daily sales
revenue. The client builds it with a GROUP BY query on the transactions table,
ordered oldest to newest, because the trend signal depends on the direction
of change over time.

`total_cogs` is the sum of Cost of Goods expenses only — wholesale inventory
purchases, not overhead. The client filters WHERE category = 'COST_OF_GOODS'.

`total_expenses` is the sum of ALL expenses including both COGS and overhead.
This is obtained with a broader SUM() across all expense records.

`consistency_ratio` is computed on the Node.js side before the call,
because it requires date arithmetic on the upload history that the Node.js backend already
has in memory. The formula is: unique upload days ÷ calendar span from first
to last upload. A trader who uploaded on 21 out of 34 calendar days has a
consistency ratio of 0.618.

Here is exactly how it is computed:

```javascript
async function buildScorePayload(traderId) {

  // Three parallel queries to build the payload efficiently
  const [revenueRows, totals, uploadDates] = await Promise.all([

    // Daily revenues grouped by date, oldest first
    db.query(`
      SELECT transaction_date, SUM(amount) as daily_total
      FROM transactions
      WHERE trader_id = $1 AND type = 'SALE'
      GROUP BY transaction_date
      ORDER BY transaction_date ASC
    `, [traderId]),

    // Aggregate totals across the full period
    db.query(`
      SELECT
        SUM(CASE WHEN type = 'SALE'             THEN amount ELSE 0 END) AS total_revenue,
        SUM(CASE WHEN category = 'COST_OF_GOODS' THEN amount ELSE 0 END) AS total_cogs,
        SUM(CASE WHEN type = 'EXPENSE'           THEN amount ELSE 0 END) AS total_expenses
      FROM transactions
      WHERE trader_id = $1
    `, [traderId]),

    // Distinct upload dates for consistency calculation
    db.query(`
      SELECT DISTINCT transaction_date
      FROM uploads
      WHERE trader_id = $1
      ORDER BY transaction_date ASC
    `, [traderId])
  ]);

  // Compute the calendar span from first to last upload.
  // We add 1 because both the first and last day count as part of the span.
  // Example: April 1 to April 30 subtracts to 29 days, but spans 30 calendar
  // days. Without +1, a trader uploading every single day would score slightly
  // above 1.0, which is nonsensical.
  const dates    = uploadDates.rows.map(r => new Date(r.transaction_date));
  const spanDays = Math.ceil(
    (dates[dates.length - 1] - dates[0]) / (1000 * 60 * 60 * 24)
  ) + 1;

  const consistencyRatio = uploadDates.rows.length / spanDays;

  return {
    trader_id:         traderId,
    daily_revenues:    revenueRows.rows.map(r => parseFloat(r.daily_total)),
    total_revenue:     parseFloat(totals.rows[0].total_revenue  || 0),
    total_cogs:        parseFloat(totals.rows[0].total_cogs      || 0),
    total_expenses:    parseFloat(totals.rows[0].total_expenses  || 0),
    consistency_ratio: parseFloat(consistencyRatio.toFixed(4)),
    days_tracked:      spanDays
  };
}
```

**On the size of daily_revenues:** The payload includes one number per upload day.
At 30 days that is 30 numbers. At 365 days that is 365 numbers. Each number
is 8 bytes as a float, so a full year of history is under 3 kilobytes — well
within the comfortable limit of any HTTP request. This is never a performance
concern at realistic scale.

---

## What the Endpoint Returns

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

`everiscore` is the base score **before** the fraud penalty. The Node.js backend multiplies
this by `penalty_multiplier` from `/fraud-check` to get the final score.

`tier` is the **pre-fraud** tier. The client must recompute the tier after applying
the penalty — never display this value directly in the UI.

`tax_status` controls what the app shows the trader: a "Tax Exempt" badge for
`NANO_EXEMPT`, or a prompt to generate a tax report for `TAXABLE_1PCT`.

`signals` exposes the four individual scores so the mobile app can show the
trader a breakdown of what drove their EveriScore, helping them understand
what behaviour to improve.

`eligible` is false when `days_tracked` is below 30. The client should skip the
`/fraud-check` call entirely when this is false and show the trader a progress
indicator instead.

---

## The Four Signals

### Signal 1 — Revenue Volatility (35% weight)

Volatility measures how consistent the trader's daily revenue is. The tool is
the coefficient of variation — standard deviation divided by mean. This
normalises the measurement so it is comparable across traders of different
sizes: a large trader with ₦500,000 average daily revenue and ₦50,000 standard
deviation is equally consistent as a small trader with ₦50,000 average and
₦5,000 standard deviation.

```python
def compute_volatility_score(daily_revenues: list) -> float:
    arr  = np.array(daily_revenues)
    mean = np.mean(arr)

    if mean == 0:
        return 0.0

    coeff_variation  = np.std(arr) / mean
    # 1 minus CoV: lower volatility = higher score, capped at 1.0
    volatility_score = 1.0 - min(coeff_variation, 1.0)

    return round(volatility_score, 4)
```

### Signal 2 — Income Trend (25% weight)

Trend captures whether the business is growing, stable, or declining. We use
linear regression on weekly averages rather than daily figures to smooth out
day-of-week effects — many traders do more business on market days, and we
do not want Monday-heavy weeks to look artificially better than other weeks.

```python
def compute_trend_score(daily_revenues: list) -> float:
    weekly_avgs = []
    for i in range(0, len(daily_revenues), 7):
        week = daily_revenues[i:i + 7]
        if len(week) >= 3:
            weekly_avgs.append(np.mean(week))

    if len(weekly_avgs) < 2:
        return 0.5  # Not enough weeks — return neutral score

    x = np.arange(len(weekly_avgs))
    slope, _ = np.polyfit(x, weekly_avgs, 1)

    avg_weekly = np.mean(weekly_avgs)
    if avg_weekly == 0:
        return 0.5

    # Normalise slope relative to average revenue so large and small
    # traders are treated equally, then map to 0-1 range around 0.5
    normalised_slope = slope / avg_weekly
    trend_score      = 0.5 + float(np.clip(normalised_slope, -0.5, 0.5))

    return round(trend_score, 4)
```

### Signal 3 — Consistency Score (20% weight)

This is the `consistency_ratio` pre-computed and passed in the request
body. No additional calculation is needed — the value is used directly as the
signal score. A trader who uploads every single day scores 1.0. A trader who
uploaded on 15 of 30 days scores 0.5.

### Signal 4 — Gross Margin Score (20% weight)

Gross margin measures how much revenue remains after paying for the goods sold.
A trader with high turnover but tiny margins retains little real value from
their activity. This signal separates genuine traders from turnover-inflators.

```python
def compute_gross_margin_score(total_revenue: float, total_cogs: float) -> float:
    if total_revenue == 0:
        return 0.0

    gross_margin = 1.0 - (total_cogs / total_revenue)
    # Clip to 0-1: negative gross margin means selling below cost
    return round(max(0.0, min(1.0, gross_margin)), 4)
```

---

## The Complete Scoring Pipeline

```python
import numpy as np

def compute_everiscore(
    trader_id:         str,
    daily_revenues:    list,
    total_revenue:     float,
    total_cogs:        float,
    total_expenses:    float,
    consistency_ratio: float,
    days_tracked:      int
) -> dict:

    # ── ELIGIBILITY GATE ─────────────────────────────────────────────────
    if days_tracked < 30:
        return {
            "trader_id":        trader_id,
            "eligible":         False,
            "ineligible_reason": f"Need {30 - days_tracked} more days of records",
            "everiscore":       None,
            "tier":             "INELIGIBLE",
            "tax_status":       None
        }

    # ── SIGNAL COMPUTATION ────────────────────────────────────────────────
    volatility_score   = compute_volatility_score(daily_revenues)       # 35%
    trend_score        = compute_trend_score(daily_revenues)             # 25%
    consistency_score  = consistency_ratio                               # 20%
    gross_margin_score = compute_gross_margin_score(total_revenue,
                                                    total_cogs)          # 20%

    # ── WEIGHTED COMBINATION ─────────────────────────────────────────────
    base_score = (
        volatility_score   * 0.35 +
        trend_score        * 0.25 +
        consistency_score  * 0.20 +
        gross_margin_score * 0.20
    )

    # ── TAX CLASSIFICATION ────────────────────────────────────────────────
    annualised_turnover = np.mean(daily_revenues) * 365
    tax_status = (
        "NANO_EXEMPT"  if annualised_turnover <= 12_000_000
        else "TAXABLE_1PCT"
    )

    # ── TIER CLASSIFICATION ───────────────────────────────────────────────
    # This is the PRE-FRAUD tier. The client recomputes after applying
    # the penalty multiplier from /fraud-check.
    tier = (
        "GREEN"  if base_score >= 0.70
        else "YELLOW" if base_score >= 0.40
        else "RED"
    )

    return {
        "trader_id":           trader_id,
        "everiscore":          round(base_score, 3),
        "tier":                tier,
        "tax_status":          tax_status,
        "annualised_turnover": round(annualised_turnover, 2),
        "eligible":            True,
        "ineligible_reason":   None,
        "signals": {
            "volatility_score":    volatility_score,
            "trend_score":         trend_score,
            "consistency_score":   round(consistency_score, 4),
            "gross_margin_score":  gross_margin_score
        }
    }
```

---

---

# `/fraud-check` Endpoint

## Overview

This endpoint runs three checks on a trader's transaction history to detect
patterns that suggest manipulation. It returns a `penalty_multiplier` between
0 and 1 that the Node.js backend applies to the base EveriScore. A multiplier of 1.0 means
no fraud was detected and no penalty applies. A multiplier of 0.50 means a
significant anomaly was detected and the score is halved. It is mathematically
impossible for fraud attempts to improve a trader's score — every flag makes
the score worse.

---

## Request Payload

```json
{
  "trader_id": "uuid-string",
  "daily_revenues": [45000, 48000, 52000, 43000, 47000, 150000],
  "total_revenue": 850000,
  "total_expenses": 320000,
  "trader_category": "general_trade",
  "upload_history": [
    {
      "transaction_date": "2026-04-13",
      "uploaded_at": "2026-04-13T19:45:00Z"
    },
    {
      "transaction_date": "2026-04-01",
      "uploaded_at": "2026-04-13T19:46:00Z"
    }
  ]
}
```

`upload_history` contains both the date the trader *claims* the transaction
happened (`transaction_date`) and the server timestamp of when the record was
actually received (`uploaded_at`). The Node.js backend gets `uploaded_at` from the
`created_at` column that PostgreSQL sets automatically on INSERT — **never
from the mobile client**. If the client can send the timestamp, the backdating
check is trivially defeated.

```javascript
async function buildFraudCheckPayload(traderId) {
  const [revenueRows, uploadRows, totals] = await Promise.all([

    db.query(`
      SELECT transaction_date, SUM(amount) as daily_total
      FROM transactions
      WHERE trader_id = $1 AND type = 'SALE'
      GROUP BY transaction_date
      ORDER BY transaction_date ASC
    `, [traderId]),

    // uploaded_at comes from created_at — set by PostgreSQL, not the client
    db.query(`
      SELECT transaction_date, created_at as uploaded_at
      FROM uploads
      WHERE trader_id = $1
      ORDER BY created_at ASC
    `, [traderId]),

    db.query(`
      SELECT
        SUM(CASE WHEN type = 'SALE'    THEN amount ELSE 0 END) as total_revenue,
        SUM(CASE WHEN type = 'EXPENSE' THEN amount ELSE 0 END) as total_expenses
      FROM transactions WHERE trader_id = $1
    `, [traderId])
  ]);

  return {
    trader_id:       traderId,
    daily_revenues:  revenueRows.rows.map(r => parseFloat(r.daily_total)),
    total_revenue:   parseFloat(totals.rows[0].total_revenue),
    total_expenses:  parseFloat(totals.rows[0].total_expenses),
    trader_category: "general_trade",
    upload_history:  uploadRows.rows
  };
}
```

---

## What the Endpoint Returns

```json
{
  "trader_id": "uuid-string",
  "fraud_flags": [
    {
      "type": "revenue_spike",
      "severity": "HIGH",
      "anomaly_score": -0.23
    },
    {
      "type": "suspicious_backdate",
      "severity": "MEDIUM",
      "days_gap": 12,
      "transaction_date": "2026-04-01",
      "uploaded_at": "2026-04-13T19:46:00Z"
    }
  ],
  "expense_anomaly": true,
  "expense_flag": "revenue_inflation",
  "flag_count": 2,
  "integrity_score": 0.70,
  "penalty_multiplier": 0.50
}
```

`penalty_multiplier` is the only field the client needs to act on. Multiply it
against `everiscore` from `/score` to get the final adjusted score.

---

## The Three Checks

### Check 1 — Revenue Spike Detection

A simple threshold rule fails here because it would incorrectly penalise
legitimate seasonal spikes — a trader who always does strong business during
Eid would be flagged every year. Isolation Forest solves this by defining
anomaly as "unusual *relative to this trader's own history*," not unusual in
absolute terms.

When fewer than 14 days of data exist, the system falls back to a Z-score.
A Z-score above 3.0 means the value sits more than three standard deviations
from the mean — statistically, this occurs by chance less than 0.3% of the time.

```python
from sklearn.ensemble import IsolationForest
import numpy as np

def detect_revenue_anomaly(daily_revenues: list) -> dict:

    if len(daily_revenues) < 14:
        # Z-score fallback for early-stage traders
        arr           = np.array(daily_revenues)
        mean_baseline = np.mean(arr[:-1])
        std_baseline  = np.std(arr[:-1])

        if std_baseline == 0:
            return {"anomaly": daily_revenues[-1] != mean_baseline,
                    "method": "zscore_fallback"}

        z_score = (arr[-1] - mean_baseline) / std_baseline
        return {"anomaly": z_score > 3.0,
                "z_score": round(z_score, 2),
                "method": "zscore_fallback"}

    # Isolation Forest for traders with 14+ days of history.
    # The model learns what normal looks like for THIS specific trader
    # and flags points that are unusually easy to isolate from the cluster.
    arr   = np.array(daily_revenues).reshape(-1, 1)
    model = IsolationForest(contamination=0.05, random_state=42)
    model.fit(arr)

    predictions = model.predict(arr)
    scores      = model.decision_function(arr)

    latest_anomaly = predictions[-1] == -1

    return {
        "anomaly":       bool(latest_anomaly),
        "anomaly_score": round(float(scores[-1]), 3),
        "severity":      "HIGH" if scores[-1] < -0.15 else "MEDIUM",
        "method":        "isolation_forest"
    }
```

### Check 2 — Expense Ratio Anomaly with River Online Learning

The original PRD used hardcoded baselines like `{"min": 0.30, "max": 0.85}`.
These were reasonable guesses but never improved. The River package replaces
them with running statistics that update continuously as new traders join, so
over time the baseline reflects real Nigerian market conditions rather than
estimates.

```python
from river import stats

# One running mean and variance per trader category.
# These persist in memory across requests and are periodically
# serialised to PostgreSQL so they survive service restarts.
category_baselines = {
    "general_trade": {"mean": stats.Mean(), "var": stats.Var()},
    "food_vendor":   {"mean": stats.Mean(), "var": stats.Var()},
    "artisan":       {"mean": stats.Mean(), "var": stats.Var()},
}

def normalise_category(raw: str) -> str:
    if not raw:
        return "general_trade"
    import re
    normalised = raw.lower().strip()
    normalised = re.sub(r'[\s\-]+', '_', normalised)
    return re.sub(r'[^\w]', '', normalised)

def update_expense_baseline(expense_ratio: float,
                            category: str = "general_trade"):
    """Call this every time any trader's expense ratio is computed.
    River updates the running statistics incrementally — no need to
    store all historical data, just the current mean and variance."""
    category = normalise_category(category)
    b = category_baselines.get(category,
                               category_baselines["general_trade"])
    b["mean"].update(expense_ratio)
    b["var"].update(expense_ratio)

def check_expense_anomaly(total_revenue:   float,
                          total_expenses:  float,
                          category:        str = "general_trade") -> dict:
    if total_revenue == 0:
        return {"anomaly": False, "reason": "zero_revenue"}

    category = normalise_category(category)
    expense_ratio = total_expenses / total_revenue
    b             = category_baselines.get(category,
                                           category_baselines["general_trade"])
    mean          = b["mean"].get()
    variance      = b["var"].get()

    # Guard against the case where we have very few traders in this category
    if variance is None or variance == 0:
        return {"anomaly": False, "reason": "insufficient_baseline_data",
                "expense_ratio": round(expense_ratio, 3)}

    std        = variance ** 0.5
    deviation  = abs(expense_ratio - mean)
    is_anomaly = deviation > (2 * std)

    return {
        "anomaly":       is_anomaly,
        "expense_ratio": round(expense_ratio, 3),
        "baseline_mean": round(mean, 3),
        "flag": (
            "revenue_inflation" if expense_ratio < mean - (2 * std)
            else "expense_inflation" if expense_ratio > mean + (2 * std)
            else "ok"
        )
    }
```

### Check 3 — Timestamp Integrity

This check is deterministic — no ML needed. A claimed transaction date that
is more than 7 days before the server's upload timestamp is objectively
suspicious regardless of any learned pattern. The critical implementation
detail is that `uploaded_at` must come from PostgreSQL's `NOW()`, never from
the mobile client.

```python
from datetime import datetime

def check_timestamp_integrity(upload_history: list) -> dict:
    flags    = []
    sessions = group_into_sessions(upload_history, gap_minutes=10)

    for session in sessions:
        claimed_dates  = [r["transaction_date"] for r in session]
        unique_claimed = set(claimed_dates)

        # A single session claiming 3+ different past dates suggests
        # the trader uploaded a week's worth of backdated records at once
        if len(unique_claimed) > 3:
            flags.append({
                "type":                "bulk_backdate",
                "severity":            "HIGH",
                "unique_dates_claimed": len(unique_claimed)
            })

        for record in session:
            claimed    = datetime.fromisoformat(record["transaction_date"])
            uploaded   = datetime.fromisoformat(record["uploaded_at"])
            delta_days = (uploaded.date() - claimed.date()).days

            if delta_days > 7:
                flags.append({
                    "type":             "suspicious_backdate",
                    "severity":         "MEDIUM" if delta_days < 30 else "HIGH",
                    "days_gap":         delta_days,
                    "transaction_date": record["transaction_date"],
                    "uploaded_at":      record["uploaded_at"]
                })

    # Each flag reduces the integrity score by 15%, floored at 0
    integrity_score = max(0.0, 1.0 - (len(flags) * 0.15))

    return {
        "flags":           flags,
        "flag_count":      len(flags),
        "integrity_score": round(integrity_score, 2),
        "passed":          len(flags) == 0
    }
```

---

## Penalty Multiplier Calculation

```python
def compute_penalty_multiplier(spike_result:    dict,
                               expense_result:  dict,
                               integrity_result: dict) -> float:
    multiplier = 1.0

    # Revenue spike: score cut in half
    if spike_result.get("anomaly") or spike_result.get("spike"):
        multiplier *= 0.50

    # Expense anomaly: score reduced by 40%
    if expense_result.get("anomaly"):
        multiplier *= 0.60

    # Integrity score already ranges from 0 to 1
    # Each backdating flag reduces it by 15%
    multiplier *= integrity_result["integrity_score"]

    return round(multiplier, 3)
```

If a trader triggers all three checks simultaneously, their multiplier is
`1.0 × 0.50 × 0.60 × 0.55 = 0.165` — their final EveriScore would be 16.5%
of what it would have been without fraud. Every manipulation attempt makes
the score worse, never better.

---

*Document version 1.0 — May 2026. EveriKobo ML Microservice.*