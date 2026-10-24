# data/team_stats.py — Fetch and cache team statistics from football-data.org

import requests
import time
import sqlite3
import os
from datetime import datetime, timedelta
from collections import defaultdict


class TeamStats:
    """Fetches and caches team form, goals, and H2H from football-data.org."""

    BASE_URL = "https://api.football-data.org/v4"
    API_KEY = "17414518b4cc4b2f987595779dce4fa6"
    DB_PATH = "/app/football.db"
    CACHE_TTL_HOURS = 6

    def __init__(self, db_path: str = None):
        self.key = self.API_KEY
        self.db_path = db_path or os.environ.get("DATABASE", self.DB_PATH)
        self.session = requests.Session()
        self.session.headers.update({"X-Auth-Token": self.key})
        self._cache = {}          # team_id -> stats dict (in-memory fallback)
        self._h2h_cache = {}     # (home_id, away_id) -> H2H dict (in-memory only)
        self._league_cache = {}   # league_id -> standings dict (in-memory only)

    # ── Core HTTP ──────────────────────────────────────────────────────────

    def _get(self, endpoint: str, params: dict = None, _retries: int = 3) -> dict | None:
        if not self.key or self.key == "YOUR_API_KEY_HERE":
            return None
        for attempt in range(_retries):
            try:
                r = self.session.get(f"{self.BASE_URL}/{endpoint}", params=params, timeout=15)
                if r.status_code == 429:
                    # Respect Retry-After header, or back off 10s/30s/60s
                    retry_after = r.headers.get("Retry-After")
                    wait = int(retry_after) if retry_after and retry_after.isdigit() else (2 ** attempt)
                    print(f"[TeamStats] Rate limited on {endpoint}, waiting {wait}s (attempt {attempt+1}/{_retries})")
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                return r.json()
            except Exception as e:
                if attempt == _retries - 1:
                    print(f"[TeamStats] _get failed after {_retries} attempts on {endpoint}: {e}")
                    return None
                time.sleep(2 ** attempt)
        return None

    # ── DB helpers ─────────────────────────────────────────────────────────

    def _db_get(self, team_id: int, league_id: str = None) -> dict | None:
        """Load cached stats from DB if fresh (within CACHE_TTL_HOURS)."""
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cutoff = (datetime.now() - timedelta(hours=self.CACHE_TTL_HOURS)).isoformat()
            cur.execute(
                """SELECT stat_key, stat_value FROM team_stats_cache
                   WHERE team_id=? AND league_id=? AND updated_at > ?""",
                (team_id, league_id, cutoff)
            )
            rows = cur.fetchall()
            conn.close()
            return {r[0]: r[1] for r in rows} if rows else None
        except Exception:
            return None

    def _db_set(self, team_id: int, league_id: str, stats: dict):
        """Persist team stats to DB, replacing any existing stale entries."""
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            for key, val in stats.items():
                cur.execute("""INSERT OR REPLACE INTO team_stats_cache
                    (team_id, league_id, stat_key, stat_value, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                    (team_id, league_id, key, val))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[TeamStats] DB set failed: {e}")

    def update_match_stats(self, match_id: int, stats: dict):
        """Write computed stats back to the matches table for persistence."""
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            for key, val in stats.items():
                col_map = {
                    "goals_scored_avg": "home_goals_scored_avg",
                    "goals_conceded_avg": "home_goals_conceded_avg",
                }
                col = col_map.get(key)
                if col and val is not None:
                    cur.execute(f"UPDATE matches SET {col}=? WHERE id=?", (val, match_id))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[TeamStats] update_match_stats failed: {e}")

    # ── Team stats from last N matches ─────────────────────────────────────

    def get_team_stats(self, team_id: int, league_id: str = None, limit: int = 10) -> dict:
        """
        Returns dict:
          form_score       float  0..1 (1=winning, 0=losing)
          goals_scored_avg float
          goals_conceded_avg float
          matches_played   int
        """
        # Check DB cache first (shared across servers)
        cached = self._db_get(team_id, league_id)
        if cached:
            self._cache[team_id] = cached
            return cached

        # Fall back to in-memory cache
        if team_id in self._cache:
            return self._cache[team_id]

        params = {"limit": limit, "status": "FINISHED"}
        if league_id:
            params["competitions"] = str(league_id)

        data = self._get(f"teams/{team_id}/matches", params)
        if not data:
            result = self._default_stats()
            self._cache[team_id] = result
            self._db_set(team_id, league_id, result)
            return result

        matches = data.get("matches", [])
        if not matches:
            result = self._default_stats()
            self._cache[team_id] = result
            self._db_set(team_id, league_id, result)
            return result

        # Parse last N matches
        scored = conceded = 0
        form_pts = 0
        played = 0

        for m in matches[:limit]:
            if m.get("status") != "FINISHED":
                continue
            played += 1
            my_team = None
            if m.get("homeTeam", {}).get("id") == team_id:
                my_team = "home"
            elif m.get("awayTeam", {}).get("id") == team_id:
                my_team = "away"
            else:
                continue

            score = m.get("score", {}) or {}
            ft = score.get("fullTime", {}) or {}
            my_goals = ft.get("home") if my_team == "home" else ft.get("away")
            opp_goals = ft.get("away") if my_team == "home" else ft.get("home")

            if my_goals is not None and opp_goals is not None:
                scored += my_goals
                conceded += opp_goals
                if my_goals > opp_goals:
                    form_pts += 1
                elif my_goals == opp_goals:
                    form_pts += 0.4

        n = played if played > 0 else 1
        result = {
            "form_score": round(form_pts / n, 4),
            "goals_scored_avg": round(scored / n, 4),
            "goals_conceded_avg": round(conceded / n, 4),
            "matches_played": played,
        }
        self._cache[team_id] = result
        self._db_set(team_id, league_id, result)
        return result

    # ── Head-to-head ───────────────────────────────────────────────────────

    def get_h2h(self, home_id: int, away_id: int, limit: int = 10) -> dict:
        """Returns h2h_home_wins, h2h_draws, h2h_away_wins from last N meetings."""
        key = (home_id, away_id)
        if key in self._h2h_cache:
            return self._h2h_cache[key]

        data = self._get(
            "matches",
            {
                "limit": limit,
                "homeTeam": home_id,
                "awayTeam": away_id,
                "status": "FINISHED",
            }
        )
        if not data:
            result = {"h2h_home_wins": 0, "h2h_draws": 0, "h2h_away_wins": 0}
            self._h2h_cache[key] = result
            return result

        hw = dw = aw = 0
        for m in data.get("matches", []):
            score = m.get("score", {}) or {}
            ft = score.get("fullTime", {}) or {}
            hg = ft.get("home")
            ag = ft.get("away")
            if hg is None or ag is None:
                continue
            if hg > ag:
                hw += 1
            elif hg == ag:
                dw += 1
            else:
                aw += 1

        result = {"h2h_home_wins": hw, "h2h_draws": dw, "h2h_away_wins": aw}
        self._h2h_cache[key] = result
        return result

    # ── League standings ───────────────────────────────────────────────────

    def get_league_position(self, team_id: int, league_id: str) -> int | None:
        """Return league position (1=first) or None if unknown."""
        if league_id not in self._league_cache:
            data = self._get(f"competitions/{league_id}/standings")
            if not data:
                self._league_cache[league_id] = {}
            else:
                standings = {}
                for entry in data.get("standings", []):
                    for row in entry.get("table", []):
                        standings[row.get("team", {}).get("id")] = row.get("position")
                self._league_cache[league_id] = standings

        return self._league_cache[league_id].get(team_id, 8)

    # ── Default fallback ────────────────────────────────────────────────────

    @staticmethod
    def _default_stats() -> dict:
        return {"form_score": 0.5, "goals_scored_avg": 1.5, "goals_conceded_avg": 1.2, "matches_played": 0}


# Singleton shared across requests
_team_stats = None


def get_team_stats(db_path: str = None) -> TeamStats:
    global _team_stats
    if _team_stats is None:
        _team_stats = TeamStats(db_path=db_path)
    return _team_stats
