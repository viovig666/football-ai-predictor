# config.py — Configuration for Football AI Predictor

import os

# RapidAPI API-Football key — get from https://rapidapi.com/api-sports/api/api-football
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY", "YOUR_RAPIDAPI_KEY_HERE")
API_FOOTBALL_HOST = "free-football-api-v1.p.rapidapi.com"

# Database
DATABASE_PATH = os.path.join(os.path.dirname(__file__), "data", "predictions.db")

# Model
MODEL_VERSION = "1.0.0"
MIN_CONFIDENCE_THRESHOLD = 50  # Don't show predictions below 50%

# Prediction defaults when no API data available
FALLBACK_MODE = True  # Use statistical model without live data

# Bookmaker affiliate links (placeholders)
BOOKMAKER_LINKS = {
    "bet365": "https://www.bet365.com",
    "pinnacle": "https://www.pinnacle.com",
    "betway": "https://www.betway.com",
}

# League priorities (top leagues = more reliable predictions)
TOP_LEAGUES = [
    "Premier League", "La Liga", "Bundesliga", "Serie A", "Ligue 1",
    "Eredivisie", "Primeira Liga", "Belgian Pro League", "Scottish Premiership",
]

# Flask
DEBUG = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
HOST = "0.0.0.0"
PORT = 5000
