from sklearn.ensemble import IsolationForest
import numpy as np
from datetime import datetime
import re
from repository.baseline_repo import repo

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

def detect_revenue_anomaly(daily_revenues: list) -> dict:
    if len(daily_revenues) < 14:
        arr = np.array(daily_revenues)
        # Avoid slicing if only 1 item
        if len(arr) <= 1:
            return {"anomaly": False, "method": "zscore_fallback", "z_score": 0.0}
            
        mean_baseline = np.mean(arr[:-1])
        std_baseline = np.std(arr[:-1])

        if std_baseline == 0:
            return {
                "anomaly": float(daily_revenues[-1]) != float(mean_baseline),
                "method": "zscore_fallback"
            }

        z_score = (arr[-1] - mean_baseline) / std_baseline
        return {
            "anomaly": bool(z_score > 3.0),
            "z_score": round(float(z_score), 2),
            "method": "zscore_fallback"
        }

    arr = np.array(daily_revenues).reshape(-1, 1)
    model = IsolationForest(contamination=0.05, random_state=42)
    model.fit(arr)

    predictions = model.predict(arr)
    scores = model.decision_function(arr)

    latest_anomaly = predictions[-1] == -1

    return {
        "anomaly": bool(latest_anomaly),
        "anomaly_score": round(float(scores[-1]), 3),
        "severity": "HIGH" if scores[-1] < -0.15 else "MEDIUM",
        "method": "isolation_forest"
    }

def check_expense_anomaly(total_revenue: float, total_expenses: float, category: str = "general_trade") -> dict:
    if total_revenue == 0:
        return {"anomaly": False, "reason": "zero_revenue"}

    category = normalise_category(category)

    expense_ratio = total_expenses / total_revenue
    
    # Update the baseline immediately
    repo.update_baseline(category, expense_ratio)
    
    # Get current stats
    b = repo.get_baseline(category)
    mean = b["mean"].get()
    variance = b["var"].get()

    if variance is None or variance == 0:
        return {
            "anomaly": False, 
            "reason": "insufficient_baseline_data",
            "expense_ratio": round(expense_ratio, 3)
        }

    std = variance ** 0.5
    deviation = abs(expense_ratio - mean)
    is_anomaly = deviation > (2 * std)

    flag = "ok"
    if is_anomaly:
        if expense_ratio < mean - (2 * std):
            flag = "revenue_inflation"
        elif expense_ratio > mean + (2 * std):
            flag = "expense_inflation"

    return {
        "anomaly": is_anomaly,
        "expense_ratio": round(expense_ratio, 3),
        "baseline_mean": round(mean, 3),
        "flag": flag
    }

def group_into_sessions(upload_history: list, gap_minutes: int = 10) -> list:
    if not upload_history:
        return []
    
    # Sort by uploaded_at just in case
    sorted_history = sorted(
        upload_history, 
        key=lambda x: datetime.fromisoformat(x.uploaded_at.replace("Z", "+00:00"))
    )
    
    sessions = []
    current_session = [sorted_history[0]]
    
    for record in sorted_history[1:]:
        prev_time = datetime.fromisoformat(current_session[-1].uploaded_at.replace("Z", "+00:00"))
        curr_time = datetime.fromisoformat(record.uploaded_at.replace("Z", "+00:00"))
        
        delta = (curr_time - prev_time).total_seconds() / 60.0
        if delta <= gap_minutes:
            current_session.append(record)
        else:
            sessions.append(current_session)
            current_session = [record]
            
    if current_session:
        sessions.append(current_session)
        
    return sessions

def check_timestamp_integrity(upload_history: list) -> dict:
    flags = []
    sessions = group_into_sessions(upload_history, gap_minutes=10)

    for session in sessions:
        claimed_dates = [r.transaction_date for r in session]
        unique_claimed = set(claimed_dates)

        if len(unique_claimed) > 3:
            flags.append({
                "type": "bulk_backdate",
                "severity": "HIGH",
                "unique_dates_claimed": len(unique_claimed)
            })

        for record in session:
            # Handle possible trailing 'Z' which datetime.fromisoformat doesn't like in python < 3.11 without replace
            claimed = datetime.fromisoformat(record.transaction_date.split('T')[0])
            uploaded = datetime.fromisoformat(record.uploaded_at.replace('Z', '+00:00'))
            
            delta_days = (uploaded.date() - claimed.date()).days

            if delta_days > 7:
                flags.append({
                    "type": "suspicious_backdate",
                    "severity": "MEDIUM" if delta_days < 30 else "HIGH",
                    "days_gap": delta_days,
                    "transaction_date": record.transaction_date,
                    "uploaded_at": record.uploaded_at
                })

    integrity_score = max(0.0, 1.0 - (len(flags) * 0.15))

    return {
        "flags": flags,
        "flag_count": len(flags),
        "integrity_score": round(integrity_score, 2),
        "passed": len(flags) == 0
    }

def compute_penalty_multiplier(spike_result: dict, expense_result: dict, integrity_result: dict) -> float:
    multiplier = 1.0

    if spike_result.get("anomaly") or spike_result.get("spike"):
        multiplier *= 0.50

    if expense_result.get("anomaly"):
        multiplier *= 0.60

    multiplier *= integrity_result["integrity_score"]

    return round(multiplier, 3)
