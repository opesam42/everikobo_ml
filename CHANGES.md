# Bug Fixes — `fix/crash-bugs-and-edge-cases`

## `services/score_service.py`

### Empty `daily_revenues` list crash
**Function:** `compute_volatility_score`  
**Problem:** Passing an empty list caused `np.mean([])` to return `NaN`. The `mean == 0` guard does not catch `NaN` (because `NaN != 0` in Python), so the function continued to compute `np.std([]) / NaN`, producing another `NaN`. `NaN` is not JSON-serialisable, causing a 500 on the `/score` endpoint.  
**Fix:** Added an early return of `0.0` when `daily_revenues` is empty.

### `annualised_turnover` with empty list
**Function:** `compute_everiscore`  
**Problem:** `np.mean(daily_revenues) * 365` returned `NaN` when `daily_revenues` was empty, propagating `NaN` into the response.  
**Fix:** Defaults to `0.0` when the list is empty before multiplying.

---

## `services/fraud_service.py`

### Malformed timestamp crash in `group_into_sessions`
**Problem:** `datetime.fromisoformat(x.uploaded_at.replace("Z", "+00:00"))` inside the sort key had no error handling. Any malformed or unexpected timestamp format raised an unhandled `ValueError`, crashing the entire `/fraud-check` request with a 500.  
**Fix:** Extracted a `_parse_dt(ts)` helper that wraps the parse in a `try/except (ValueError, AttributeError)` and falls back to `datetime.min`, keeping the sort safe.

### Malformed timestamp crash in `check_timestamp_integrity`
**Problem:** The same unguarded `datetime.fromisoformat()` calls on `record.transaction_date` and `record.uploaded_at` inside the session loop had no error handling.  
**Fix:** Wrapped both calls in a `try/except` block; malformed records are now skipped with `continue` instead of crashing.

### Duplicate parse logic
**Problem:** The `uploaded_at` parsing was duplicated across `group_into_sessions` and the session iteration loop with slightly different patterns, making it easy for future edits to break one but not the other.  
**Fix:** Both now use the shared `_parse_dt` helper.

---

## `auth/api_key.py`

### Unauthenticated requests bypassing auth when env var is unset
**Problem:** When the `EVERIKOBO_API_KEY` environment variable was not set, `os.getenv("EVERIKOBO_API_KEY")` returned `None`. A request sent without an `X-API-Key` header also resulted in `api_key = None`. The comparison `None != None` evaluated to `False`, so the `HTTPException` was never raised and the request passed through unauthenticated.  
**Fix:**
- If `EVERIKOBO_API_KEY` is not set in the environment, the server now returns `500` immediately (misconfigured server, not a client error).
- If the key is missing from the request or does not match, the server returns `403` as expected.

---

## `models.py`

### `RankedCandidate.id` type mismatch with `Seeker.id`
**Problem:** `Seeker.id` is typed as `Optional[str] = None`, meaning a seeker can be created without an `id`. However, `RankedCandidate.id` was typed as `str` (required). In `match_service.rank_candidates`, each seeker is converted via `seeker.model_dump()` and passed directly to `RankedCandidate(...)`. When `seeker.id` was `None`, Pydantic raised a `ValidationError`, crashing the `/match` endpoint.  
**Fix:** Changed `RankedCandidate.id` to `Optional[str] = None` to be consistent with `Seeker`.
