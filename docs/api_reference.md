# EveriKobo ML Microservice — API Reference

This document provides everything you (Praise) need to interact with the Python ML Microservice from your Node.js backend. 

## Base URL
- **Local:** `http://localhost:8000`
- **Production:** *(Set via your `ML_SERVICE_URL` environment variable)*

---

## 1. `POST /score`
Computes the trader's EveriScore using deterministic, rule-based logic to ensure explainability for lending decisions.

### Request Payload
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
**Notes on Payload:**
- `daily_revenues`: Array of daily sales totals, chronologically ordered (oldest to newest).
- `total_cogs`: Sum of Cost of Goods expenses only.
- `consistency_ratio`: (Unique upload days) ÷ (calendar span from first to last upload).

### Response
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
**What you do with it:**
- Store the `everiscore` and `signals`.
- **Wait** for the `/fraud-check` response to apply the `penalty_multiplier` before finalizing the `tier`.

---

## 2. `POST /fraud-check`
Runs anomaly detection on transaction patterns to detect manipulation or backdating.

### Request Payload
```json
{
  "trader_id": "uuid-string",
  "daily_revenues": [45000, 48000, 52000, 43000, 47000, 150000],
  "total_revenue": 850000,
  "total_expenses": 320000,
  "trader_category": "food_vendor",
  "upload_history": [
    {
      "transaction_date": "2026-04-13",
      "uploaded_at": "2026-04-13T19:45:00Z"
    }
  ]
}
```
**Notes on Payload:**
- `trader_category`: Pass whatever string you have (e.g., "Food Vendor"). **The Python side automatically normalizes it**, so you don't need to format it before sending.
- `uploaded_at`: Must come from PostgreSQL `created_at` (server time), never from the mobile client.

### Response
```json
{
  "trader_id": "uuid-string",
  "fraud_flags": [
    {
      "type": "revenue_spike",
      "severity": "HIGH",
      "anomaly_score": -0.23
    }
  ],
  "expense_anomaly": true,
  "expense_flag": "revenue_inflation",
  "flag_count": 1,
  "integrity_score": 0.50,
  "penalty_multiplier": 0.50
}
```
**What you do with it:**
- Multiply the `penalty_multiplier` by the `everiscore` from the `/score` endpoint to get the final score.
- Recompute the final tier based on the final score.

---

## 3. Managing Baselines (`/baselines`)
The fraud detection system uses River online learning to learn market conditions over time. Since Railway/Python containers restart, you need to back up and restore this memory using your PostgreSQL database.

### `GET /baselines`
Fetches the current baseline memory state.
**Action for Praise:** Call this via a CRON job (e.g., every 6 hours) and save the JSON response to a `baselines` table in PostgreSQL.

### `POST /baselines`
Restores the baseline memory state.
**Action for Praise:** Call this whenever your Node.js server detects the Python service booting up (or during your own startup sequence) and push the last saved baseline state from PostgreSQL.

**Payload:**
```json
{
  "baselines": [
    {
      "category": "general_trade",
      "mean": 0.45,
      "variance": 0.02,
      "count": 150
    }
  ]
}
```

---

## Example Flow: Putting It Together

To optimize performance, call `/score` and `/fraud-check` **in parallel**:

```javascript
async function computeFinalEveriScore(traderId) {
  // 1. Build payloads
  const [scorePayload, fraudPayload] = await Promise.all([
    buildScorePayload(traderId),
    buildFraudCheckPayload(traderId)
  ]);

  // 2. Check eligibility early (Needs 30 days of data)
  if (scorePayload.days_tracked < 30) {
    return { eligible: false, tier: 'INELIGIBLE' };
  }

  // 3. Fire calls in parallel
  const [scoreResult, fraudResult] = await Promise.all([
    callScoreEndpoint(scorePayload),
    callFraudCheckEndpoint(fraudPayload)
  ]);

  // 4. Calculate Final Score & Tier
  const finalScore = scoreResult.everiscore * fraudResult.penalty_multiplier;
  const finalTier = finalScore >= 0.70 ? 'GREEN'
                  : finalScore >= 0.40 ? 'YELLOW'
                  : 'RED';

  // 5. Save to DB and return to client...
}
```
