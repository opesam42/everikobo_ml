# UI Signals — What to Show the Trader Instead of a Score

## The Core Product Decision

EveriKobo does not show traders a raw credit score.

A number like 0.673 is meaningless to Mama Ngozi. "You qualify for a loan
referral" tells her exactly what to do next. The score is our internal risk
assessment — the trader sees outcomes and directional feedback, not algorithms.

This also protects the system. If traders know the exact formula, they will
optimise the number rather than running a genuine business. Hiding the score
preserves data integrity.

---

## What the ML Service Returns

The `/score` endpoint already returns four individual signal scores inside
the `signals` field:

```json
{
  "everiscore": 0.673,
  "tier": "YELLOW",
  "signals": {
    "volatility_score": 0.71,
    "trend_score": 0.58,
    "consistency_score": 0.42,
    "gross_margin_score": 0.68
  }
}
```

The mobile app should:
- **Never display** `everiscore` to the trader
- **Never display** the raw signal numbers (0.71, 0.58 etc.)
- **Use `tier`** to determine which state screen to show
- **Use `signals`** to render directional progress bars only

---

## The Four States — What Each Screen Shows

### State 1 — ONBOARDING (days_tracked < 30)

```
Header:     "Building Your Financial Profile"
Subtext:    "Upload X more days of records to unlock your EveriScore"
Visual:     Progress bar — days uploaded vs 30-day target
CTA:        "Scan Today's Records" button
```

No signals shown. No score shown. Just progress toward the threshold.

```javascript
// Node.js determines this before calling the ML service
if (scorePayload.days_tracked < 30) {
  return {
    state: 'ONBOARDING',
    days_uploaded: scorePayload.days_tracked,
    days_needed: 30 - scorePayload.days_tracked,
    progress_pct: Math.round((scorePayload.days_tracked / 30) * 100)
  };
}
```

---

### State 2 — RED (final_score < 0.40)

```
Header:     "Keep Building Your Profile"
Subtext:    "Upload consistently to improve your financial identity"
Visual:     Four signal bars (see below)
CTA:        "Scan Today's Records" button
No loan referral shown.
No WorkConnect tab shown.
```

---

### State 3 — YELLOW (0.40 ≤ final_score < 0.70)

```
Header:     "Your Profile is Looking Strong"
Subtext:    "Keep uploading to unlock loan referrals and WorkConnect"
Visual:     Four signal bars (see below)
CTA:        "Scan Today's Records" button
WorkConnect tab: hidden
Loan referral: hidden
Tax report: show if tax_status = TAXABLE_1PCT
```

---

### State 4 — GREEN (final_score ≥ 0.70)

```
Header:     "Congratulations — You Qualify"
Subtext:    "Your financial profile is strong"
Visual:     Four signal bars (see below)
CTA 1:      "Apply for a Loan Referral" → Squad Payment Link
CTA 2:      "Post a Job on WorkConnect" → unlocked
Tax report: show if tax_status = TAXABLE_1PCT
```

---

## The Four Signal Bars — How to Render Them

Show four horizontal progress bars with labels. Use the signal values from
the ML response to set bar width as a percentage. Do NOT show the raw numbers.

```
Revenue Consistency    [████████░░]   Good
Business Growth        [██████████]   Excellent
Upload Regularity      [████░░░░░░]   Needs Work
Profit Margin          [████████░░]   Good
```

### Signal to Label Mapping

| Signal field | Bar label | Icon suggestion |
|---|---|---|
| `volatility_score` | "Revenue Consistency" | 📊 |
| `trend_score` | "Business Growth" | 📈 |
| `consistency_score` | "Upload Regularity" | 📅 |
| `gross_margin_score` | "Profit Margin" | 💰 |

### Bar Width Calculation

```javascript
// Convert 0-1 score to percentage for bar width
// Round to nearest 10% so the bar looks intentional, not precise
function toBarWidth(score) {
  return Math.round(score * 10) * 10;  // e.g. 0.71 → 70%
}

// Label based on score range
function toBarLabel(score) {
  if (score >= 0.75) return "Excellent";
  if (score >= 0.55) return "Good";
  if (score >= 0.35) return "Needs Work";
  return "Low";
}
```

### Colour Coding

```
Excellent (≥ 0.75)  → Green   #16A34A
Good (≥ 0.55)       → Blue    #1D4ED8
Needs Work (≥ 0.35) → Yellow  #CA8A04
Low (< 0.35)        → Red     #DC2626
```

---

## Full Response Shape Node.js Should Send to Mobile

After computing the final score, Node.js transforms the ML response into
a UI-ready object before sending it to the mobile app. The mobile app never
sees the raw score — only this processed object.

```javascript
function buildUIResponse(traderId, scoreResult, fraudResult, finalScore, finalTier) {

  // Signal bars — transform raw scores into display-ready objects
  const signals = scoreResult.signals ? [
    {
      label:     "Revenue Consistency",
      icon:      "chart-bar",
      bar_width: toBarWidth(scoreResult.signals.volatility_score),
      bar_label: toBarLabel(scoreResult.signals.volatility_score),
      color:     toBarColor(scoreResult.signals.volatility_score),
      tip:       "Consistent daily revenue improves this signal"
    },
    {
      label:     "Business Growth",
      icon:      "trending-up",
      bar_width: toBarWidth(scoreResult.signals.trend_score),
      bar_label: toBarLabel(scoreResult.signals.trend_score),
      color:     toBarColor(scoreResult.signals.trend_score),
      tip:       "Growing weekly revenue improves this signal"
    },
    {
      label:     "Upload Regularity",
      icon:      "calendar",
      bar_width: toBarWidth(scoreResult.signals.consistency_score),
      bar_label: toBarLabel(scoreResult.signals.consistency_score),
      color:     toBarColor(scoreResult.signals.consistency_score),
      tip:       "Upload your records every day to improve this signal"
    },
    {
      label:     "Profit Margin",
      icon:      "currency-naira",
      bar_width: toBarWidth(scoreResult.signals.gross_margin_score),
      bar_label: toBarLabel(scoreResult.signals.gross_margin_score),
      color:     toBarColor(scoreResult.signals.gross_margin_score),
      tip:       "Strong margins show your business retains value"
    }
  ] : [];

  // Tax status message
  const tax_message = scoreResult.tax_status === 'NANO_EXEMPT'
    ? { exempt: true,  text: "Your business is tax exempt — annual turnover below ₦12M" }
    : { exempt: false, text: "Your business may have a tax obligation — download your report" };

  // State-specific messaging
  const state_messages = {
    ONBOARDING: {
      header:  "Building Your Financial Profile",
      subtext: `Upload ${scoreResult.ineligible_reason} to unlock your profile`,
      show_loan_referral:  false,
      show_workconnect:    false,
      show_tax_report:     false
    },
    RED: {
      header:  "Keep Building Your Profile",
      subtext: "Upload consistently to strengthen your financial identity",
      show_loan_referral:  false,
      show_workconnect:    false,
      show_tax_report:     scoreResult.tax_status === 'TAXABLE_1PCT'
    },
    YELLOW: {
      header:  "Your Profile is Looking Strong",
      subtext: "Keep uploading to unlock loan referrals and WorkConnect",
      show_loan_referral:  false,
      show_workconnect:    false,
      show_tax_report:     scoreResult.tax_status === 'TAXABLE_1PCT'
    },
    GREEN: {
      header:  "Congratulations — You Qualify",
      subtext: "Your financial profile is strong",
      show_loan_referral:  true,
      show_workconnect:    true,
      show_tax_report:     scoreResult.tax_status === 'TAXABLE_1PCT'
    }
  };

  const messaging = state_messages[finalTier] || state_messages['ONBOARDING'];

  return {
    trader_id:    traderId,
    state:        finalTier,           // ONBOARDING | RED | YELLOW | GREEN
    ...messaging,                      // header, subtext, show_* flags
    signals:      signals,             // four bar objects for the UI
    tax_status:   scoreResult.tax_status,
    tax_message:  tax_message,
    fraud_flags:  fraudResult.flag_count > 0 ? fraudResult.flag_count : 0,
    // Internal fields — log these but never send to mobile app
    _internal: {
      base_score:          scoreResult.everiscore,
      final_score:         finalScore,
      penalty_multiplier:  fraudResult.penalty_multiplier,
      annualised_turnover: scoreResult.annualised_turnover
    }
  };
}

// Helper functions
function toBarWidth(score) {
  return Math.round(score * 10) * 10;
}

function toBarLabel(score) {
  if (score >= 0.75) return "Excellent";
  if (score >= 0.55) return "Good";
  if (score >= 0.35) return "Needs Work";
  return "Low";
}

function toBarColor(score) {
  if (score >= 0.75) return "#16A34A";  // green
  if (score >= 0.55) return "#1D4ED8";  // blue
  if (score >= 0.35) return "#CA8A04";  // yellow
  return "#DC2626";                      // red
}
```

---

## What the Mobile App Receives — Example

This is what Praise sends to the React Native app after processing.
The mobile app renders directly from this — no further computation needed.

```json
{
  "trader_id": "uuid-string",
  "state": "YELLOW",
  "header": "Your Profile is Looking Strong",
  "subtext": "Keep uploading to unlock loan referrals and WorkConnect",
  "show_loan_referral": false,
  "show_workconnect": false,
  "show_tax_report": false,
  "signals": [
    {
      "label": "Revenue Consistency",
      "icon": "chart-bar",
      "bar_width": 70,
      "bar_label": "Good",
      "color": "#1D4ED8",
      "tip": "Consistent daily revenue improves this signal"
    },
    {
      "label": "Business Growth",
      "icon": "trending-up",
      "bar_width": 60,
      "bar_label": "Good",
      "color": "#1D4ED8",
      "tip": "Growing weekly revenue improves this signal"
    },
    {
      "label": "Upload Regularity",
      "icon": "calendar",
      "bar_width": 40,
      "bar_label": "Needs Work",
      "color": "#CA8A04",
      "tip": "Upload your records every day to improve this signal"
    },
    {
      "label": "Profit Margin",
      "icon": "currency-naira",
      "bar_width": 70,
      "bar_label": "Good",
      "color": "#1D4ED8",
      "tip": "Strong margins show your business retains value"
    }
  ],
  "tax_status": "NANO_EXEMPT",
  "tax_message": {
    "exempt": true,
    "text": "Your business is tax exempt — annual turnover below ₦12M"
  },
  "fraud_flags": 0
}
```

---

## For the Demo on Friday

The demo flow showing the score dashboard should show:

1. Trader scans notebook
2. Processing indicator for 2-3 seconds
3. Dashboard appears showing state (GREEN for demo)
4. Four signal bars animate in
5. "Congratulations — You Qualify" header
6. "Apply for Loan Referral" button appears
7. "Post a Job on WorkConnect" tab unlocks
8. Tax report prompt appears if applicable

Never show a number. Never show "0.673". Show the state and the bars.

---

## Key Rule for Praise

The `_internal` object in the response should be logged server-side for
debugging but **never forwarded to the React Native app**. Strip it before
sending the final response to the mobile client.

```javascript
// Before sending to mobile app — remove internal fields
const { _internal, ...mobileResponse } = buildUIResponse(...);
res.json(mobileResponse);  // _internal never reaches the mobile app
```

---

*Document version 1.0 — May 2026. EveriKobo UI Signal Communication.*