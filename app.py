# app.py — Flask main application for Football AI Predictor
# v3 — force fresh Railway build

from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_cors import CORS
import sqlite3
import os
import json
from datetime import datetime, timedelta, timezone as tz0
from zoneinfo import ZoneInfo
PARIS_TZ = ZoneInfo("Europe/Paris")


def _paris_now():
    """Get current time in Paris timezone."""
    return datetime.now(PARIS_TZ)


def _target_date(date_str: str) -> str:
    """Convert 'today'/'tomorrow'/date to Paris-relative date string."""
    if date_str == "today":
        return _paris_now().strftime("%Y-%m-%d")
    elif date_str == "tomorrow":
        return (_paris_now() + timedelta(days=1)).strftime("%Y-%m-%d")
    return date_str

import config
from ai.predictor import FootballPredictor
from data.db import init_db, get_matches, get_prediction, save_prediction, save_result, insert_match
from data.api_football import APIFootball
from data.team_stats import get_team_stats

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
      refresh: if set, force-refresh from API and update DB
      league_id: optional filter
    """
    date_str = request.args.get("date", "today")
    league_id = request.args.get("league_id", None)
    force_refresh = request.args.get("refresh") is not None

    if date_str == "today":
        target_date = _paris_now().strftime("%Y-%m-%d")
    elif date_str == "tomorrow":
        target_date = (_paris_now() + timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        target_date = date_str

    # Try DB first
    matches = get_matches(app.config["DATABASE"], date=target_date, league_id=league_id)

    # Force refresh: delete old matches for this date and refetch from API
    if force_refresh or not matches:
        api_football_client = APIFootball()
        raw = api_football_client.get_matches_by_date(target_date)
        if raw:
            conn2 = sqlite3.connect(app.config["DATABASE"])
            cur2 = conn2.cursor()
            cur2.execute("DELETE FROM matches WHERE date = ?", (target_date,))
            conn2.commit()
            conn2.close()
            for m in raw:
                m["date"] = target_date
                insert_match(app.config["DATABASE"], m)
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
    Generate AI prediction for a match, fully stateless.
    match_id is the LOCAL DB id, but we look it up directly from the API
    via the external_id mapping to avoid needing the DB at prediction time.
    """
    # Step 1: Try to find match in local DB (most reliable path)
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM matches WHERE id = ?", (match_id,))
    row = cur.fetchone()
    conn.close()
    match = dict(row) if row else None

    # Step 2: If not in DB (wiped on deploy), fetch from API for today + tomorrow
    if not match:
        import logging
        logging.warning(f"[api_predict] match_id={match_id} not in DB, attempting self-heal from API")
        api = APIFootball()
        today = _paris_now().strftime("%Y-%m-%d")
        tomorrow = (_paris_now() + timedelta(days=1)).strftime("%Y-%m-%d")
        for target_date in [today, tomorrow]:
            raw = api.get_matches_by_date(target_date)
            logging.warning(f"[api_predict] API for {target_date} returned {len(raw)} matches")
            for m in raw:
                m["date"] = target_date
                db_id = insert_match(app.config["DATABASE"], m)
                logging.warning(f"[api_predict] insert_match returned id={db_id} for {m.get('home_team')} vs {m.get('away_team')}")
                if db_id == match_id:
                    match = m.copy()
                    match["id"] = db_id
                    break
            if match:
                break

    if not match:
        return jsonify({"error": "Match not found"}), 404

    # Step 3: Enrich with real team stats from football-data.org API
    ts = get_team_stats()
    home_id = match.get("home_team_id")
    away_id = match.get("away_team_id")
    league_id = match.get("league_id", "2001")

    import logging
    logging.warning(f"[api_predict] match_id={match_id} enrichment: home_id={home_id} away_id={away_id} league_id={league_id}")

    if home_id:
        hs = ts.get_team_stats(home_id, league_id)
        logging.warning(f"[api_predict] home stats: {hs}")
        match["home_form"] = []
        match["home_goals_scored_avg"] = hs["goals_scored_avg"]
        match["home_goals_conceded_avg"] = hs["goals_conceded_avg"]
    if away_id:
        as_ = ts.get_team_stats(away_id, league_id)
        logging.warning(f"[api_predict] away stats: {as_}")
        match["away_form"] = []
        match["away_goals_scored_avg"] = as_["goals_scored_avg"]
        match["away_goals_conceded_avg"] = as_["goals_conceded_avg"]
    if home_id and away_id:
        h2h = ts.get_h2h(home_id, away_id)
        logging.warning(f"[api_predict] h2h: {h2h}")
        match["h2h_home_wins"] = h2h["h2h_home_wins"]
        match["h2h_draws"] = h2h["h2h_draws"]
        match["h2h_away_wins"] = h2h["h2h_away_wins"]
    if home_id and league_id:
        match["home_league_pos"] = ts.get_league_position(home_id, league_id) or 8
    if away_id and league_id:
        match["away_league_pos"] = ts.get_league_position(away_id, league_id) or 8

    logging.warning(f"[api_predict] enriched match keys: {list(match.keys())}")
    logging.warning(f"[api_predict] enriched match: home_goals_scored_avg={match.get('home_goals_scored_avg')} away_goals_scored_avg={match.get('away_goals_scored_avg')} h2h_draws={match.get('h2h_draws')}")

    # Step 4: Check DB cache (within 6 hours) — best effort
    try:
        existing = get_prediction(app.config["DATABASE"], match_id)
        if existing and existing.get("fresh", False):
            return jsonify({"prediction": existing})
    except Exception:
        pass  # DB may be empty/wiped — continue without cache

    # Step 5: Generate prediction and cache it
    prediction = predictor.predict(match)

    try:
        save_prediction(app.config["DATABASE"], match_id, prediction)
    except Exception:
        pass  # DB may be full/empty — continue without cache

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
        target_date = _paris_now().strftime("%Y-%m-%d")
    elif date_str == "tomorrow":
        target_date = (_paris_now() + timedelta(days=1)).strftime("%Y-%m-%d")
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
