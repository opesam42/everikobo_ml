from fastapi.testclient import TestClient
from main import app
from auth.api_key import verify_api_key

client = TestClient(app)

# Override the API key dependency so tests always pass regardless of the .env file
app.dependency_overrides[verify_api_key] = lambda: "test_key"

def test_match_endpoint():
    payload = {
        "job_post": {
            "lga": "Kosofe",
            "skill_needed": "delivery",
            "skills_needed": ["delivery", "logistics"],
            "max_rate": 3500,
            "trader_everiscore": 0.73
        },
        "trader": {
            "id": "uuid-string",
            "lga": "Kosofe"
        },
        "candidate_pool": [
            {
                "id": "uuid-string-1",
                "lga": "Kosofe",
                "skills": ["delivery", "inventory"],
                "daily_rate": 3000,
                "available": True,
                "avg_rating": 0.85,
                "jobs_completed": 12
            }
        ]
    }
    response = client.post("/match", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["total_candidates"] == 1
    assert data["ranked_candidates"][0]["id"] == "uuid-string-1"
    assert "match_score" in data["ranked_candidates"][0]
    assert data["method_used"] in ["rules_only", "ml_blend"]

def test_match_feedback_endpoint():
    payload = {
        "seeker_id": "uuid-string-1",
        "job_post": {
            "lga": "Kosofe",
            "skill_needed": "delivery",
            "max_rate": 3500,
            "trader_everiscore": 0.73
        },
        "seeker": {
            "lga": "Kosofe",
            "skills": ["delivery"],
            "daily_rate": 3000
        },
        "outcome": True
    }
    response = client.post("/match/feedback", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "learned"
    assert "total_matches_learned" in data
    assert "ml_active" in data
