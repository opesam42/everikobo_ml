# EveriKobo ML Microservice — README

## What This Service Is

EveriKobo has two backend services that talk to each other over HTTP. The
main Node.js backend handles the mobile app, PostgreSQL, and Squad API.
This Python FastAPI microservice handles all AI and ML work. The separation
is intentional — ML components can be updated, retrained, and deployed
independently without risking the stability of the main application.

```
React Native App
      |
      v
Node.js Backend ──────> Python ML Microservice
      |                          |

      |                  POST /score
      |                  POST /fraud-check
      |                  POST /match
      |                  POST /match/feedback
      v
PostgreSQL (Neon)
Squad API
```

The Node.js backend is the orchestrator. It calls this microservice when it
needs AI intelligence, uses the results to make product decisions, and stores
outcomes in PostgreSQL. It does not need to understand the internals of any
endpoint — only what to send and what to do with what comes back.

---

## Setup

```bash
pip install fastapi uvicorn numpy scikit-learn river python-dotenv

cp .env.example .env

uvicorn main:app --reload --port 8000
```

```bash
# .env.example
EVERIKOBO_API_KEY=your_shared_api_key_here
PORT=8000
```

```bash
# Node.js .env
ML_SERVICE_URL=http://localhost:8000
ML_SERVICE_URL=https://everikobo-ml-production.up.railway.app  # production
EVERIKOBO_API_KEY=same_key_as_python_service
```

---

## Authentication

All endpoints except `/health` require an API key header:

```
X-API-Key: your_api_key_here
```

```python
from fastapi import FastAPI, Header, HTTPException, Depends
import os

app = FastAPI()

def verify_api_key(x_api_key: str = Header(...)):
    expected = os.getenv("EVERIKOBO_API_KEY", "dev_api_key_123")
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "EveriKobo ML Microservice"}
```

Every protected endpoint includes `Depends(verify_api_key)`. Node.js must
send the `X-API-Key` header on every request.

---

## Endpoints at a Glance

| Endpoint | What It Does | Client Action |
|---|---|---|

| `POST /score` | Computes EveriScore from transaction history | Multiply returned `everiscore` by fraud penalty |
| `POST /fraud-check` | Runs ML anomaly detection | Apply `penalty_multiplier` to base score |
| `POST /match` | Ranks job seekers for a WorkConnect post | Display top candidates in UI |
| `POST /match/feedback` | Records match outcome for online learning | Call after every job completion or cancellation |

---

## How Scoring Comes Together

`/score` and `/fraud-check` run in parallel using `Promise.all` because they
use different data and neither depends on the other. This cuts response time
roughly in half.

```javascript
async function computeFinalEveriScore(traderId) {

  const [scorePayload, fraudPayload] = await Promise.all([
    buildScorePayload(traderId),
    buildFraudCheckPayload(traderId)
  ]);

  if (scorePayload.days_tracked < 30) {
    const daysNeeded = 30 - scorePayload.days_tracked;
    return {
      eligible: false,
      ineligible_reason: `Upload ${daysNeeded} more days of records to unlock your EveriScore`,
      tier: 'INELIGIBLE'
    };
  }

  const [scoreResult, fraudResult] = await Promise.all([
    callScoreEndpoint(scorePayload),
    callFraudCheckEndpoint(fraudPayload)
  ]);

  const finalScore = scoreResult.everiscore * fraudResult.penalty_multiplier;

  // Always recompute tier from the FINAL adjusted score.
  // The fraud penalty may have pushed the score into a different tier.
  // A GREEN score of 0.71 with a 0.50 penalty becomes 0.355 which is RED.
  const finalTier = finalScore >= 0.70 ? 'GREEN'
                  : finalScore >= 0.40 ? 'YELLOW'
                  : 'RED';

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

Neither endpoint should ever block the trader from getting a response. If
the microservice is temporarily unavailable, fall back to safe defaults.

```javascript
async function callScoreEndpoint(payload) {
  try {
    const response = await fetch(`${process.env.ML_SERVICE_URL}/score`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': process.env.EVERIKOBO_API_KEY
      },
      body: JSON.stringify(payload)
    });
    if (!response.ok) throw new Error(`Score service: ${response.status}`);
    return response.json();
  } catch (error) {
    console.error('Score service unavailable:', error.message);
    return { everiscore: null, tier: 'UNAVAILABLE', eligible: false,
             ineligible_reason: 'Scoring service temporarily unavailable' };
  }
}

async function callFraudCheckEndpoint(payload) {
  try {
    const response = await fetch(`${process.env.ML_SERVICE_URL}/fraud-check`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': process.env.EVERIKOBO_API_KEY
      },
      body: JSON.stringify(payload)
    });
    if (!response.ok) throw new Error(`Fraud check: ${response.status}`);
    return response.json();
  } catch (error) {
    console.error('Fraud check unavailable:', error.message);
    // Default to no penalty rather than blocking the scoring flow.
    // Better to occasionally miss a fraud flag than to always
    // block legitimate traders from getting their score.
    return { penalty_multiplier: 1.0, flag_count: 0, fraud_flags: [] };
  }
}
```

---

## Detailed Documentation

The technical documentation for the ML endpoints has been split into dedicated files for readability. Please refer to the following guides:

- **[Scoring System Documentation](docs/scoring.md)**: Deep dive into the `/score` endpoint, the four signals, and why it's rule-based.
- **[Fraud Detection Documentation](docs/fraud_check.md)**: Deep dive into the `/fraud-check` endpoint, Isolation Forest, River Online Learning persistence, and timestamp integrity.
- **[WorkConnect Matching Documentation](docs/matching.md)**: Details on the `/match` and `/match/feedback` endpoints, including the rule-based to ML transition.
