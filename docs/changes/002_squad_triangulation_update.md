# Changelog: Digital Velocity Triangulation (Squad + Mono)

**Date:** May 2026
**Component:** Fraud Detection System (`/fraud-check`)

## Overview
Added the "4th Pillar" to the ML fraud detection system called **Digital Velocity Triangulation**. This mechanism cross-references self-reported notebook revenue against actual digital payments received via the **Squad API** (EveriKobo's platform) and the **Mono Open Banking API** (external/pre-existing bank history). By combining both sources, we get a complete, verified picture of the trader's digital inflows without double-counting.

## Payload Changes
The Node.js backend must now supply these fields in the `POST /fraud-check` JSON payload:
- `notebook_revenue_daily_avg`: (float) Average daily revenue computed from notebook sales over the specified span.
- `squad_credit_daily_avg`: (float) Average daily revenue computed exclusively from `CREDIT` transactions on the Squad API.
- `mono_credit_daily_avg`: (float) Average daily revenue computed exclusively from `credit` transactions on the Mono Open Banking API.
- `days_with_squad_data`: (int) Number of unique days with Squad data.
- `days_with_mono_data`: (int) Number of unique days with Mono data.

## Core Logic & Rules
1. **Combined Digital Average**: `squad_credit_daily_avg + mono_credit_daily_avg`.
2. **Grace Period**: If `max(days_with_squad_data, days_with_mono_data) < 7`, the check is entirely skipped. We do not penalize traders who are brand new to digital payments.
3. **Thresholds**: 
   - We expect the combined digital numbers to be lower than notebook numbers due to cash sales.
   - We flag anomalies when the deviation `(notebook - combined_digital) / notebook` exceeds 85%.
   - **> 85% Deviation**: Triggers a `HIGH` severity `digital_inflation` flag. Multiplier penalty: `0.70` (30% cut to EveriScore).
   - **> 70% Deviation**: Triggers a `MEDIUM` severity `digital_inflation` flag. Multiplier penalty: `0.85` (15% cut to EveriScore).
   - **<= 70% Deviation**: No penalty applied.

## Architecture Impact
- **Endpoint**: `POST /fraud-check`
- **Output**: The multiplier returned by `/fraud-check` now factors in the `digital_inflation` penalty cumulatively.
- **Node.js Action Required**: Ensure the aggregation queries pulling from both `squad_transactions` and `mono_transactions` strictly apply `transaction_type = 'CREDIT'` filters.
