from river import stats

class BaselineRepository:
    def __init__(self):
        # In-memory store for running statistics
        self.category_baselines = {}
        
    def _init_category(self, category: str):
        if category not in self.category_baselines:
            self.category_baselines[category] = {
                "mean": stats.Mean(),
                "var": stats.Var()
            }
            
    def get_baseline(self, category: str):
        self._init_category(category)
        return self.category_baselines[category]
        
    def update_baseline(self, category: str, expense_ratio: float):
        self._init_category(category)
        b = self.category_baselines[category]
        b["mean"].update(expense_ratio)
        b["var"].update(expense_ratio)

    def dump_state(self) -> list:
        """
        Dumps the current state so Node.js can save it to PostgreSQL.
        """
        state = []
        for cat, b in self.category_baselines.items():
            mean_val = b["mean"].get()
            var_val = b["var"].get()
            # River's stats.Mean typically has an 'n' property
            n_val = getattr(b["mean"], 'n', 0.0)
            
            state.append({
                "category": cat,
                "mean": mean_val if mean_val is not None else 0.0,
                "variance": var_val if var_val is not None else 0.0,
                "count": n_val
            })
        return state

    def restore_state(self, state_list: list):
        """
        Restores state from a Node.js payload on startup.
        Note: Exact restoration of River Variance requires internal attributes.
        """
        self.category_baselines.clear()
        for s in state_list:
            cat = s["category"]
            self._init_category(cat)
            b = self.category_baselines[cat]
            
            count = s.get("count", 0.0)
            mean_val = s.get("mean", 0.0)
            var_val = s.get("variance", 0.0)
            
            # Manually inject state back into River objects
            b["mean"].n = count
            b["mean"].mean = mean_val
            
            # Variance uses a running sum of squares
            b["var"].mean.n = count
            b["var"].mean.mean = mean_val
            if count > 1:
                # Reconstruct sum of squares from variance
                # Sample variance = SOS / (n - 1) => SOS = var * (n - 1)
                b["var"].sum_of_squares = var_val * (count - 1)
            else:
                b["var"].sum_of_squares = 0.0

# Singleton instance for the app to use
repo = BaselineRepository()
