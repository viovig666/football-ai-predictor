# data/db.py — SQLite database manager for storing matches and predictions

import sqlite3
import os
import json
from datetime import datetime


def init_db(db_path: str):
    """Initialize the SQLite database with required tables."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_id TEXT,
            date TEXT NOT NULL,
            time TEXT,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            home_team_id INTEGER,
            away_team_id INTEGER,
            home_score INTEGER,
            away_score INTEGER,
            league TEXT,
            country TEXT,
            league_id TEXT,
            status TEXT DEFAULT 'upcoming',
            weather TEXT,
            temperature REAL,
            weather_icon TEXT,
            home_odds REAL,
            draw_odds REAL,
            away_odds REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER NOT NULL,
            prediction TEXT NOT NULL,
            home_prob REAL NOT NULL,
            draw_prob REAL NOT NULL,
            away_prob REAL NOT NULL,
            confidence INTEGER NOT NULL,
            over_25_prob REAL,
            under_25_prob REAL,
            btts_yes_prob REAL,
            btts_no_prob REAL,
            correct_score TEXT,
            correct_score_prob REAL,
            ht_ft TEXT,
            ht_ft_prob REAL,
            model_version TEXT,
            model_type TEXT,
            ht_ft_probs_json TEXT DEFAULT '{}',
            cs_probs_json TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (match_id) REFERENCES matches(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER NOT NULL UNIQUE,
            actual_outcome TEXT NOT NULL,
            home_score INTEGER,
            away_score INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (match_id) REFERENCES matches(id)
        )
    """)

    # Indexes
    cur.execute("CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_predictions_match ON predictions(match_id)")

    # Team stats cache — shared across all workers/servers so predictions are consistent
    cur.execute("""
        CREATE TABLE IF NOT EXISTS team_stats_cache (
            team_id INTEGER NOT NULL,
            league_id TEXT,
            stat_key TEXT NOT NULL,
            stat_value REAL NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (team_id, league_id, stat_key)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_team_stats_team ON team_stats_cache(team_id)")

    # Add JSON columns if they don't exist (migration for existing DBs)
    for col, default in [("ht_ft_probs_json", "{}"), ("cs_probs_json", "{}")]:
        try:
            cur.execute(f"ALTER TABLE predictions ADD COLUMN {col} TEXT DEFAULT '{default}'")
        except sqlite3.OperationalError:
            pass  # Column already exists

    conn.commit()
    conn.close()


def get_matches(db_path: str, date: str = None, league_id: str = None, limit: int = 100):
    """Fetch matches from DB, optionally filtered by date and league."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    query = "SELECT * FROM matches WHERE 1=1"
    params = []
    if date:
        query += " AND date = ?"
        params.append(date)
    if league_id:
        query += " AND league_id = ?"
        params.append(league_id)
    query += " ORDER BY time ASC LIMIT ?"
    params.append(limit)

    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_prediction(db_path: str, match_id: int) -> dict | None:
    """Get the latest prediction for a match, if it exists and is fresh (< 6h old)."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT * FROM predictions
        WHERE match_id = ?
        ORDER BY created_at DESC
        LIMIT 1
    """, (match_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    pred = dict(row)

    # Reconstruct dict fields from JSON columns
    try:
        pred["ht_ft_probs"] = json.loads(pred.pop("ht_ft_probs_json", "{}"))
    except (json.JSONDecodeError, TypeError):
        pred["ht_ft_probs"] = {}
    try:
        pred["correct_score_probs"] = json.loads(pred.pop("cs_probs_json", "{}"))
    except (json.JSONDecodeError, TypeError):
        pred["correct_score_probs"] = {}

    # Check freshness
    created = datetime.fromisoformat(pred["created_at"])
    age_hours = (datetime.now() - created).total_seconds() / 3600
    pred["fresh"] = age_hours < 6

    return pred


def save_prediction(db_path: str, match_id: int, prediction: dict):
    """Store a prediction in the DB, replacing any existing one for this match."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Upsert
    cur.execute("DELETE FROM predictions WHERE match_id = ?", (match_id,))
    cur.execute("""
        INSERT INTO predictions (
            match_id, prediction, home_prob, draw_prob, away_prob,
            confidence, over_25_prob, under_25_prob, btts_yes_prob, btts_no_prob,
            correct_score, correct_score_prob, ht_ft, ht_ft_prob,
            model_version, model_type, ht_ft_probs_json, cs_probs_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        match_id,
        prediction["prediction"],
        prediction["home_prob"],
        prediction["draw_prob"],
        prediction["away_prob"],
        prediction["confidence"],
        prediction.get("over_25_prob"),
        prediction.get("under_25_prob"),
        prediction.get("btts_yes_prob"),
        prediction.get("btts_no_prob"),
        prediction.get("correct_score"),
        prediction.get("correct_score_prob"),
        prediction.get("ht_ft"),
        prediction.get("ht_ft_prob"),
        prediction.get("model_version"),
        prediction.get("model_type"),
        json.dumps(prediction.get("ht_ft_probs", {})),
        json.dumps(prediction.get("correct_score_probs", {})),
    ))
    conn.commit()
    conn.close()


def save_result(db_path: str, match_id: int, actual_outcome: str, home_score: int, away_score: int):
    """Store the actual result of a match and compute prediction correctness."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Get the prediction for this match
    cur.execute("SELECT prediction FROM predictions WHERE match_id = ?", (match_id,))
    row = cur.fetchone()
    predicted = row["prediction"] if row else None
    correct = 1 if predicted == actual_outcome else 0

    cur.execute("DELETE FROM results WHERE match_id = ?", (match_id,))
    cur.execute("""
        INSERT INTO results (match_id, actual_outcome, home_score, away_score)
        VALUES (?, ?, ?, ?)
    """, (match_id, actual_outcome, home_score, away_score))

    conn.commit()
    conn.close()
    return correct


def insert_match(db_path: str, match_data: dict) -> int:
    """
    Insert a new match and return its ID.
    Skips insertion if a match with the same external_id and date already exists (dedup).
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Deduplicate: skip if this external_id + date combo already exists
    external_id = match_data.get("external_id")
    date_val = match_data.get("date")
    if external_id and date_val:
        cur.execute(
            "SELECT id FROM matches WHERE external_id = ? AND date = ?",
            (external_id, date_val)
        )
        existing = cur.fetchone()
        if existing:
            conn.close()
            return existing[0]

    cur.execute("""
        INSERT INTO matches (external_id, date, time, home_team, away_team,
                            home_team_id, away_team_id,
                            home_score, away_score, league, country, league_id, status,
                            weather, temperature, weather_icon,
                            home_odds, draw_odds, away_odds)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        match_data.get("external_id"),
        match_data.get("date"),
        match_data.get("time"),
        match_data.get("home_team"),
        match_data.get("away_team"),
        match_data.get("home_team_id"),
        match_data.get("away_team_id"),
        match_data.get("home_score"),
        match_data.get("away_score"),
        match_data.get("league"),
        match_data.get("country"),
        match_data.get("league_id"),
        match_data.get("status", "upcoming"),
        match_data.get("weather"),
        match_data.get("temperature"),
        match_data.get("weather_icon"),
        match_data.get("home_odds"),
        match_data.get("draw_odds"),
        match_data.get("away_odds"),
    ))
    match_id = cur.lastrowid
    conn.commit()
    conn.close()
    return match_id
