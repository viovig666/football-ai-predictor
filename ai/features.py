# ai/features.py — Feature engineering for football match predictions
# Implements Dixon-Coles attack/defense strength + Poisson goal model

import pandas as pd
import numpy as np
from datetime import datetime


# ── League-average baselines (fallback when API data is thin) ────────────────
LEAGUE_AVG_HOME_GOALS = 1.45
LEAGUE_AVG_AWAY_GOALS = 1.12
LEAGUE_AVG_GOALS = 2.57          # total goals per game
HOME_ADVANTAGE_GOALS = 0.33      # historical home advantage


def engineer_features(match_data: dict) -> pd.DataFrame:
    """
    Convert raw match data into a feature vector for the ML model.

    Args:
        match_data: dict containing any of:
            - home_team, away_team
            - home_form (list of W/D/L), away_form
            - home_goals_scored_avg, away_goals_scored_avg
            - home_goals_conceded_avg, away_goals_conceded_avg
            - h2h_home_wins, h2h_draws, h2h_away_wins
            - home_league_pos, away_league_pos
            - is_home (bool, always 1 for home team)
            - h2h_half_time_home, h2h_half_time_draws, h2h_half_time_away (optional)
            - league_avg_home_goals, league_avg_away_goals (optional override)

    Returns:
        DataFrame with single row of features
    """
    f = {}

    # ── League-average context ───────────────────────────────────────────────
    league_avg_home = match_data.get("league_avg_home_goals", LEAGUE_AVG_HOME_GOALS)
    league_avg_away = match_data.get("league_avg_away_goals", LEAGUE_AVG_AWAY_GOALS)
    league_avg_total = match_data.get("league_avg_goals", LEAGUE_AVG_GOALS)

    # ── Form conversion (last 10 matches) ───────────────────────────────────
    def form_to_numeric(form_list):
        if not form_list or len(form_list) == 0:
            return 0.5
        weights = np.linspace(0.5, 1.0, len(form_list))
        score = 0.0
        for i, r in enumerate(form_list):
            if str(r).upper() == "W":
                score += weights[i]
            elif str(r).upper() == "D":
                score += weights[i] * 0.4
        return score / len(form_list)

    home_form_score = form_to_numeric(match_data.get("home_form", []))
    away_form_score = form_to_numeric(match_data.get("away_form", []))
    f["home_form_score"] = home_form_score
    f["away_form_score"] = away_form_score
    f["form_diff"] = home_form_score - away_form_score

    # ── Raw goals features ───────────────────────────────────────────────────
    # Use `or` fallback — explicit None from failed enrichment must fall through to defaults
    home_gs = match_data.get("home_goals_scored_avg") or 1.5
    away_gs = match_data.get("away_goals_scored_avg") or 1.2
    home_gc = match_data.get("home_goals_conceded_avg") or 1.1
    away_gc = match_data.get("away_goals_conceded_avg") or 1.3

    f["home_goals_scored_avg"] = home_gs
    f["away_goals_scored_avg"] = away_gs
    f["home_goals_conceded_avg"] = home_gc
    f["away_goals_conceded_avg"] = away_gc

    # ── Dixon-Coles attack / defense strength ratios ─────────────────────────
    # Ratio > 1 means better than league average; < 1 means worse
    # These are the key features — relative, not absolute

    home_attack = home_gs / league_avg_home          # home scoring vs league home avg
    away_attack = away_gs / league_avg_away          # away scoring vs league away avg
    home_defense = league_avg_away / away_gc        # how well home suppresses away attacks
    away_defense = league_avg_home / home_gc        # how well away suppresses home attacks

    # Clip extremes to prevent runaway values from thin-data defaults
    home_attack = np.clip(home_attack, 0.40, 2.50)
    away_attack = np.clip(away_attack, 0.40, 2.50)
    home_defense = np.clip(home_defense, 0.40, 2.50)
    away_defense = np.clip(away_defense, 0.40, 2.50)

    f["home_attack_strength"] = home_attack
    f["away_attack_strength"] = away_attack
    f["home_defense_strength"] = home_defense
    f["away_defense_strength"] = away_defense

    # ── Poisson expected goals (Dixon-Coles lambda model) ───────────────────
    # lambda_home = league_avg_home * home_attack * away_defense
    # lambda_away = league_avg_away * away_attack * home_defense
    # Home advantage is embedded in league_avg_home being higher than league_avg_away
    lambda_home = league_avg_home * home_attack * away_defense
    lambda_away = league_avg_away * away_attack * home_defense

    # Sanity clamp — thin data defaults produce moderate lambdas
    lambda_home = np.clip(lambda_home, 0.30, 4.50)
    lambda_away = np.clip(lambda_away, 0.20, 4.00)

    f["expected_goals"] = lambda_home + lambda_away
    f["expected_home_goals"] = lambda_home
    f["expected_away_goals"] = lambda_away

    # ── Head-to-head (with informative fallback) ────────────────────────────
    h2h_home = match_data.get("h2h_home_wins", 0)
    h2h_draws = match_data.get("h2h_draws", 0)
    h2h_away = match_data.get("h2h_away_wins", 0)
    h2h_total = h2h_home + h2h_draws + h2h_away

    if h2h_total >= 3:
        # Sufficient H2H — use actual rates
        f["h2h_home_win_rate"] = h2h_home / h2h_total
        f["h2h_draw_rate"] = h2h_draws / h2h_total
        f["h2h_away_win_rate"] = h2h_away / h2h_total
        f["h2h_weight"] = min(h2h_total / 10.0, 1.0)   # more matches = higher weight
    elif h2h_total > 0:
        # Partial H2H — blend with league priors
        prior_home = 0.44
        prior_draw = 0.26
        prior_away = 0.30
        weight = h2h_total / 5.0   # up to 0.6 weight for 3 H2H matches
        f["h2h_home_win_rate"] = (h2h_home / h2h_total) * weight + prior_home * (1 - weight)
        f["h2h_draw_rate"] = (h2h_draws / h2h_total) * weight + prior_draw * (1 - weight)
        f["h2h_away_win_rate"] = (h2h_away / h2h_total) * weight + prior_away * (1 - weight)
        f["h2h_weight"] = weight
    else:
        # No H2H — use league priors with low weight, not 0.33 uniform
        f["h2h_home_win_rate"] = 0.44
        f["h2h_draw_rate"] = 0.26
        f["h2h_away_win_rate"] = 0.30
        f["h2h_weight"] = 0.05    # near-zero H2H influence

    # ── HT/FT H2H (optional) ────────────────────────────────────────────────
    h2h_ht_home = match_data.get("h2h_half_time_home", None)
    h2h_ht_draws = match_data.get("h2h_half_time_draws", None)
    h2h_ht_away = match_data.get("h2h_half_time_away", None)
    if h2h_ht_home is not None and h2h_ht_draws is not None and h2h_ht_away is not None:
        ht_total = h2h_ht_home + h2h_ht_draws + h2h_ht_away
        if ht_total >= 2:
            f["h2h_ht_home_rate"] = h2h_ht_home / ht_total
            f["h2h_ht_draw_rate"] = h2h_ht_draws / ht_total
            f["h2h_ht_away_rate"] = h2h_ht_away / ht_total
        else:
            f["h2h_ht_home_rate"] = 0.40
            f["h2h_ht_draw_rate"] = 0.30
            f["h2h_ht_away_rate"] = 0.30
    else:
        # No HT H2H — derive from 1X2 using home-side HT correlation
        f["h2h_ht_home_rate"] = 0.40
        f["h2h_ht_draw_rate"] = 0.30
        f["h2h_ht_away_rate"] = 0.30

    # ── League position ─────────────────────────────────────────────────────
    f["home_league_pos"] = match_data.get("home_league_pos", 10)
    f["away_league_pos"] = match_data.get("away_league_pos", 10)
    f["league_pos_diff"] = f["home_league_pos"] - f["away_league_pos"]

    # ── Home advantage (always 1 for home team in this model) ───────────────
    f["home_advantage"] = match_data.get("is_home", 1)

    # ── Data freshness ─────────────────────────────────────────────────────
    f["data_freshness"] = match_data.get("data_freshness", 1.0)

    # ── Strength differential (key predictor for 1X2) ──────────────────────
    f["strength_diff"] = (home_attack * home_defense) - (away_attack * away_defense)

    return pd.DataFrame([f])


def get_feature_names():
    """Return ordered list of feature names (for model training/inference)."""
    return [
        "home_form_score", "away_form_score", "form_diff",
        "home_goals_scored_avg", "away_goals_scored_avg",
        "home_goals_conceded_avg", "away_goals_conceded_avg",
        "home_attack_strength", "away_attack_strength",
        "home_defense_strength", "away_defense_strength",
        "expected_goals", "expected_home_goals", "expected_away_goals",
        "h2h_home_win_rate", "h2h_draw_rate", "h2h_away_win_rate", "h2h_weight",
        "h2h_ht_home_rate", "h2h_ht_draw_rate", "h2h_ht_away_rate",
        "home_league_pos", "away_league_pos", "league_pos_diff",
        "home_advantage", "data_freshness", "strength_diff",
    ]


# ── Poisson probability helpers (used by predictor.py) ───────────────────────

def poisson_prob(lam: float, k: int) -> float:
    """P(X = k) for Poisson(lambda)."""
    import math
    if lam <= 0 or k < 0:
        return 0.0
    return math.exp(-lam + k * math.log(lam) - math.lgamma(k + 1))


def poisson_cdf(lam: float, threshold: int) -> float:
    """P(X <= threshold) for Poisson(lambda)."""
    total = 0.0
    for k in range(threshold + 1):
        total += poisson_prob(lam, k)
    return min(total, 1.0)


def correct_score_probs(lambda_home: float, lambda_away: float,
                        max_goals: int = 7) -> dict:
    """
    Return probability distribution over (home_goals, away_goals) scorelines
    using independent Poisson model.

    Returns dict: { "1-0": 0.12, "2-1": 0.09, ... }
    """
    scores = {}
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            p = poisson_prob(lambda_home, h) * poisson_prob(lambda_away, a)
            if p > 0.0001:   # skip negligible probabilities
                scores[f"{h}-{a}"] = round(p, 5)
    return scores


def half_time_probs(lambda_home: float, lambda_away: float,
                    ht_factor: float = 0.48) -> tuple:
    """
    Estimate half-time 1X2 probabilities from Poisson lambdas.
    ht_factor: HT goals are ~48% of full-game goals on average.

    Returns (home_prob, draw_prob, away_prob) for HT.
    """
    ht_home = lambda_home * ht_factor
    ht_away = lambda_away * ht_factor

    # P(HT home win) = P(home goals > away goals at HT)
    # P(HT draw)    = P(home goals == away goals at HT)
    p_home = sum(
        poisson_prob(ht_home, h) * poisson_prob(ht_away, a)
        for h in range(8) for a in range(8) if h > a
    )
    p_draw = sum(
        poisson_prob(ht_home, h) * poisson_prob(ht_away, a)
        for h in range(8) for a in range(8) if h == a
    )
    p_away = 1.0 - p_home - p_draw

    # Clamp to valid probability range
    p_away = max(0.0, min(1.0, p_away))
    p_draw = max(0.0, min(1.0, p_draw))
    p_home = max(0.0, min(1.0, p_home))
    total = p_home + p_draw + p_away
    if total > 0:
        p_home /= total
        p_draw /= total
        p_away /= total

    return p_home, p_draw, p_away


def ht_ft_probs(p_ht_home: float, p_ht_draw: float, p_ht_away: float,
                p_home_win: float, p_draw: float, p_away_win: float) -> dict:
    """
    Combine HT and FT probabilities to get HT/FT market probabilities.

    HT/FT markets: HH, HD, HA, DH, DD, DA, AH, AD, AA

    Simplified model: independence assumption modulated by correlation.
    """
    # HH = P(HT home) * P(FT home | HT home) — home team more likely to stay ahead
    # Correlation factor: if HT home, FT home probability boosted by ~10pp
    corr = 0.10

    p_ft_home_if_ht = min(p_home_win + corr * (1 - p_home_win), 0.98)
    p_ft_draw_if_ht = p_draw * (1 - corr)
    p_ft_away_if_ht = p_away_win * (1 - corr)

    p_ft_home_if_ht_draw = p_home_win * (1 - corr * 0.5)
    p_ft_draw_if_ht_draw = min(p_draw + corr * 0.3, 0.95)
    p_ft_away_if_ht_draw = p_away_win * (1 - corr * 0.5)

    p_ft_home_if_ht_away = p_home_win * (1 - corr)
    p_ft_draw_if_ht_away = p_draw * (1 - corr)
    p_ft_away_if_ht_away = min(p_away_win + corr * (1 - p_away_win), 0.98)

    # Normalize each conditional row
    for pt_home, pt_draw, pt_away in [
        (p_ft_home_if_ht, p_ft_draw_if_ht, p_ft_away_if_ht),
        (p_ft_home_if_ht_draw, p_ft_draw_if_ht_draw, p_ft_away_if_ht_draw),
        (p_ft_home_if_ht_away, p_ft_draw_if_ht_away, p_ft_away_if_ht_away),
    ]:
        s = pt_home + pt_draw + pt_away
        if s > 0:
            pt_home /= s
            pt_draw /= s
            pt_away /= s

    hh = p_ht_home * p_ft_home_if_ht
    hd = p_ht_home * p_ft_draw_if_ht
    ha = p_ht_home * p_ft_away_if_ht
    dh = p_ht_draw * p_ft_home_if_ht_draw
    dd = p_ht_draw * p_ft_draw_if_ht_draw
    da = p_ht_draw * p_ft_away_if_ht_draw
    ah = p_ht_away * p_ft_home_if_ht_away
    ad = p_ht_away * p_ft_draw_if_ht_away
    aa = p_ht_away * p_ft_away_if_ht_away

    # Collect only non-negligible markets
    result = {}
    for label, val in [("HH", hh), ("HD", hd), ("HA", ha),
                       ("DH", dh), ("DD", dd), ("DA", da),
                       ("AH", ah), ("AD", ad), ("AA", aa)]:
        if val > 0.001:
            result[label] = round(val, 4)

    return result
