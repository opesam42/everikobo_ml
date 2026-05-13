# Category Normalisation Strategy

## What This File Is

This file tracks the coordination of category strings between the Python ML microservice and the Node.js backend for the fraud detection system.

---

## The Problem and The Solution

The `/fraud-check` endpoint uses River online learning to maintain running statistics about expense ratios per trader category. Originally, we needed the Node.js backend to ensure it always sent consistent category strings (e.g., always "food_vendor", never "Food Vendor" or "food vendor") to avoid fragmenting the baseline data.

**The Solution:** Defensive Engineering in Python.

We have implemented a `normalise_category` helper function directly in the Python microservice. This function takes whatever category string the Node.js backend sends and converts it into a canonical lowercase underscore format before it touches the `category_baselines` dictionary.

```python
import re

def normalise_category(raw: str) -> str:
    """
    Convert any category string into a consistent canonical format.
    """
    if not raw:
        return "general_trade"
    
    normalised = raw.lower().strip()
    normalised = re.sub(r'[\s\-]+', '_', normalised)
    normalised = re.sub(r'[^\w]', '', normalised)
    
    return normalised
```

Because we use a `defaultdict`-like pattern in our River `baseline_repo` along with this normalization function, the Python service is genuinely robust to whatever the Node.js backend sends:
- `"Electronic Work"`     -> `"electronic_work"`
- `"Food Vendor"`         -> `"food_vendor"`
- `"electronics_trader"`  -> `"electronics_trader"`
- `"ARTISAN"`             -> `"artisan"`
- `"General Trade "`      -> `"general_trade"`

## What The Client Needs To Do

**Nothing.**

Because normalisation is handled centrally on the Python side, we have created a single point of truth. The client can send the raw category string exactly as it was entered in the onboarding form or stored in the database. We do not need to rely on the Node.js backend implementing normalization correctly and consistently across every code path (onboarding forms, admin tools, data migration scripts, etc.).

Just ensure that the `trader_category` is included in the `/fraud-check` request payload (it defaults to `general_trade` if missing).
