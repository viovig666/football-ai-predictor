# ai/features.py — Feature engineering for football match predictions

import pandas as pd
import numpy as np
from datetime import datetime


def engineer_features(match_data: dict) -> pd.DataFrame:
    """
    Convert raw match data into a feature vector for the ML model.
    
    Args:
        match_data: dict containing:
            - home_team, away_team
            - home_form (list of W/D/L), away_form
            - home_goals_scored_avg, away_goals_scored_avg
            - home_goals_conceded_avg, away_goals_conceded_avg
            - h2h_home_wins, h2h_draws, h2h_away_wins
            - home_league_pos, away_league_pos
            - home_games_played, away_games_played
    
    Returns:
        DataFrame with single row of features
    """
    f = {}

    # ── Form conversion (last 10 matches) ─────────────────────────────────
    def form_to_numeric(form_list):
        """Convert W/D/L list to weighted score (recent matches weighted higher)."""
        if not form_list or len(form_list) == 0:
            return 0.5
        weights = np.linspace(0.5, 1.0, len(form_list))  # older = lower weight
        score = 0
        for i, r in enumerate(form_list):
            if r.upper() == "W":
                score += weights[i]
            elif r.upper() == "D":
                score += weights[i] * 0.4
            # L = 0
        return score / len(form_list) if form_list else 0.5

    home_form_score = form_to_numeric(match_data.get("home_form", []))
    away_form_score = form_to_numeric(match_data.get("away_form", []))
    f["home_form_score"] = home_form_score
    f["away_form_score"] = away_form_score
    f["form_diff"] = home_form_score - away_form_score

    # ── Goals features ──────────────────────────────────────────────────────
    f["home_goals_scored_avg"] = match_data.get("home_goals_scored_avg", 1.5)
    f["away_goals_scored_avg"] = match_data.get("away_goals_scored_avg", 1.2)
    f["home_goals_conceded_avg"] = match_data.get("home_goals_conceded_avg", 1.0)
    f["away_goals_conceded_avg"] = match_data.get("away_goals_conceded_avg", 1.3)

    f["home_attack_strength"] = (f["home_goals_scored_avg"] + f["away_goals_conceded_avg"]) / 2
    f["away_attack_strength"] = (f["away_goals_scored_avg"] + f["home_goals_conceded_avg"]) / 2
    f["home_defense_strength"] = 2.0 - f["home_goals_conceded_avg"]
    f["away_defense_strength"] = 2.0 - f["away_goals_conceded_avg"]

    expected_home_goals = f["home_attack_strength"] * f["away_defense_strength"] / 2
    expected_away_goals = f["away_attack_strength"] * f["home_defense_strength"] / 2
    f["expected_goals"] = expected_home_goals + expected_away_goals

    # ── Head-to-head ────────────────────────────────────────────────────────
    h2h_home = match_data.get("h2h_home_wins", 0)
    h2h_draws = match_data.get("h2h_draws", 0)
    h2h_away = match_data.get("h2h_away_wins", 0)
    h2h_total = h2h_home + h2h_draws + h2h_away
    if h2h_total > 0:
        f["h2h_home_win_rate"] = h2h_home / h2h_total
        f["h2h_draw_rate"] = h2h_draws / h2h_total
        f["h2h_away_win_rate"] = h2h_away / h2h_total
    else:
        f["h2h_home_win_rate"] = 0.33
        f["h2h_draw_rate"] = 0.33
        f["h2h_away_win_rate"] = 0.33

    # ── League position ─────────────────────────────────────────────────────
    f["home_league_pos"] = match_data.get("home_league_pos", 8)
    f["away_league_pos"] = match_data.get("away_league_pos", 8)
    f["league_pos_diff"] = f["home_league_pos"] - f["away_league_pos"]

    # ── Home advantage ──────────────────────────────────────────────────────
    f["home_advantage"] = match_data.get("is_home", 1)  # 1 if home team, 0 if away

    # ── Time-based decay (predictions more reliable when less stale) ────────
    # If we have last update time, factor it in
    f["data_freshness"] = 1.0  # default: fresh

    return pd.DataFrame([f])


def get_feature_names():
    """Return ordered list of feature names (for model training/inference)."""
    return [
        "home_form_score", "away_form_score", "form_diff",
        "home_goals_scored_avg", "away_goals_scored_avg",
        "home_goals_conceded_avg", "away_goals_conceded_avg",
        "home_attack_strength", "away_attack_strength",
        "home_defense_strength", "away_defense_strength",
        "expected_goals",
        "h2h_home_win_rate", "h2h_draw_rate", "h2h_away_win_rate",
        "home_league_pos", "away_league_pos", "league_pos_diff",
        "home_advantage", "data_freshness",
    ]
