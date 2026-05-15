from services.fraud_service import check_velocity_triangulation

def test_velocity_triangulation_insufficient_history():
    result = check_velocity_triangulation(10000, 5000, 0, 5, 0)
    assert result["checked"] is False
    assert result["reason"] == "insufficient_digital_history"
    assert result["penalty"] == 1.0

def test_velocity_triangulation_zero_notebook():
    result = check_velocity_triangulation(0, 5000, 0, 10, 0)
    assert result["checked"] is False
    assert result["reason"] == "zero_notebook_revenue"
    assert result["penalty"] == 1.0

def test_velocity_triangulation_high_deviation():
    # 20000 notebook, 2000 squad, 0 mono -> 90% deviation
    result = check_velocity_triangulation(20000, 2000, 0, 10, 0)
    assert result["checked"] is True
    assert result["anomaly"] is True
    assert result["severity"] == "HIGH"
    assert result["penalty"] == 0.70
    assert result["deviation"] == 0.90

def test_velocity_triangulation_medium_deviation():
    # 20000 notebook, 4000 squad, 0 mono -> 80% deviation
    result = check_velocity_triangulation(20000, 4000, 0, 10, 0)
    assert result["checked"] is True
    assert result["anomaly"] is True
    assert result["severity"] == "MEDIUM"
    assert result["penalty"] == 0.85
    assert result["deviation"] == 0.80

def test_velocity_triangulation_no_anomaly():
    # 20000 notebook, 10000 squad, 0 mono -> 50% deviation (acceptable)
    result = check_velocity_triangulation(20000, 10000, 0, 10, 0)
    assert result["checked"] is True
    assert result["anomaly"] is False
    assert result["penalty"] == 1.0
    assert result["deviation"] == 0.50

def test_velocity_triangulation_combined_squad_and_mono():
    # 20000 notebook, 1000 squad, 3000 mono -> Total Digital = 4000
    # Deviation = (20000 - 4000) / 20000 = 0.80 (Medium anomaly)
    result = check_velocity_triangulation(20000, 1000, 3000, 10, 8)
    assert result["checked"] is True
    assert result["anomaly"] is True
    assert result["severity"] == "MEDIUM"
    assert result["penalty"] == 0.85
    assert result["deviation"] == 0.80
    assert result["combined_digital_avg"] == 4000
    assert result["sources_used"]["squad"] is True
    assert result["sources_used"]["mono"] is True
