# `/fraud-check` Endpoint
## Overview

Runs three checks and returns a `penalty_multiplier` between 0 and 1.
A multiplier of 1.0 means no fraud detected. A multiplier of 0.50 means
the score is halved. Every fraud attempt makes the score worse, never better.

---

## Request Payload

```json
{
  "trader_id": "uuid-string",
  "daily_revenues": [45000, 48000, 52000, 43000, 47000, 150000],
  "total_revenue": 850000,
  "total_expenses": 320000,
  "trader_category": "general_trade",
  "trader": { "registered_at": "2026-04-01T00:00:00Z" },
  "upload_history": [
    { "transaction_date": "2026-04-13", "uploaded_at": "2026-04-13T19:45:00Z" },
    { "transaction_date": "2026-04-01", "uploaded_at": "2026-04-13T19:46:00Z" }
  ]
}
```

`uploaded_at` must come from PostgreSQL's `created_at` column — set by the
database server on INSERT, never from the mobile client. If the client can
send the timestamp, backdating detection is trivially defeated.

`trader.registered_at` enables the onboarding grace period. New traders
uploading 5 months of historical notebook data should not be penalised.

```javascript
async function buildFraudCheckPayload(traderId) {
  const [revenueRows, uploadRows, totals, traderRow] = await Promise.all([
    db.query(`
      SELECT transaction_date, SUM(amount) as daily_total
      FROM transactions WHERE trader_id = $1 AND type = 'SALE'
      GROUP BY transaction_date ORDER BY transaction_date ASC
    `, [traderId]),
    // uploaded_at from created_at — set by PostgreSQL, not the client
    db.query(`
      SELECT transaction_date, created_at as uploaded_at
      FROM uploads WHERE trader_id = $1 ORDER BY created_at ASC
    `, [traderId]),
    db.query(`
      SELECT
        SUM(CASE WHEN type = 'SALE'    THEN amount ELSE 0 END) as total_revenue,
        SUM(CASE WHEN type = 'EXPENSE' THEN amount ELSE 0 END) as total_expenses
      FROM transactions WHERE trader_id = $1
    `, [traderId]),
    db.query(`
      SELECT registered_at, trader_category FROM traders WHERE id = $1
    `, [traderId])
  ]);

  return {
    trader_id:       traderId,
    daily_revenues:  revenueRows.rows.map(r => parseFloat(r.daily_total)),
    total_revenue:   parseFloat(totals.rows[0].total_revenue),
    total_expenses:  parseFloat(totals.rows[0].total_expenses),
    trader_category: traderRow.rows[0].trader_category || 'general_trade',
    trader:          { registered_at: traderRow.rows[0].registered_at },
    upload_history:  uploadRows.rows
  };
}
```

---

## Response

```json
{
  "trader_id": "uuid-string",
  "fraud_flags": [
    { "type": "revenue_spike", "severity": "HIGH", "anomaly_score": -0.23 },
    { "type": "suspicious_backdate", "severity": "MEDIUM", "days_gap": 12 }
  ],
  "expense_anomaly": true,
  "expense_flag": "revenue_inflation",
  "flag_count": 2,
  "integrity_score": 0.70,
  "penalty_multiplier": 0.50
}
```

---

## Check 1 — Revenue Spike Detection

Isolation Forest defines anomaly as unusual *relative to this trader's own
history*, not unusual in absolute terms. A trader who always spikes during
Eid is not flagged. A trader who spikes once after 30 consistent days is.

Z-score fallback applies when fewer than 14 days of data exist.

```python
from sklearn.ensemble import IsolationForest
import numpy as np

def detect_revenue_anomaly(daily_revenues: list) -> dict:
    if len(daily_revenues) < 14:
        arr           = np.array(daily_revenues)
        mean_baseline = np.mean(arr[:-1])
        std_baseline  = np.std(arr[:-1])
        if std_baseline == 0:
            return {"anomaly": daily_revenues[-1] != mean_baseline,
                    "method": "zscore_fallback"}
        z_score = (arr[-1] - mean_baseline) / std_baseline
        return {"anomaly": z_score > 3.0, "z_score": round(z_score, 2),
                "method": "zscore_fallback"}

    arr   = np.array(daily_revenues).reshape(-1, 1)
    model = IsolationForest(contamination=0.05, random_state=42)
    model.fit(arr)
    predictions    = model.predict(arr)
    scores         = model.decision_function(arr)
    latest_anomaly = predictions[-1] == -1

    return {
        "anomaly":       bool(latest_anomaly),
        "anomaly_score": round(float(scores[-1]), 3),
        "severity":      "HIGH" if scores[-1] < -0.15 else "MEDIUM",
        "method":        "isolation_forest"
    }
```

---

## Check 2 — Expense Ratio Anomaly with River Online Learning

River replaces hardcoded baselines with running statistics that update
as new traders join. After 1,000 traders, the baseline reflects real
Lagos market conditions rather than developer estimates.

`EWMean` and `EWVar` give more weight to recent observations, making the
baseline adapt faster to inflation and supply chain changes — important
for the volatile Nigerian market.

`ADWIN` detects when market conditions have shifted so dramatically that
the baseline needs to be reset entirely.

```python
from river import stats, drift
from collections import defaultdict
import re

category_baselines = defaultdict(
    lambda: {
        "mean": stats.EWMean(alpha=0.1),  # adapts to recent market changes
        "var":  stats.EWVar(alpha=0.1)
    }
)

category_drift_detectors = defaultdict(drift.ADWIN)

def normalise_category(raw: str) -> str:
    if not raw:
        return "general_trade"
    normalised = raw.lower().strip()
    normalised = re.sub(r'[\s\-]+', '_', normalised)
    return re.sub(r'[^\w]', '', normalised)

def update_expense_baseline(expense_ratio: float, category: str = "general_trade"):
    category = normalise_category(category)
    b = category_baselines[category]
    b["mean"].update(expense_ratio)
    b["var"].update(expense_ratio)

    # Check if market conditions have drifted significantly
    detector = category_drift_detectors[category]
    detector.update(expense_ratio)
    if detector.drift_detected:
        # Reset the baseline — old market conditions no longer apply
        print(f"Market drift detected in {category} — resetting baseline")
        category_baselines[category] = {
            "mean": stats.EWMean(alpha=0.1),
            "var":  stats.EWVar(alpha=0.1)
        }

def check_expense_anomaly(total_revenue: float, total_expenses: float,
                          category: str = "general_trade") -> dict:
    if total_revenue == 0:
        return {"anomaly": False, "reason": "zero_revenue"}

    category      = normalise_category(category)
    expense_ratio = total_expenses / total_revenue
    b             = category_baselines[category]
    mean          = b["mean"].get()
    variance      = b["var"].get()

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

### State Persistence for River (The `/baselines` Endpoints)

Because River uses **Online Learning**, its knowledge is stateful and lives in the Python microservice's RAM (`stats.EWMean`, `stats.EWVar`, etc.). FastAPI microservices are designed to be stateless and ephemeral—if the server restarts, scales, or crashes, River's memory is wiped clean, and the anomaly detection loses all its learned market baselines.

To solve this, the Python service exposes two persistence endpoints:
- `GET /baselines`: Node.js calls this periodically (e.g., via a cron job) to pull a serialized snapshot of River's current learning state and save it permanently into PostgreSQL.
- `POST /baselines`: Whenever the Python service boots up, Node.js calls this endpoint to inject the latest saved snapshot back into memory. This ensures the ML model resumes exactly where it left off, allowing safe restarts and deployments without amnesia.

---

## Check 3 — Timestamp Integrity with Onboarding Grace Period

New traders uploading 5 months of historical notebook data should not be
penalised. The grace period relaxes backdating thresholds for the first 14
days after registration.

```python
from datetime import datetime, timezone

def check_timestamp_integrity(upload_history: list, trader: dict) -> dict:
    flags = []

    registered_at   = datetime.fromisoformat(trader["registered_at"])
    now             = datetime.now(timezone.utc)
    days_since_join = (now - registered_at).days

    # During the 14-day onboarding window, allow up to 180 days of backdating
    # so traders can upload their historical notebook records legitimately.
    # After the grace period, revert to the strict 7-day rule.
    backdate_threshold = 180 if days_since_join <= 14 else 7

    sessions = group_into_sessions(upload_history, gap_minutes=10)

    for session in sessions:
        claimed_dates  = [r["transaction_date"] for r in session]
        unique_claimed = set(claimed_dates)

        # Only flag bulk backdating after the onboarding grace period
        if len(unique_claimed) > 3 and days_since_join > 14:
            flags.append({
                "type": "bulk_backdate", "severity": "HIGH",
                "unique_dates_claimed": len(unique_claimed)
            })

        for record in session:
            claimed    = datetime.fromisoformat(record["transaction_date"])
            uploaded   = datetime.fromisoformat(record["uploaded_at"])
            delta_days = (uploaded.date() - claimed.date()).days

            if delta_days > backdate_threshold:
                flags.append({
                    "type":             "suspicious_backdate",
                    "severity":         "MEDIUM" if delta_days < 30 else "HIGH",
                    "days_gap":         delta_days,
                    "transaction_date": record["transaction_date"],
                    "uploaded_at":      record["uploaded_at"]
                })

    integrity_score = max(0.0, 1.0 - (len(flags) * 0.15))

    return {
        "flags": flags, "flag_count": len(flags),
        "integrity_score": round(integrity_score, 2),
        "onboarding_mode": days_since_join <= 14,
        "passed": len(flags) == 0
    }
```

---

---

## Check 4 — Digital Velocity Triangulation (Squad + Mono)

Cross-references self-reported notebook data with actual digital payments received via Squad and Mono Open Banking to detect upward notebook inflation.

```python
def check_velocity_triangulation(
    notebook_revenue_daily_avg: float,
    squad_credit_daily_avg: float,
    mono_credit_daily_avg: float,
    days_with_squad_data: int,
    days_with_mono_data: int
) -> dict:

    combined_digital_avg = squad_credit_daily_avg + mono_credit_daily_avg
    total_days = max(days_with_squad_data, days_with_mono_data)

    if total_days < 7:
        return {
            "checked": False,
            "reason": "insufficient_digital_history",
            "penalty": 1.0,
            "sources_available": {"squad": days_with_squad_data > 0, "mono": days_with_mono_data > 0}
        }

    if notebook_revenue_daily_avg == 0:
        return {"checked": False, "reason": "zero_notebook_revenue", "penalty": 1.0}

    deviation = (notebook_revenue_daily_avg - combined_digital_avg) / notebook_revenue_daily_avg

    if deviation > 0.85:
        return {
            "checked": True, "deviation": round(deviation, 3), "anomaly": True,
            "severity": "HIGH", "penalty": 0.70,
            "combined_digital_avg": round(combined_digital_avg, 2),
            "sources_used": {"squad": squad_credit_daily_avg > 0, "mono": mono_credit_daily_avg > 0}
        }
    elif deviation > 0.70:
        return {
            "checked": True, "deviation": round(deviation, 3), "anomaly": True,
            "severity": "MEDIUM", "penalty": 0.85,
            "combined_digital_avg": round(combined_digital_avg, 2),
            "sources_used": {"squad": squad_credit_daily_avg > 0, "mono": mono_credit_daily_avg > 0}
        }
    else:
        return {
            "checked": True, "deviation": round(deviation, 3), "anomaly": False,
            "penalty": 1.0,
            "combined_digital_avg": round(combined_digital_avg, 2),
            "sources_used": {"squad": squad_credit_daily_avg > 0, "mono": mono_credit_daily_avg > 0}
        }
```

---

## Penalty Multiplier

```python
def compute_penalty_multiplier(spike_result: dict, expense_result: dict,
                               integrity_result: dict, squad_result: dict = None) -> float:
    multiplier = 1.0
    if spike_result.get("anomaly") or spike_result.get("spike"):
        multiplier *= 0.50
    if expense_result.get("anomaly"):
        multiplier *= 0.60
    multiplier *= integrity_result["integrity_score"]
    
    if squad_result and squad_result.get("checked"):
        multiplier *= squad_result.get("penalty", 1.0)
        
    return round(multiplier, 3)
```

All four checks triggered simultaneously: `1.0 × 0.50 × 0.60 × 0.55 × 0.70 = 0.115`.
Final score would be 11.5% of what it would have been without fraud.
