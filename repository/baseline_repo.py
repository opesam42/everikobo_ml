from river import stats, drift

class BaselineRepository:
    def __init__(self):
        # In-memory store for running statistics
        self.category_baselines = {}
        
    def _init_category(self, category: str):
        if category not in self.category_baselines:
            self.category_baselines[category] = {
                "mean": stats.EWMean(fading_factor=0.1),
                "var": stats.EWVar(fading_factor=0.1),
                "detector": drift.ADWIN()
            }
            
    def get_baseline(self, category: str):
        self._init_category(category)
        return self.category_baselines[category]
        
    def update_baseline(self, category: str, expense_ratio: float):
        self._init_category(category)
        b = self.category_baselines[category]
        
        b["mean"].update(expense_ratio)
        b["var"].update(expense_ratio)

        # Check for market drift
        detector = b["detector"]
        detector.update(expense_ratio)
        if detector.drift_detected:
            print(f"Market drift detected in {category} — resetting baseline")
            # Reset the baseline because market conditions have fundamentally changed
            self.category_baselines[category] = {
                "mean": stats.EWMean(fading_factor=0.1),
                "var": stats.EWVar(fading_factor=0.1),
                "detector": drift.ADWIN()
            }

    def dump_state(self) -> list:
        """
        Dumps the current state so Node.js can save it to PostgreSQL.
        """
        state = []
        for cat, b in self.category_baselines.items():
            mean_val = b["mean"].get()
            var_val = b["var"].get()
            
            state.append({
                "category": cat,
                "mean": mean_val if mean_val is not None else 0.0,
                "variance": var_val if var_val is not None else 0.0,
                "count": 0.0  # Count is irrelevant for EW stats, kept for schema compatibility
            })
        return state

    def restore_state(self, state_list: list):
        """
        Restores state from a Node.js payload on startup.
        """
        self.category_baselines.clear()
        for s in state_list:
            cat = s["category"]
            self._init_category(cat)
            b = self.category_baselines[cat]
            
            mean_val = s.get("mean", 0.0)
            
            # Re-initialize to clear any existing state
            b["mean"] = stats.EWMean(fading_factor=0.1)
            b["var"] = stats.EWVar(fading_factor=0.1)
            
            # The first update to an EW stat sets its initial value exactly.
            # We use the public API instead of reflection since River internals vary.
            b["mean"].update(mean_val)
            b["var"].update(mean_val)

# Singleton instance for the app to use
repo = BaselineRepository()
