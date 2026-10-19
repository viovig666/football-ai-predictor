# data/team_stats.py — Fetch and cache team statistics from football-data.org

import requests
import time
from datetime import datetime, timedelta
from collections import defaultdict


class TeamStats:
    """Fetches and caches team form, goals, and H2H from football-data.org."""

    BASE_URL = "https://api.football-data.org/v4"
    API_KEY = "17414518b4cc4b2f987595779dce4fa6"

    def __init__(self):
        self.key = self.API_KEY
        self.session = requests.Session()
        self.session.headers.update({"X-Auth-Token": self.key})
        self._cache = {}          # team_id -> stats dict
        self._h2h_cache = {}      # (home_id, away_id) -> H2H dict
        self._league_cache = {}   # league_id -> standings dict

    # ── Core HTTP ──────────────────────────────────────────────────────────

    def _get(self, endpoint: str, params: dict = None) -> dict | None:
        if not self.key or self.key == "YOUR_API_KEY_HERE":
            return None
        try:
            r = self.session.get(f"{self.BASE_URL}/{endpoint}", params=params, timeout=10)
            if r.status_code == 429:
                return None
            r.raise_for_status()
            return r.json()
        except Exception:
            return None

    # ── Team stats from last N matches ─────────────────────────────────────

    def get_team_stats(self, team_id: int, league_id: str = None, limit: int = 10) -> dict:
        """
        Returns dict:
          form_score       float  0..1 (1=winning, 0=losing)
          goals_scored_avg float
          goals_conceded_avg float
          matches_played   int
        """
        if team_id in self._cache:
            return self._cache[team_id]

        params = {"limit": limit, "status": "FINISHED"}
        if league_id:
            params["competitions"] = str(league_id)

        data = self._get(f"teams/{team_id}/matches", params)
        if not data:
            # Fallback defaults
            result = self._default_stats()
            self._cache[team_id] = result
            return result

        matches = data.get("matches", [])
        if not matches:
            result = self._default_stats()
            self._cache[team_id] = result
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
        return result

    # ── Head-to-head ────────────────────────────────────────────────────────

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

def get_team_stats() -> TeamStats:
    global _team_stats
    if _team_stats is None:
        _team_stats = TeamStats()
    return _team_stats
