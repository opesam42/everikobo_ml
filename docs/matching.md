# `/match` and `/match/feedback` Endpoints
## Overview

WorkConnect needs to rank job seekers for a trader's post. The matching
system has three layers that engage progressively as the platform grows.

- **Day 1**: Deterministic rule-based scoring — skill overlap, rate
  compatibility, availability. No training data needed.
- **After 50 completed matches**: River LogisticRegression activates and
  learns which features predict successful outcomes from real data.
- **After 500 matches**: ML predictions become the primary ranking signal
  with rule-based scoring as a stability backstop.

This directly satisfies the challenge brief requirement that the system
"learns and improves over time as more users join."

---

## `POST /match` — Rank Candidates

### Request

```json
{
  "job_post": {
    "lga": "Kosofe",
    "skill_needed": "delivery",
    "skills_needed": ["delivery", "logistics"],
    "max_rate": 3500,
    "trader_everiscore": 0.73
  },
  "trader": {
    "id": "uuid-string",
    "lga": "Kosofe"
  },
  "candidate_pool": [
    {
      "id": "uuid-string",
      "lga": "Kosofe",
      "skills": ["delivery", "inventory"],
      "daily_rate": 3000,
      "available": true,
      "avg_rating": 0.85,
      "jobs_completed": 12
    }
  ]
}
```

### Response

```json
{
  "ranked_candidates": [
    {
      "id": "uuid-string",
      "match_score": 0.823,
      "skill_overlap": 0.9,
      "rate_compatibility": 0.86,
      "method": "ml_blend"
    }
  ],
  "total_candidates": 8,
  "method_used": "ml_blend"
}
```

### Implementation

```python
from river import linear_model, preprocessing, compose
from collections import defaultdict

# Online learning pipeline — updates incrementally with each outcome
match_model    = compose.Pipeline(
    preprocessing.StandardScaler(),
    linear_model.LogisticRegression()
)
total_matches_learned = 0

def apply_hard_filters(job_post: dict, seekers: list) -> list:
    return [
        s for s in seekers
        if s["lga"] == job_post["lga"]
        and job_post["skill_needed"] in s["skills"]
        and s.get("available", True)
        and s["daily_rate"] <= job_post["max_rate"]
    ]

def extract_match_features(seeker: dict, job_post: dict) -> dict:
    required = set(job_post.get("skills_needed", [job_post["skill_needed"]]))
    seeker_s = set(seeker.get("skills", []))
    return {
        "skill_overlap_ratio":    len(required & seeker_s) / max(len(required), 1),
        "rate_compatibility":     1.0 - abs(seeker["daily_rate"] - job_post["max_rate"])
                                  / max(job_post["max_rate"], 1),
        "seeker_avg_rating":      seeker.get("avg_rating", 0.5),
        "seeker_jobs_completed":  min(seeker.get("jobs_completed", 0) / 50, 1.0),
        "trader_everiscore":      job_post.get("trader_everiscore", 0.5),
    }

def score_candidate_rules(seeker: dict, job_post: dict) -> float:
    f = extract_match_features(seeker, job_post)
    return round(
        f["skill_overlap_ratio"]   * 0.50 +
        f["rate_compatibility"]    * 0.15 +
        f["seeker_avg_rating"]     * 0.20 +
        f["seeker_jobs_completed"] * 0.15,
        4
    )

def rank_candidates(job_post: dict, candidate_pool: list, trader: dict) -> dict:
    eligible = apply_hard_filters(job_post, candidate_pool)

    if not eligible:
        return {"ranked_candidates": [], "total_candidates": 0,
                "method_used": "no_candidates"}

    use_ml = total_matches_learned >= 50
    scored = []

    for seeker in eligible:
        if use_ml:
            features   = extract_match_features(seeker, job_post)
            ml_score   = match_model.predict_proba_one(features).get(True, 0.5)
            rule_score = score_candidate_rules(seeker, job_post)
            # Blend ML prediction with rule-based score for stability
            final = 0.6 * ml_score + 0.4 * rule_score
            method = "ml_blend"
        else:
            final  = score_candidate_rules(seeker, job_post)
            method = "rules_only"

        scored.append({**seeker, "match_score": round(final, 4),
                       "method": method})

    ranked = sorted(scored, key=lambda x: x["match_score"], reverse=True)

    return {
        "ranked_candidates": ranked,
        "total_candidates":  len(ranked),
        "method_used":       "ml_blend" if use_ml else "rules_only"
    }
```

---

## `POST /match/feedback` — Record Match Outcome

Called after every job completion or cancellation. This is what feeds the
River online learning loop and makes matching smarter over time.

### Request

```json
{
  "seeker_id": "uuid-string",
  "job_post": {
    "lga": "Kosofe",
    "skill_needed": "delivery",
    "skills_needed": ["delivery"],
    "max_rate": 3500,
    "trader_everiscore": 0.73
  },
  "seeker": {
    "lga": "Kosofe",
    "skills": ["delivery", "inventory"],
    "daily_rate": 3000,
    "avg_rating": 0.85,
    "jobs_completed": 12
  },
  "outcome": true
}
```

`outcome` is `true` when the trader confirmed completion AND the seeker
rated the experience positively. `false` when the job was cancelled, disputed,
or the seeker no-showed.

### Response

```json
{
  "status": "learned",
  "total_matches_learned": 51,
  "ml_active": true
}
```

### Implementation

```python
def record_match_outcome(seeker: dict, job_post: dict, outcome: bool) -> dict:
    global total_matches_learned

    features = extract_match_features(seeker, job_post)
    match_model.learn_one(features, outcome)
    total_matches_learned += 1

    return {
        "status":               "learned",
        "total_matches_learned": total_matches_learned,
        "ml_active":            total_matches_learned >= 50
    }
```

---

## Node.js Integration for WorkConnect

```javascript
// When a trader submits a job post
async function rankCandidatesForJob(jobPost, trader, candidatePool) {
  try {
    const response = await fetch(`${process.env.ML_SERVICE_URL}/match`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': process.env.EVERIKOBO_API_KEY
      },
      body: JSON.stringify({
        job_post:       jobPost,
        trader:         trader,
        candidate_pool: candidatePool
      })
    });
    if (!response.ok) throw new Error(`Match service: ${response.status}`);
    return response.json();
  } catch (error) {
    console.error('Match service unavailable:', error.message);
    // Fall back to returning the candidate pool unranked
    return { ranked_candidates: candidatePool, method_used: 'fallback_unranked' };
  }
}

// When a job is completed or cancelled
async function recordMatchOutcome(seekerId, jobPost, seeker, outcome) {
  try {
    await fetch(`${process.env.ML_SERVICE_URL}/match/feedback`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': process.env.EVERIKOBO_API_KEY
      },
      body: JSON.stringify({
        seeker_id: seekerId,
        job_post:  jobPost,
        seeker:    seeker,
        outcome:   outcome   // true = success, false = cancellation
      })
    });
  } catch (error) {
    // Non-critical — log but do not surface to user
    console.error('Match feedback failed:', error.message);
  }
}
```

---

*Document version 2.0 — May 2026. EveriKobo ML Microservice.*
