# data/db.py — SQLite database manager for storing matches and predictions

import sqlite3
import os
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
            home_score INTEGER,
            away_score INTEGER,
            league TEXT,
            country TEXT,
            league_id TEXT,
            status TEXT DEFAULT 'upcoming',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER NOT NULL,
            predicted_outcome TEXT NOT NULL,
            home_prob REAL NOT NULL,
            draw_prob REAL NOT NULL,
            away_prob REAL NOT NULL,
            confidence INTEGER NOT NULL,
            over_25_prob REAL,
            under_25_prob REAL,
            btts_yes_prob REAL,
            btts_no_prob REAL,
            model_version TEXT,
            model_type TEXT,
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
            match_id, predicted_outcome, home_prob, draw_prob, away_prob,
            confidence, over_25_prob, under_25_prob, btts_yes_prob, btts_no_prob,
            model_version, model_type
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        prediction.get("model_version"),
        prediction.get("model_type"),
    ))
    conn.commit()
    conn.close()


def save_result(db_path: str, match_id: int, actual_outcome: str, home_score: int, away_score: int):
    """Store the actual result of a match and compute prediction correctness."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Get the prediction for this match
    cur.execute("SELECT predicted_outcome FROM predictions WHERE match_id = ?", (match_id,))
    row = cur.fetchone()
    predicted = row["predicted_outcome"] if row else None
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
    """Insert a new match and return its ID."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO matches (external_id, date, time, home_team, away_team,
                            home_score, away_score, league, country, league_id, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        match_data.get("external_id"),
        match_data.get("date"),
        match_data.get("time"),
        match_data.get("home_team"),
        match_data.get("away_team"),
        match_data.get("home_score"),
        match_data.get("away_score"),
        match_data.get("league"),
        match_data.get("country"),
        match_data.get("league_id"),
        match_data.get("status", "upcoming"),
    ))
    match_id = cur.lastrowid
    conn.commit()
    conn.close()
    return match_id
