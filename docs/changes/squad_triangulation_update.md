# Changelog: Squad Velocity Triangulation

**Date:** May 2026
**Component:** Fraud Detection System (`/fraud-check`)

## Overview
Added a new "4th Pillar" to the ML fraud detection system called **Squad Velocity Triangulation**. This mechanism cross-references self-reported notebook revenue against actual digital payments received via the Squad API to detect upward notebook inflation (i.e. traders claiming they make far more than their digital footprint suggests).

## Payload Changes
The Node.js backend must now supply three new fields in the `POST /fraud-check` JSON payload:
- `notebook_revenue_daily_avg`: (float) The average daily revenue computed from notebook sales over the specified span.
- `squad_credit_daily_avg`: (float) The average daily revenue computed *exclusively* from `CREDIT` transactions on the Squad API.
- `days_with_squad_data`: (int) The number of unique days the trader has used Squad.

## Core Logic & Rules
1. **Grace Period**: If `days_with_squad_data < 7`, the check is entirely skipped. We do not penalize traders who are brand new to digital payments.
2. **Thresholds**: 
   - We expect Squad numbers to be lower than notebook numbers due to cash sales.
   - We flag anomalies when the deviation `(notebook - squad) / notebook` exceeds 85%.
   - **> 85% Deviation**: Triggers a `HIGH` severity `squad_inflation` flag. Multiplier penalty: `0.70` (30% cut to EveriScore).
   - **> 70% Deviation**: Triggers a `MEDIUM` severity `squad_inflation` flag. Multiplier penalty: `0.85` (15% cut to EveriScore).
   - **<= 70% Deviation**: No penalty applied.

## Architecture Impact
- **Endpoint**: `POST /fraud-check`
- **Output**: The multiplier returned by `/fraud-check` now factors in the `squad_inflation` penalty cumulatively with existing Revenue Spikes, Expense Anomalies, and Timestamp Integrity.
- **Node.js Action Required**: Ensure the aggregation query pulling from `squad_transactions` strictly applies `WHERE transaction_type = 'CREDIT'` to avoid miscalculating the digital velocity.
