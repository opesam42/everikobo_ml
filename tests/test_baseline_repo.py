from repository.baseline_repo import BaselineRepository
import pytest

def test_baseline_repo_update_and_drift():
    repo = BaselineRepository()
    category = "test_cat"
    
    # Simulate a stable market environment with expense ratio around 0.4
    for _ in range(30):
        repo.update_baseline(category, 0.4)
        
    b = repo.get_baseline(category)
    assert 0.39 < b["mean"].get() < 0.41
    
    # Simulate a massive drift (expense inflation to 0.8)
    # ADWIN should eventually catch this and reset
    drift_detected = False
    for _ in range(100):
        # We patch print temporarily to detect if the drift message is printed
        # But an easier way is to just observe the mean drop significantly towards the new value quickly
        # because alpha=0.1. However, if ADWIN resets, it starts fresh.
        repo.update_baseline(category, 0.8)
        
    b = repo.get_baseline(category)
    # Because of EWMean or reset, the mean should now be extremely close to 0.8
    assert b["mean"].get() > 0.75

def test_dump_and_restore_state():
    repo = BaselineRepository()
    category = "dump_test_cat"
    
    for _ in range(10):
        repo.update_baseline(category, 0.5)
        
    dumped = repo.dump_state()
    assert len(dumped) == 1
    assert dumped[0]["category"] == category
    assert "mean" in dumped[0]
    assert "variance" in dumped[0]
    
    # Create a new repo and restore
    new_repo = BaselineRepository()
    new_repo.restore_state(dumped)
    
    restored_b = new_repo.get_baseline(category)
    assert restored_b["mean"].get() == dumped[0]["mean"]
    
    # It should still be able to update cleanly after restore
    new_repo.update_baseline(category, 0.6)
    updated_b = new_repo.get_baseline(category)
    assert updated_b["mean"].get() != dumped[0]["mean"]
