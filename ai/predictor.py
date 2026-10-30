# ai/predictor.py — AI prediction engine (ensemble of models + Poisson layers)

import pickle
import os
import numpy as np
import pandas as pd
import threading
import math

from ai.features import (
    engineer_features,
    get_feature_names,
    poisson_prob,
    poisson_cdf,
    correct_score_probs,
    half_time_probs,
    ht_ft_probs,
    LEAGUE_AVG_HOME_GOALS,
    LEAGUE_AVG_AWAY_GOALS,
)
import config


class FootballPredictor:
    """
    Ensemble AI predictor combining:
      - Logistic Regression (well-calibrated probabilities)
      - Random Forest (captures non-linear interactions)
      - XGBoost (gradient boosting for accuracy)

    Secondary Poisson layer for correct-score, HT/FT, and O/U markets.
    """

    def __init__(self):
        self.models = {}
        self.feature_names = get_feature_names()
        self._models_loaded = False
        self._trainer = None
        self._ready_event = threading.Event()

    def _ensure_models(self):
        if self._models_loaded and self.models:
            return
        self._load_or_build_models()
        self._models_loaded = True
        self._ready_event.set()

    def _load_or_build_models(self):
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
        from sklearn.linear_model import LogisticRegression
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import accuracy_score, log_loss

        print("[Predictor] Generating synthetic training data...")
        X, y = self._generate_training_data(n_samples=25000)

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

        # Model 1: Logistic Regression
        lr = LogisticRegression(max_iter=1000, solver='lbfgs', random_state=42)
        lr.fit(X_train, y_train)
        self.models["lr"] = lr

        # Model 2: Random Forest
        rf = RandomForestClassifier(
            n_estimators=150, max_depth=10,
            min_samples_leaf=20, random_state=42, n_jobs=-1
        )
        rf.fit(X_train, y_train)
        self.models["rf"] = rf

        # Model 3: XGBoost
        try:
            from xgboost import XGBClassifier
            xgb = XGBClassifier(
                n_estimators=150, max_depth=7,
                learning_rate=0.08,
                subsample=0.8, colsample_bytree=0.8,
                random_state=42,
                eval_metric="mlogloss",
                use_label_encoder=False,
            )
            xgb.fit(X_train, y_train)
            self.models["xgb"] = xgb
        except ImportError:
            print("[Predictor] XGBoost not available, falling back to RF.")
            self.models["xgb"] = rf

        # Accuracy report
        print("\n[Predictor] Model performance on test set:")
        for name, model in self.models.items():
            pred = model.predict(X_test)
            acc = accuracy_score(y_test, pred)
            ll = log_loss(y_test, model.predict_proba(X_test))
            print(f"  {name:6s}  accuracy={acc:.3f}  log_loss={ll:.3f}")

    def _generate_training_data(self, n_samples: int = 25000) -> tuple:
        """
        Generate synthetic historical match data using a proper
        Dixon-Coles Poisson goal model with real signal.

        Key improvements over v1:
          - Wide, non-overlapping team strength distribution
          - Attack/defense strengths derived from lambdas, not random noise
          - H2H that actually correlates with true outcome
          - Form that carries genuine predictive signal

        Returns: X (DataFrame), y (numpy array: 0=home, 1=draw, 2=away)
        """
        rng = np.random.default_rng(seed=42)
        records = []

        for _ in range(n_samples):
            # ── Team strength: two independent draws from a wide distribution ─
            # ~N(0.5, 0.18) truncated to [0.05, 0.95] gives real spread:
            #   ~15% of teams are clearly weak (strength < 0.35)
            #   ~15% of teams are clearly strong (strength > 0.65)
            home_talent = rng.beta(3, 3) * 0.90 + 0.05   # ~N(0.5, 0.22) clipped
            away_talent = rng.beta(3, 3) * 0.90 + 0.05

            # ── Attack & defense strengths (Dixon-Coles ratios) ─────────────────
            # Each is a ratio: team_vs_league_average
            # A strong team attacking a weak defense → high ratio → high lambda
            home_att = rng.beta(4, 3) * 1.2 + 0.35   # [0.35, 1.55] — wide spread
            home_def = rng.beta(4, 3) * 1.2 + 0.35   # [0.35, 1.55]
            away_att = rng.beta(4, 3) * 1.2 + 0.35
            away_def = rng.beta(4, 3) * 1.2 + 0.35

            # ── Form: correlated with talent but with independent noise ───────────
            home_form_base = home_talent + rng.normal(0, 0.12)
            away_form_base = away_talent + rng.normal(0, 0.12)
            home_form_base = float(np.clip(home_form_base, 0.0, 1.0))
            away_form_base = float(np.clip(away_form_base, 0.0, 1.0))

            # ── Poisson lambda (expected goals) ─────────────────────────────────
            # Historical league averages: home ~1.45, away ~1.12
            lam_home = LEAGUE_AVG_HOME_GOALS * home_att * away_def
            lam_away = LEAGUE_AVG_AWAY_GOALS * away_att * home_def
            lam_home = float(np.clip(lam_home, 0.30, 4.50))
            lam_away = float(np.clip(lam_away, 0.20, 4.00))

            # ── Simulate actual goals ───────────────────────────────────────────
            home_goals = rng.poisson(lam_home)
            away_goals = rng.poisson(lam_away)

            if home_goals > away_goals:
                outcome = 0   # home
            elif home_goals < away_goals:
                outcome = 2   # away
            else:
                outcome = 1   # draw

            # ── H2H rates: noisy but correlated with true outcome ───────────────
            # True home win rate (from lambdas)
            true_h2h_home = lam_home / (lam_home + lam_away + 0.5)
            true_h2h_draw = 0.26 + rng.normal(0, 0.06)
            true_h2h_away = 1.0 - true_h2h_home - true_h2h_draw

            # Blend true rate with some noise
            h2h_home_rate = float(np.clip(true_h2h_home + rng.normal(0, 0.07), 0.10, 0.75))
            h2h_draw_rate = float(np.clip(true_h2h_draw + rng.normal(0, 0.05), 0.10, 0.50))
            h2h_away_rate = max(0.05, 1.0 - h2h_home_rate - h2h_draw_rate)

            # ── League positions: inverse of talent with noise ───────────────────
            home_pos = int(np.clip(round(20 - home_talent * 17 + rng.normal(0, 1.8)), 1, 20))
            away_pos = int(np.clip(round(20 - away_talent * 17 + rng.normal(0, 1.8)), 1, 20))

            # ── H2H weight: based on how many matches in the "H2H history" ─────
            # Simulate 1–10 H2H matches for this pair
            h2h_total = int(rng.integers(1, 11))

            # ── H2H HT/FT rates — derived from INDEPENDENT Poisson HT goals, NOT
            # scaled from full-game H2H. Old bug: h2h_ht_home_rate = h2h_home_rate * 0.95
            # forced HT to always mirror FT outcome → model always predicted HH.
            # Real HT rates: ~45% home, ~30% draw, ~25% away (flat distribution).
            _ht_home = float(np.clip(0.45 + rng.normal(0, 0.09), 0.10, 0.80))
            _ht_draw = float(np.clip(0.30 + rng.normal(0, 0.07), 0.10, 0.55))
            _ht_away = float(np.clip(0.25 + rng.normal(0, 0.07), 0.05, 0.65))
            _ht_sum = _ht_home + _ht_draw + _ht_away
            h2h_ht_home_rate = _ht_home / _ht_sum
            h2h_ht_draw_rate = _ht_draw / _ht_sum
            h2h_ht_away_rate = _ht_away / _ht_sum

            records.append({
                # Form features
                "home_form_score": home_form_base,
                "away_form_score": away_form_base,
                "form_diff": home_form_base - away_form_base,
                # Raw goals features
                "home_goals_scored_avg": max(0.3, home_talent * 2.0 + 0.4),
                "away_goals_scored_avg": max(0.3, away_talent * 1.8 + 0.35),
                "home_goals_conceded_avg": max(0.3, (1 - home_talent) * 1.8 + 0.35),
                "away_goals_conceded_avg": max(0.3, (1 - away_talent) * 1.8 + 0.35),
                # Dixon-Coles attack/defense strengths (ratios)
                "home_attack_strength": home_att,
                "away_attack_strength": away_att,
                "home_defense_strength": home_def,
                "away_defense_strength": away_def,
                # Poisson lambdas
                "expected_goals": lam_home + lam_away,
                "expected_home_goals": lam_home,
                "expected_away_goals": lam_away,
                # H2H
                "h2h_home_win_rate": h2h_home_rate,
                "h2h_draw_rate": h2h_draw_rate,
                "h2h_away_win_rate": h2h_away_rate,
                "h2h_weight": min(h2h_total / 10.0, 1.0),
                # HT/FT H2H — independent flat distribution (fixes HH bias)
                "h2h_ht_home_rate": h2h_ht_home_rate,
                "h2h_ht_draw_rate": h2h_ht_draw_rate,
                "h2h_ht_away_rate": h2h_ht_away_rate,
                # League positions
                "home_league_pos": home_pos,
                "away_league_pos": away_pos,
                "league_pos_diff": home_pos - away_pos,
                # Fixed
                "home_advantage": 1,
                "data_freshness": 1.0,
                # Key differential feature
                "strength_diff": (home_att * home_def) - (away_att * away_def),
                # Target
                "outcome": outcome,
            })

        df = pd.DataFrame(records)
        X = df[self.feature_names]
        y = df["outcome"].values
        return X, y

    def _save_models(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self.models, f)
        print(f"[Predictor] Models saved to {path}")

    def predict(self, match_data: dict) -> dict:
        """Generate full prediction for a single match."""
        self._ensure_models()

        features = engineer_features(match_data)
        features = features[self.feature_names]

        # ── Ensemble 1X2 probabilities ──────────────────────────────────────
        probs_sum = np.zeros(3)
        weights = {"lr": 0.30, "rf": 0.35, "xgb": 0.35}

        for name, weight in weights.items():
            if name not in self.models:
                continue
            model = self.models[name]
            try:
                p = model.predict_proba(features)[0]
                if np.isnan(p).any():
                    print(f"[Predictor] {name} returned NaN, skipping")
                    continue
                probs_sum += weight * p
            except Exception as e:
                print(f"[Predictor] {name} failed: {e}")

        total = probs_sum.sum()
        if total <= 0 or np.isnan(total):
            print("[Predictor] All models failed, using Poisson fallback")
            # Fall back to pure Poisson 1X2 from lambdas in features
            lam_home = float(features["expected_home_goals"].values[0])
            lam_away = float(features["expected_away_goals"].values[0])
            p_home, p_draw, p_away = _poisson_1x2(lam_home, lam_away)
            probs = np.array([p_home, p_draw, p_away])
        else:
            probs = probs_sum / total

        home_prob, draw_prob, away_prob = probs
        confidence = int(max(probs) * 100)

        if probs.argmax() == 0:
            prediction = "home"
        elif probs.argmax() == 1:
            prediction = "draw"
        else:
            prediction = "away"

        # ── Poisson secondary predictions ────────────────────────────────────
        lam_home = float(features["expected_home_goals"].values[0])
        lam_away = float(features["expected_away_goals"].values[0])
        total_goals = lam_home + lam_away

        # Over/Under 2.5
        over_25_prob = 1.0 - poisson_cdf(lam_home + lam_away, 2)  # P(X >= 3)
        over_25_prob = float(np.clip(over_25_prob, 0.0, 0.99))
        under_25_prob = 1.0 - over_25_prob

        # BTTS — P(both score) = P(home>0) * P(away>0) under independence
        p_btts_yes = (1 - poisson_prob(lam_home, 0)) * (1 - poisson_prob(lam_away, 0))
        p_btts_yes = float(np.clip(p_btts_yes, 0.0, 0.99))
        p_btts_no = 1.0 - p_btts_yes

        # Correct score distribution (top scorelines)
        cs_probs = correct_score_probs(lam_home, lam_away, max_goals=6)

        # HT/FT
        p_ht_home, p_ht_draw, p_ht_away = half_time_probs(lam_home, lam_away)
        ht_ft = ht_ft_probs(p_ht_home, p_ht_draw, p_ht_away,
                            float(home_prob), float(draw_prob), float(away_prob))

        return {
            # 1X2
            "prediction": prediction,
            "home_prob": round(float(home_prob), 4),
            "draw_prob": round(float(draw_prob), 4),
            "away_prob": round(float(away_prob), 4),
            "confidence": confidence,
            # O/U
            "over_25_prob": round(over_25_prob, 4),
            "under_25_prob": round(under_25_prob, 4),
            # BTTS
            "btts_yes_prob": round(p_btts_yes, 4),
            "btts_no_prob": round(p_btts_no, 4),
            # Correct score (top 6 most likely)
            "correct_score_probs": _top_scores(cs_probs, n=6),
            # HT/FT
            "ht_ft_probs": ht_ft,
            # Meta
            "expected_goals": round(total_goals, 2),
            "model_version": config.MODEL_VERSION,
            "model_type": "ensemble+poisson",
        }

    def recalibrate(self):
        """Retrain models with fresh synthetic data."""
        print("[Predictor] Recalibrating models...")
        self._build_models()
        model_path = os.path.join(os.path.dirname(__file__), "models.pkl")
        self._save_models(model_path)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _poisson_1x2(lam_home: float, lam_away: float) -> tuple:
    """Derive 1X2 from Poisson lambdas (independence model)."""
    p_home = sum(
        poisson_prob(lam_home, h) * poisson_prob(lam_away, a)
        for h in range(9) for a in range(9) if h > a
    )
    p_away = sum(
        poisson_prob(lam_home, h) * poisson_prob(lam_away, a)
        for h in range(9) for a in range(9) if h < a
    )
    p_draw = 1.0 - p_home - p_away
    p_draw = max(0.0, min(1.0, p_draw))
    p_away = max(0.0, min(1.0, p_away))
    p_home = max(0.0, min(1.0, p_home))
    return p_home, p_draw, p_away


def _top_scores(cs_probs: dict, n: int = 6) -> dict:
    """Return the n most likely correct-score outcomes."""
    sorted_scores = sorted(cs_probs.items(), key=lambda x: x[1], reverse=True)
    return dict(sorted_scores[:n])
