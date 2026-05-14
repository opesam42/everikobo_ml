from models import JobPost, Seeker, Trader
from services.match_service import (
    apply_hard_filters,
    extract_match_features,
    score_candidate_rules,
    rank_candidates,
    record_match_outcome,
)

def test_apply_hard_filters():
    job_post = JobPost(lga="Kosofe", skill_needed="delivery", skills_needed=["delivery"], max_rate=3500, trader_everiscore=0.7)
    seekers = [
        Seeker(id="1", lga="Kosofe", skills=["delivery"], daily_rate=3000, available=True),
        Seeker(id="2", lga="Ikeja", skills=["delivery"], daily_rate=3000, available=True),  # Wrong LGA
        Seeker(id="3", lga="Kosofe", skills=["plumbing"], daily_rate=3000, available=True), # Wrong Skill
        Seeker(id="4", lga="Kosofe", skills=["delivery"], daily_rate=4000, available=True), # Too Expensive
        Seeker(id="5", lga="Kosofe", skills=["delivery"], daily_rate=3000, available=False),# Not Available
    ]
    
    filtered = apply_hard_filters(job_post, seekers)
    assert len(filtered) == 1
    assert filtered[0].id == "1"

def test_extract_match_features():
    job_post = JobPost(lga="Kosofe", skill_needed="delivery", skills_needed=["delivery", "inventory"], max_rate=4000, trader_everiscore=0.8)
    seeker = Seeker(id="1", lga="Kosofe", skills=["delivery"], daily_rate=3000, avg_rating=0.9, jobs_completed=25)
    
    features = extract_match_features(seeker, job_post)
    # 1 overlap out of 2 needed = 0.5
    assert features["skill_overlap_ratio"] == 0.5
    # 1.0 - (1000 / 4000) = 0.75
    assert features["rate_compatibility"] == 0.75
    assert features["seeker_avg_rating"] == 0.9
    assert features["seeker_jobs_completed"] == 0.5 # 25 / 50
    assert features["trader_everiscore"] == 0.8

def test_score_candidate_rules():
    job_post = JobPost(lga="Kosofe", skill_needed="delivery", skills_needed=["delivery"], max_rate=4000, trader_everiscore=0.8)
    seeker = Seeker(id="1", lga="Kosofe", skills=["delivery"], daily_rate=4000, avg_rating=1.0, jobs_completed=50)
    
    # Overlap = 1.0, Rate = 1.0, Rating = 1.0, Jobs = 1.0
    # Expected score = 0.50 + 0.15 + 0.20 + 0.15 = 1.0
    score = score_candidate_rules(seeker, job_post)
    assert score == 1.0

def test_rank_candidates():
    job_post = JobPost(lga="Kosofe", skill_needed="delivery", skills_needed=["delivery"], max_rate=4000, trader_everiscore=0.8)
    trader = Trader(id="T1", lga="Kosofe")
    seekers = [
        Seeker(id="1", lga="Kosofe", skills=["delivery"], daily_rate=3000, avg_rating=0.9, jobs_completed=10),
        Seeker(id="2", lga="Kosofe", skills=["delivery"], daily_rate=4000, avg_rating=1.0, jobs_completed=50),
    ]
    
    result = rank_candidates(job_post, seekers, trader.id)
    assert result["total_candidates"] == 2
    # Seeker 2 should score higher because rating and jobs completed are maxed out, despite same skill overlap and rate compatibility
    assert result["ranked_candidates"][0].id == "2"
    assert result["method_used"] in ["rules_only", "ml_blend"]

def test_record_match_outcome():
    job_post = JobPost(lga="Kosofe", skill_needed="delivery", skills_needed=["delivery"], max_rate=4000, trader_everiscore=0.8)
    seeker = Seeker(id="1", lga="Kosofe", skills=["delivery"], daily_rate=3000, avg_rating=0.9, jobs_completed=10)
    
    result = record_match_outcome(seeker, job_post, True)
    assert result["status"] == "learned"
    assert result["total_matches_learned"] >= 1
    # Note: ML active becomes true when total >= 50
    assert "ml_active" in result
