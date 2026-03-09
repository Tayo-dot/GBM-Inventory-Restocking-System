# app/predictor.py

import joblib
import pandas as pd
from xgboost import XGBRegressor

from app.restock import calculate_restock


class RestockPredictor:
    def __init__(
        self,
        model_path: str = "models/xgb_restock_model.json",
        features_path: str = "models/model_features.pkl",
    ):
        self.model = XGBRegressor()
        self.model.load_model(model_path)
        self.features = joblib.load(features_path)

    def predict_and_restock(self, payload: dict) -> dict:
        """
        payload: dict containing at least all columns in self.features

        Returns:
          predicted_demand, restock_needed, restock_quantity, reorder_point, target_stock
        """

        # Build a one-row dataframe
        row = pd.DataFrame([payload])

        # Ensure all required columns exist
        missing = [c for c in self.features if c not in row.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        # Reorder columns to match training
        X_input = row[self.features]

        # Predict demand
        predicted = float(self.model.predict(X_input)[0])

        # Use inventory_level for restock logic
        inv = float(payload.get("inventory_level", 0))

        restock_info = calculate_restock(
            predicted_demand=predicted,
            inventory_level=inv,
            safety_factor=0.15,
            reorder_threshold=0.7
        )

        return {
            "predicted_demand": predicted,
            **restock_info
        }


# Quick test (optional): run `python -m app.predictor`
if __name__ == "__main__":
    predictor = RestockPredictor()

    # Example payload: fill with REAL values from your dataset schema
    example = {feature: 0 for feature in predictor.features}
    example["inventory_level"] = 120

    result = predictor.predict_and_restock(example)
    print(result)

    if __name__ == "__main__":
        predictor = RestockPredictor()

    # Create dummy input using expected features
    example = {feature: 0 for feature in predictor.features}
    example["inventory_level"] = 120

    result = predictor.predict_and_restock(example)

    print("System Output:")
    print(result)