# ai/predictor.py — AI prediction engine (ensemble of models)

import pickle
import os
import numpy as np
import pandas as pd

from ai.features import engineer_features, get_feature_names
import config


class FootballPredictor:
    """
    Ensemble AI predictor combining:
    - Logistic Regression (well-calibrated probabilities)
    - Random Forest (captures non-linear interactions)
    - XGBoost (gradient boosting for accuracy)
    
    Final probability = weighted average of all three models.
    """

    def __init__(self):
        self.models = {}
        self.feature_names = get_feature_names()
        self._models_loaded = False
        self._trainer = None

    def _ensure_models(self):
        """Lazy-load models on first use."""
        if self._models_loaded:
            return
        # First call: start background trainer, return immediately
        # so gunicorn worker can respond to health checks
        import threading
        self._trainer = threading.Thread(target=self._bg_train, daemon=True)
        self._trainer.start()
        self._models_loaded = True

    def _bg_train(self):
        """Background thread: build & cache models, then set flag."""
        import time
        time.sleep(2)  # small grace period for gunicorn to start
        self._load_or_build_models()
        self._models_loaded = True
        print("[Predictor] Background training complete.")

    def _load_or_build_models(self):
        """Load pickled models if available, otherwise build & save them."""
        model_path = os.path.join(os.path.dirname(__file__), "models.pkl")

        if os.path.exists(model_path):
            try:
                with open(model_path, "rb") as f:
                    self.models = pickle.load(f)
                print("[Predictor] Models loaded from disk.")
                return
            except Exception:
                print("[Predictor] Failed to load models, rebuilding...")

        self._build_models()
        self._save_models(model_path)

    def _build_models(self):
        """Build and train ensemble models from synthetic historical data."""
        from sklearn.linear_model import LogisticRegression
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.calibration import CalibratedClassifierCV

        print("[Predictor] Generating synthetic training data...")
        X, y = self._generate_training_data(n_samples=20000)

        # Split
        from sklearn.model_selection import train_test_split
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

        # Model 1: Logistic Regression (calibrated, good for probabilities)
        lr = LogisticRegression(max_iter=1000, solver='lbfgs', random_state=42)
        lr.fit(X_train, y_train)
        self.models["lr"] = lr

        # Model 2: Random Forest
        rf = RandomForestClassifier(n_estimators=100, max_depth=8, random_state=42)
        rf.fit(X_train, y_train)
        self.models["rf"] = rf

        # Model 3: XGBoost (calibrated)
        try:
            from xgboost import XGBClassifier
            xgb = XGBClassifier(
                n_estimators=100, max_depth=6,
                learning_rate=0.1, random_state=42,
                use_label_encoder=False, eval_metric="mlogloss"
            )
            xgb.fit(X_train, y_train)
            self.models["xgb"] = xgb
        except ImportError:
            print("[Predictor] XGBoost not available, using RF only.")
            self.models["xgb"] = rf  # fallback

        # Accuracy report
        from sklearn.metrics import accuracy_score
        for name, model in self.models.items():
            pred = model.predict(X_test)
            acc = accuracy_score(y_test, pred)
            print(f"[Predictor] {name} accuracy: {acc:.3f}")

    def _generate_training_data(self, n_samples=20000) -> tuple:
        """
        Generate synthetic historical match data for training.
        Uses a Poisson goal model with realistic home advantage (~0.25 goals)
        and team-strength-based goal expectations.

        Returns: X (DataFrame), y (numpy array: 0=home, 1=draw, 2=away)
        """
        import numpy as np
        import pandas as pd
        rng = np.random.default_rng(seed=42)

        records = []
        for _ in range(n_samples):
            # Team strength (0=weak, 1=strong) — biased around average
            home_strength = rng.beta(5, 5)
            away_strength = rng.beta(5, 5)

            # Form — correlated with team strength
            home_form_base = home_strength + rng.normal(0, 0.15)
            away_form_base = away_strength + rng.normal(0, 0.15)
            home_form_base = np.clip(home_form_base, 0, 1)
            away_form_base = np.clip(away_form_base, 0, 1)

            # Base goal expectation (Poisson lambda)
            # Home advantage ~+0.25 goals historically
            base_home_goals = 1.35 + home_strength * 0.7 - away_strength * 0.3
            base_away_goals = 1.05 + away_strength * 0.6 - home_strength * 0.25

            home_goals = rng.poisson(max(0.1, base_home_goals))
            away_goals = rng.poisson(max(0.1, base_away_goals))

            if home_goals > away_goals:
                outcome = 0
            elif home_goals < away_goals:
                outcome = 2
            else:
                outcome = 1

            # H2H: correlated with outcome
            h2h_home_rate = 0.30 + (home_strength - away_strength) * 0.15 + rng.normal(0, 0.05)
            h2h_draw_rate = 0.28 + rng.normal(0, 0.04)
            h2h_away_rate = 1 - h2h_home_rate - h2h_draw_rate
            h2h_home_rate = np.clip(h2h_home_rate, 0.1, 0.7)
            h2h_draw_rate = np.clip(h2h_draw_rate, 0.1, 0.5)
            h2h_away_rate = max(0.05, 1 - h2h_home_rate - h2h_draw_rate)

            # League positions (inverse of strength)
            home_pos = int(np.clip(round(20 - home_strength * 18 + rng.normal(0, 2)), 1, 20))
            away_pos = int(np.clip(round(20 - away_strength * 18 + rng.normal(0, 2)), 1, 20))

            records.append({
                "home_form_score": home_form_base,
                "away_form_score": away_form_base,
                "form_diff": home_form_base - away_form_base,
                "home_goals_scored_avg": max(0.3, home_strength * 1.8 + 0.5),
                "away_goals_scored_avg": max(0.3, away_strength * 1.6 + 0.4),
                "home_goals_conceded_avg": max(0.3, (1 - home_strength) * 1.5 + 0.4),
                "away_goals_conceded_avg": max(0.3, (1 - away_strength) * 1.5 + 0.4),
                "home_attack_strength": (home_strength * 1.4 + (1 - away_strength) * 0.6),
                "away_attack_strength": (away_strength * 1.3 + (1 - home_strength) * 0.5),
                "home_defense_strength": (home_strength * 0.8 + 0.6),
                "away_defense_strength": (away_strength * 0.8 + 0.6),
                "expected_goals": home_goals + away_goals,
                "h2h_home_win_rate": h2h_home_rate,
                "h2h_draw_rate": h2h_draw_rate,
                "h2h_away_win_rate": h2h_away_rate,
                "home_league_pos": home_pos,
                "away_league_pos": away_pos,
                "league_pos_diff": home_pos - away_pos,
                "home_advantage": 1,
                "data_freshness": 1.0,
                "outcome": outcome,
            })

        df = pd.DataFrame(records)
        X = df[["home_form_score", "away_form_score", "form_diff",
                "home_goals_scored_avg", "away_goals_scored_avg",
                "home_goals_conceded_avg", "away_goals_conceded_avg",
                "home_attack_strength", "away_attack_strength",
                "home_defense_strength", "away_defense_strength",
                "expected_goals",
                "h2h_home_win_rate", "h2h_draw_rate", "h2h_away_win_rate",
                "home_league_pos", "away_league_pos", "league_pos_diff",
                "home_advantage", "data_freshness"]]
        y = df["outcome"].values
        return X, y

    def _save_models(self, path: str):
        """Save trained models to disk."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self.models, f)
        print(f"[Predictor] Models saved to {path}")

    def predict(self, match_data: dict) -> dict:
        """Generate prediction for a single match."""
        self._ensure_models()
              - home_prob, draw_prob, away_prob (floats summing to 1)
              - confidence: highest probability (0-100)
              - over_25_prob, under_25_prob
              - btts_yes_prob, btts_no_prob
              - model_version
        """
        # Engineer features
        features = engineer_features(match_data)

        # Align column order
        features = features[self.feature_names]

        # Ensemble prediction (weighted average of probabilities)
        probs_sum = np.zeros(3)
        weights = {"lr": 0.30, "rf": 0.35, "xgb": 0.35}

        for name, weight in weights.items():
            if name in self.models:
                model = self.models[name]
                try:
                    p = model.predict_proba(features)[0]
                    probs_sum += weight * p
                except Exception as e:
                    print(f"[Predictor] {name} failed: {e}")

        # Normalize
        probs = probs_sum / probs_sum.sum()

        home_prob, draw_prob, away_prob = probs
        confidence = int(max(probs) * 100)

        if probs.argmax() == 0:
            prediction = "home"
        elif probs.argmax() == 1:
            prediction = "draw"
        else:
            prediction = "away"

        # ── Secondary predictions (Over/Under 2.5, BTTS) ──────────────────
        expected_goals = match_data.get("expected_goals", features["expected_goals"].values[0])
        # Poisson-based O/U
        import math
        over_25_prob = sum([math.exp(-expected_goals) * expected_goals**k / math.factorial(k)
                            for k in range(3)])  # P(X>=3) for over 2.5
        over_25_prob = min(over_25_prob, 0.95)
        under_25_prob = 1 - over_25_prob

        # BTTS (both teams to score) — rough estimate from attack/defense
        home_att = match_data.get("home_goals_scored_avg", features["home_goals_scored_avg"].values[0])
        away_att = match_data.get("away_goals_scored_avg", features["away_goals_scored_avg"].values[0])
        home_def = match_data.get("home_goals_conceded_avg", features["home_goals_conceded_avg"].values[0])
        away_def = match_data.get("away_goals_conceded_avg", features["away_goals_conceded_avg"].values[0])
        btts_yes_prob = min((home_att * away_def / 1.8) * (away_att * home_def / 1.8) * 0.5, 0.95)
        btts_no_prob = 1 - btts_yes_prob

        return {
            "prediction": prediction,
            "home_prob": round(float(home_prob), 4),
            "draw_prob": round(float(draw_prob), 4),
            "away_prob": round(float(away_prob), 4),
            "confidence": confidence,
            "over_25_prob": round(float(over_25_prob), 4),
            "under_25_prob": round(float(under_25_prob), 4),
            "btts_yes_prob": round(float(btts_yes_prob), 4),
            "btts_no_prob": round(float(btts_no_prob), 4),
            "model_version": config.MODEL_VERSION,
            "model_type": "ensemble",
        }

    def recalibrate(self):
        """Retrain models with fresh data. Call monthly or when accuracy drops."""
        print("[Predictor] Recalibrating models...")
        self._build_models()
        model_path = os.path.join(os.path.dirname(__file__), "models.pkl")
        self._save_models(model_path)
