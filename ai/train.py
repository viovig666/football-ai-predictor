# ai/train.py — Model training script
# Run: python -m ai.train

"""
Trains the ensemble model on historical match data.
For production: replace synthetic data with real historical data
from API-Football or a CSV of past matches.

Usage:
    python -m ai.train
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.predictor import FootballPredictor


def main():
    print("=" * 60)
    print("FootPredict AI — Model Training")
    print("=" * 60)

    # Initialize predictor (this builds models if not found)
    predictor = FootballPredictor()

    # Recalibrate (rebuild + save)
    predictor.recalibrate()

    print("=" * 60)
    print("Training complete! Models saved to ai/models.pkl")
    print("=" * 60)

    # Quick sanity test
    test_match = {
        "home_team": "Arsenal",
        "away_team": "Liverpool",
        "home_form": ["W", "W", "D", "W", "L", "W", "W", "D", "W", "W"],
        "away_form": ["L", "W", "W", "D", "W", "L", "W", "W", "D", "L"],
        "home_goals_scored_avg": 1.8,
        "away_goals_scored_avg": 1.6,
        "home_goals_conceded_avg": 0.9,
        "away_goals_conceded_avg": 1.1,
        "h2h_home_wins": 3,
        "h2h_draws": 1,
        "h2h_away_wins": 1,
        "home_league_pos": 3,
        "away_league_pos": 2,
        "expected_goals": 2.8,
    }

    pred = predictor.predict(test_match)
    print(f"\nSanity check — Arsenal vs Liverpool:")
    print(f"  Prediction:  {pred['prediction'].upper()}")
    print(f"  Confidence: {pred['confidence']}%")
    print(f"  Probabilities: Home {pred['home_prob']:.1%} | Draw {pred['draw_prob']:.1%} | Away {pred['away_prob']:.1%}")
    print(f"  Over 2.5: {pred['over_25_prob']:.1%} | BTTS Yes: {pred['btts_yes_prob']:.1%}")


if __name__ == "__main__":
    main()
