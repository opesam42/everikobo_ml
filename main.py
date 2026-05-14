from fastapi import FastAPI, HTTPException, Depends
from auth.api_key import verify_api_key
from fastapi.middleware.cors import CORSMiddleware
from typing import List

from models import (
    ScoreRequest, ScoreResponse,
    FraudCheckRequest, FraudCheckResponse, FraudFlag,
    BaselineState, BaselineDumpResponse,
    MatchRequest, MatchResponse, MatchFeedbackRequest, MatchFeedbackResponse
)
from services import score_service, fraud_service, match_service
from repository.baseline_repo import repo

app = FastAPI(
    title="EveriKobo ML Microservice",
    description="Handles AI and ML operations for the EveriKobo platform.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/score", response_model=ScoreResponse, dependencies=[Depends(verify_api_key)])
def compute_score(request: ScoreRequest):
    result = score_service.compute_everiscore(
        trader_id=request.trader_id,
        daily_revenues=request.daily_revenues,
        total_revenue=request.total_revenue,
        total_cogs=request.total_cogs,
        total_expenses=request.total_expenses,
        consistency_ratio=request.consistency_ratio,
        days_tracked=request.days_tracked
    )
    return ScoreResponse(**result)

@app.post("/fraud-check", response_model=FraudCheckResponse, dependencies=[Depends(verify_api_key)])
def check_fraud(request: FraudCheckRequest):
    # 1. Revenue Spike Detection
    spike_result = fraud_service.detect_revenue_anomaly(request.daily_revenues)
    
    # 2. Expense Ratio Anomaly
    expense_result = fraud_service.check_expense_anomaly(
        total_revenue=request.total_revenue,
        total_expenses=request.total_expenses,
        category=request.trader_category
    )
    
    # 3. Timestamp Integrity
    integrity_result = fraud_service.check_timestamp_integrity(request.upload_history)
    
    # Compute Final Multiplier
    multiplier = fraud_service.compute_penalty_multiplier(
        spike_result=spike_result,
        expense_result=expense_result,
        integrity_result=integrity_result
    )
    
    # Assemble Fraud Flags
    flags = []
    if spike_result.get("anomaly"):
        flags.append({
            "type": "revenue_spike",
            "severity": spike_result.get("severity", "HIGH"),
            "anomaly_score": spike_result.get("anomaly_score")
        })
        
    for f in integrity_result.get("flags", []):
        flags.append(f)
        
    return FraudCheckResponse(
        trader_id=request.trader_id,
        fraud_flags=[FraudFlag(**f) for f in flags],
        expense_anomaly=expense_result.get("anomaly", False),
        expense_flag=expense_result.get("flag", "ok"),
        flag_count=len(flags) + (1 if expense_result.get("anomaly") else 0),
        integrity_score=integrity_result.get("integrity_score", 1.0),
        penalty_multiplier=multiplier
    )

@app.get("/baselines", response_model=BaselineDumpResponse, dependencies=[Depends(verify_api_key)])
def get_baselines():
    """Returns the serialized state of River baselines for PostgreSQL persistence."""
    return {"baselines": repo.dump_state()}

@app.post("/baselines", response_model=dict, dependencies=[Depends(verify_api_key)])
def restore_baselines(request: BaselineDumpResponse):
    """Restores River baselines from Node.js on startup."""
    state_list = [s.model_dump() for s in request.baselines]
    repo.restore_state(state_list)
    return {"status": "ok", "message": "Baselines restored successfully."}

@app.post("/match", response_model=MatchResponse, dependencies=[Depends(verify_api_key)])
def match_candidates(request: MatchRequest):
    result = match_service.rank_candidates(
        job_post=request.job_post,
        candidate_pool=request.candidate_pool,
        trader_id=request.trader.id
    )
    return MatchResponse(**result)

@app.post("/match/feedback", response_model=MatchFeedbackResponse, dependencies=[Depends(verify_api_key)])
def match_feedback(request: MatchFeedbackRequest):
    result = match_service.record_match_outcome(
        seeker=request.seeker,
        job_post=request.job_post,
        outcome=request.outcome
    )
    return MatchFeedbackResponse(**result)
