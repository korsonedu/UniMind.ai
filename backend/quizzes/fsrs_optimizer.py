import numpy as np
from scipy.optimize import minimize
import math

class FSRSOptimizer:
    def __init__(self, review_data, current_weights=None):
        self.data = review_data
        # Default FSRS v4.5 weights
        self.weights = current_weights or [
            0.4, 0.6, 2.4, 5.8,
            4.93, 0.94, 0.86, 0.01,
            1.49, 0.14, 0.94,
            2.18, 0.05, 0.34, 1.26, 0.29, 2.61
        ]

    def _simulate_history(self, weights, card_history):
        predictions = []
        stability = 0.0
        difficulty = 0.0
        for i, log in enumerate(card_history):
            grade = log['grade']
            elapsed_days = log['elapsed_days']
            
            if i == 0:
                predictions.append(0.0)
                stability = weights[grade - 1]
                difficulty = weights[4] - (grade - 3) * weights[5]
                difficulty = max(1, min(10, difficulty))
            else:
                # Retrievability prediction before current review
                r = math.pow(1 + 19/81 * elapsed_days / stability, -0.5)
                predictions.append(r)
                
                # Update difficulty
                difficulty -= weights[6] * (grade - 3)
                difficulty = weights[7] * weights[4] + (1 - weights[7]) * difficulty
                difficulty = max(1, min(10, difficulty))
                
                # Update stability based on actual grade
                if grade == 1:
                    stability = weights[11] * math.pow(difficulty, -weights[12]) * (math.pow(stability + 1, weights[13]) - 1) * math.exp(weights[14] * (1 - r))
                else:
                    s_inc = math.exp(weights[8]) * (11 - difficulty) * math.pow(stability, -weights[9]) * (math.exp(weights[10] * (1 - r)) - 1)
                    if grade == 2:
                        stability = stability * (1 + s_inc * weights[15])
                    elif grade == 3:
                        stability = stability * (1 + s_inc)
                    elif grade == 4:
                        stability = stability * (1 + s_inc * weights[16])
        return predictions

    def loss_function(self, weights):
        loss = 0.0
        count = 0
        for card_history in self.data:
            try:
                predictions = self._simulate_history(weights, card_history)
                for i, log in enumerate(card_history):
                    if i == 0: continue
                    actual_r = 1.0 if log['grade'] > 1 else 0.0
                    pred_r = predictions[i]
                    loss += (actual_r - pred_r) ** 2
                    count += 1
            except OverflowError:
                return float('inf')
        return np.sqrt(loss / count) if count > 0 else float('inf')

    def optimize(self):
        bounds = [(0.01, 10.0)] * len(self.weights)
        res = minimize(
            self.loss_function, 
            x0=self.weights, 
            method='L-BFGS-B', 
            bounds=bounds
        )
        if res.success:
            return res.x.tolist(), res.fun
        return None, None

if __name__ == "__main__":
    # Task 2.1: Dummy test to verify RMSE offline tuning
    dummy_data = [
        [
            {"grade": 3, "elapsed_days": 0},
            {"grade": 2, "elapsed_days": 1},
            {"grade": 3, "elapsed_days": 3},
            {"grade": 1, "elapsed_days": 7}
        ],
        [
            {"grade": 1, "elapsed_days": 0},
            {"grade": 3, "elapsed_days": 0.5},
            {"grade": 4, "elapsed_days": 2}
        ]
    ]
    optimizer = FSRSOptimizer(dummy_data)
    print("FSRS Optimizer Initialized.")
    print("Initial RMSE Loss:", optimizer.loss_function(optimizer.weights))
    
    new_w, new_loss = optimizer.optimize()
    if new_w:
        print("Optimization successful!")
        print("New RMSE Loss:", new_loss)
        print(f"Optimized Weights (first 5): {[round(w, 4) for w in new_w[:5]]}")
    else:
        print("Optimization failed.")
