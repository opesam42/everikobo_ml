from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

# --- Score Models ---

class ScoreRequest(BaseModel):
    trader_id: str
    daily_revenues: List[float]
    total_revenue: float
    total_cogs: float
    total_expenses: float
    consistency_ratio: float
    days_tracked: int

class ScoreSignals(BaseModel):
    volatility_score: float
    trend_score: float
    consistency_score: float
    gross_margin_score: float

class ScoreResponse(BaseModel):
    trader_id: str
    everiscore: Optional[float]
    tier: str
    tax_status: Optional[str]
    annualised_turnover: Optional[float] = None
    eligible: bool
    ineligible_reason: Optional[str] = None
    signals: Optional[ScoreSignals] = None


# --- Fraud Check Models ---

class UploadRecord(BaseModel):
    transaction_date: str
    uploaded_at: str

class FraudCheckRequest(BaseModel):
    trader_id: str
    daily_revenues: List[float]
    total_revenue: float
    total_expenses: float
    trader_category: str = "general_trade"
    upload_history: List[UploadRecord]
    notebook_revenue_daily_avg: Optional[float] = 0.0
    squad_credit_daily_avg: Optional[float] = 0.0
    mono_credit_daily_avg: Optional[float] = 0.0
    days_with_squad_data: Optional[int] = 0
    days_with_mono_data: Optional[int] = 0

class FraudFlag(BaseModel):
    type: str
    severity: str
    anomaly_score: Optional[float] = None
    days_gap: Optional[int] = None
    transaction_date: Optional[str] = None
    uploaded_at: Optional[str] = None
    unique_dates_claimed: Optional[int] = None

class FraudCheckResponse(BaseModel):
    trader_id: str
    fraud_flags: List[FraudFlag]
    expense_anomaly: bool
    expense_flag: str
    flag_count: int
    integrity_score: float
    penalty_multiplier: float

# --- Baseline Models ---

class BaselineState(BaseModel):
    category: str
    mean: float
    variance: float
    count: float

class BaselineDumpResponse(BaseModel):
    baselines: List[BaselineState]


# --- Match Models ---

class JobPost(BaseModel):
    lga: str
    skill_needed: str
    skills_needed: Optional[List[str]] = None
    max_rate: float
    trader_everiscore: float

class Trader(BaseModel):
    id: str
    lga: str

class Seeker(BaseModel):
    id: Optional[str] = None
    lga: str
    skills: List[str]
    daily_rate: float
    available: Optional[bool] = True
    avg_rating: Optional[float] = 0.5
    jobs_completed: Optional[int] = 0

class MatchRequest(BaseModel):
    job_post: JobPost
    trader: Trader
    candidate_pool: List[Seeker]

class RankedCandidate(BaseModel):
    id: Optional[str] = None
    match_score: float
    method: str
    # Keep the rest of the seeker data dynamically, or just specific fields if needed
    lga: str
    skills: List[str]
    daily_rate: float
    available: Optional[bool] = True
    avg_rating: Optional[float] = 0.5
    jobs_completed: Optional[int] = 0

class MatchResponse(BaseModel):
    ranked_candidates: List[RankedCandidate]
    total_candidates: int
    method_used: str

class MatchFeedbackRequest(BaseModel):
    seeker_id: str
    job_post: JobPost
    seeker: Seeker
    outcome: bool

class MatchFeedbackResponse(BaseModel):
    status: str
    total_matches_learned: int
    ml_active: bool
