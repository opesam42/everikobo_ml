from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_score_endpoint_ineligible():
    payload = {
        "trader_id": "T123",
        "daily_revenues": [100] * 10,
        "total_revenue": 1000,
        "total_cogs": 300,
        "total_expenses": 100,
        "consistency_ratio": 0.8,
        "days_tracked": 10
    }
    response = client.post("/score", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["eligible"] is False
    assert data["tier"] == "INELIGIBLE"
    assert data["everiscore"] is None

def test_score_endpoint_eligible():
    payload = {
        "trader_id": "T124",
        "daily_revenues": [150] * 30,
        "total_revenue": 4500,
        "total_cogs": 2000,
        "total_expenses": 500,
        "consistency_ratio": 0.9,
        "days_tracked": 30
    }
    response = client.post("/score", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["eligible"] is True
    assert data["tier"] in ["GREEN", "YELLOW", "RED"]
    assert data["everiscore"] is not None
    assert "signals" in data
    assert data["signals"]["gross_margin_score"] == 0.5556
