from services.fraud_service import check_squad_velocity_triangulation

def test_squad_velocity_triangulation_insufficient_history():
    result = check_squad_velocity_triangulation(10000, 5000, 5)
    assert result["checked"] is False
    assert result["reason"] == "insufficient_squad_history"
    assert result["penalty"] == 1.0

def test_squad_velocity_triangulation_zero_notebook():
    result = check_squad_velocity_triangulation(0, 5000, 10)
    assert result["checked"] is False
    assert result["reason"] == "zero_notebook_revenue"
    assert result["penalty"] == 1.0

def test_squad_velocity_triangulation_high_deviation():
    # 20000 notebook, 2000 squad -> 90% deviation
    result = check_squad_velocity_triangulation(20000, 2000, 10)
    assert result["checked"] is True
    assert result["anomaly"] is True
    assert result["severity"] == "HIGH"
    assert result["penalty"] == 0.70
    assert result["deviation"] == 0.90

def test_squad_velocity_triangulation_medium_deviation():
    # 20000 notebook, 4000 squad -> 80% deviation
    result = check_squad_velocity_triangulation(20000, 4000, 10)
    assert result["checked"] is True
    assert result["anomaly"] is True
    assert result["severity"] == "MEDIUM"
    assert result["penalty"] == 0.85
    assert result["deviation"] == 0.80

def test_squad_velocity_triangulation_no_anomaly():
    # 20000 notebook, 10000 squad -> 50% deviation (acceptable)
    result = check_squad_velocity_triangulation(20000, 10000, 10)
    assert result["checked"] is True
    assert result["anomaly"] is False
    assert result["penalty"] == 1.0
    assert result["deviation"] == 0.50
