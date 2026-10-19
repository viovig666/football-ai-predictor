# app.py — Flask main application for Football AI Predictor
# v3 — force fresh Railway build

from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_cors import CORS
import sqlite3
import os
import json
from datetime import datetime, timedelta

import config
from ai.predictor import FootballPredictor
from data.db import init_db, get_matches, get_prediction, save_prediction, save_result
from data.api_football import APIFootball

app = Flask(__name__)
CORS(app)
app.config["DATABASE"] = config.DATABASE_PATH

predictor = FootballPredictor()
api_football = APIFootball()


# ─── Routes ────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the main SPA page."""
    return render_template("index.html")


@app.route("/static/<path:filename>")
def serve_static(filename):
    """Serve static files with no-cache headers to bypass Railway CDN."""
    response = send_from_directory(app.static_folder, filename)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/api/matches")
def api_matches():
    """
    Get matches for a date.
    Query params:
      date: today | tomorrow | YYYY-MM-DD  (default: today)
      league_id: optional filter
    """
    date_str = request.args.get("date", "today")
    league_id = request.args.get("league_id", None)

    if date_str == "today":
        target_date = datetime.now().strftime("%Y-%m-%d")
    elif date_str == "tomorrow":
        target_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        target_date = date_str

    matches = get_matches(app.config["DATABASE"], date=target_date, league_id=league_id)

    # If no matches in DB, try fetching from API
    if not matches:
        raw = api_football.get_matches_by_date(target_date)
        # Store demo/API matches in DB for prediction lookup
        for m in raw:
            m["date"] = target_date
            from data.db import insert_match
            m["id"] = insert_match(app.config["DATABASE"], m)
        matches = raw

    return jsonify({"date": target_date, "matches": matches})


@app.route("/api/matches/<int:match_id>")
def api_match_detail(match_id):
    """Get detailed info for a single match."""
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM matches WHERE id = ?", (match_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": "Match not found"}), 404

    match = dict(row)
    prediction = get_prediction(app.config["DATABASE"], match_id)

    return jsonify({"match": match, "prediction": prediction})


@app.route("/api/predict/<int:match_id>")
def api_predict(match_id):
    """
    Generate (or retrieve cached) AI prediction for a match.
    Uses feature engineering + ensemble model.
    """
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM matches WHERE id = ?", (match_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": "Match not found"}), 404

    match = dict(row)

    # Check if we already have a fresh prediction (within 6 hours)
    existing = get_prediction(app.config["DATABASE"], match_id)
    if existing and existing.get("fresh", False):
        return jsonify({"prediction": existing})

    # Generate new prediction
    prediction = predictor.predict(match)

    # Cache it
    save_prediction(app.config["DATABASE"], match_id, prediction)

    return jsonify({"prediction": prediction})


@app.route("/api/predict/batch", methods=["POST"])
def api_predict_batch():
    """
    Batch predict for all matches on a date.
    Body: {"date": "YYYY-MM-DD"}
    """
    data = request.get_json() or {}
    date_str = data.get("date", "today")

    if date_str == "today":
        target_date = datetime.now().strftime("%Y-%m-%d")
    elif date_str == "tomorrow":
        target_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        target_date = date_str

    matches = get_matches(app.config["DATABASE"], date=target_date)
    results = []

    for match in matches:
        pred = predictor.predict(dict(match))
        save_prediction(app.config["DATABASE"], match["id"], pred)
        results.append({"match_id": match["id"], "prediction": pred})

    return jsonify({"date": target_date, "predictions": results})


@app.route("/api/leagues")
def api_leagues():
    """List available leagues from API."""
    leagues = api_football.get_leagues()
    return jsonify({"leagues": leagues})


@app.route("/api/accuracy")
def api_accuracy():
    """Return platform prediction accuracy stats."""
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN actual_outcome = predicted_outcome THEN 1 ELSE 0 END) as correct
        FROM results r
        JOIN predictions p ON p.match_id = r.match_id
    """)
    row = cur.fetchone()
    conn.close()

    if row and row["total"] > 0:
        accuracy = round(row["correct"] / row["total"] * 100, 1)
    else:
        accuracy = None

    return jsonify({
        "total_predictions": row["total"] if row else 0,
        "correct_predictions": row["correct"] if row else 0,
        "accuracy_percent": accuracy
    })


@app.route("/api/feedback", methods=["POST"])
def api_feedback():
    """
    Submit actual match result to track prediction accuracy.
    Body: {"match_id": int, "home_score": int, "away_score": int}
    """
    data = request.get_json()
    match_id = data.get("match_id")
    home_score = data.get("home_score")
    away_score = data.get("away_score")

    if None in (match_id, home_score, away_score):
        return jsonify({"error": "Missing required fields"}), 400

    if home_score > away_score:
        actual = "home"
    elif home_score < away_score:
        actual = "away"
    else:
        actual = "draw"

    save_result(app.config["DATABASE"], match_id, actual, home_score, away_score)
    return jsonify({"status": "ok"})


# ─── Startup ───────────────────────────────────────────────────────────────

@app.before_request
def before_first():
    init_db(app.config["DATABASE"])


if __name__ == "__main__":
    init_db(config.DATABASE_PATH)
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
