from river import linear_model, preprocessing, compose
from collections import defaultdict
from models import JobPost, Seeker, RankedCandidate

# Online learning pipeline — updates incrementally with each outcome
match_model = compose.Pipeline(
    preprocessing.StandardScaler(),
    linear_model.LogisticRegression()
)
total_matches_learned = 0

def apply_hard_filters(job_post: JobPost, seekers: list[Seeker]) -> list[Seeker]:
    return [
        s for s in seekers
        if s.lga == job_post.lga
        and job_post.skill_needed in s.skills
        and (s.available is True or s.available is None)
        and s.daily_rate <= job_post.max_rate
    ]

def extract_match_features(seeker: Seeker, job_post: JobPost) -> dict:
    required = set(job_post.skills_needed) if job_post.skills_needed else {job_post.skill_needed}
    seeker_s = set(seeker.skills)
    return {
        "skill_overlap_ratio":    len(required & seeker_s) / max(len(required), 1),
        "rate_compatibility":     1.0 - abs(seeker.daily_rate - job_post.max_rate) / max(job_post.max_rate, 1),
        "seeker_avg_rating":      seeker.avg_rating or 0.5,
        "seeker_jobs_completed":  min((seeker.jobs_completed or 0) / 50, 1.0),
        "trader_everiscore":      job_post.trader_everiscore,
    }

def score_candidate_rules(seeker: Seeker, job_post: JobPost) -> float:
    f = extract_match_features(seeker, job_post)
    return round(
        f["skill_overlap_ratio"]   * 0.50 +
        f["rate_compatibility"]    * 0.15 +
        f["seeker_avg_rating"]     * 0.20 +
        f["seeker_jobs_completed"] * 0.15,
        4
    )

def rank_candidates(job_post: JobPost, candidate_pool: list[Seeker], trader_id: str) -> dict:
    eligible = apply_hard_filters(job_post, candidate_pool)

    if not eligible:
        return {"ranked_candidates": [], "total_candidates": 0, "method_used": "no_candidates"}

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

        # Convert the Pydantic model to a dict, then unpack
        seeker_dict = seeker.model_dump()
        scored.append(RankedCandidate(
            **seeker_dict,
            match_score=round(final, 4),
            method=method
        ))

    ranked = sorted(scored, key=lambda x: x.match_score, reverse=True)

    return {
        "ranked_candidates": ranked,
        "total_candidates":  len(ranked),
        "method_used":       "ml_blend" if use_ml else "rules_only"
    }

def record_match_outcome(seeker: Seeker, job_post: JobPost, outcome: bool) -> dict:
    """ Feed a completed match outcome back into the River model so rankings improve over time """
    global total_matches_learned

    features = extract_match_features(seeker, job_post)
    match_model.learn_one(features, outcome)
    total_matches_learned += 1

    return {
        "status":               "learned",
        "total_matches_learned": total_matches_learned,
        "ml_active":            total_matches_learned >= 50
    }
