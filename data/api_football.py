# data/api_football.py — Football-Data.org API client

import requests
from datetime import datetime, timedelta


class APIFootball:
    """Client for football-data.org v4 API (https://docs.football-data.org)"""

    BASE_URL = "https://api.football-data.org/v4"
    API_KEY = "17414518b4cc4b2f987595779dce4fa6"

    def __init__(self):
        self.key = self.API_KEY
        self.session = requests.Session()
        self.session.headers.update({
            "X-Auth-Token": self.key,
        })

    def _get(self, endpoint: str, params: dict = None) -> dict | None:
        """Make a GET request with error handling."""
        if not self.key or self.key == "YOUR_API_KEY_HERE":
            return None

        try:
            r = self.session.get(
                f"{self.BASE_URL}/{endpoint}",
                params=params,
                timeout=15
            )
            if r.status_code == 429:
                return None
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return None

    def get_matches_by_date(self, date: str) -> list:
        """Get all matches for a given date (YYYY-MM-DD)."""
        data = self._get("matches", {"date": date})
        if not data:
            return self._demo_matches(date)
        matches = []
        for f in data.get("matches", []):
            parsed = self._parse_fixture(f)
            if parsed:
                matches.append(parsed)
        return matches

    def _parse_fixture(self, f: dict) -> dict | None:
        """Convert football-data.org fixture to our standard format."""
        try:
            home = f.get("homeTeam", {}) or {}
            away = f.get("awayTeam", {}) or {}
            score = f.get("score", {}) or {}
            ft = score.get("fullTime", {}) or {}
            comp = f.get("competition", {}) or {}
            utc = f.get("utcDate", "")

            # Determine status
            status_map = {
                "SCHEDULED": "upcoming",
                "TIMED": "upcoming",
                "IN_PLAY": "live",
                "PAUSED": "live",
                "FINISHED": "finished",
                "POSTPONED": "upcoming",
                "SUSPENDED": "upcoming",
                "CANCELLED": "finished",
            }
            status_code = f.get("status", "SCHEDULED")
            status = status_map.get(status_code, "upcoming")

            return {
                "external_id": str(f.get("id", "")),
                "date": utc[:10],
                "time": utc[11:16],
                "home_team": home.get("shortName", home.get("name", "")),
                "away_team": away.get("shortName", away.get("name", "")),
                "home_team_id": home.get("id"),
                "away_team_id": away.get("id"),
                "home_score": ft.get("home"),
                "away_score": ft.get("away"),
                "league": comp.get("name", ""),
                "league_id": comp.get("id"),
                "country": comp.get("area", {}).get("name", ""),
                "flag": "",
                "status": status,
                "venue": None,
            }
        except Exception as e:
            return None

    def get_leagues(self) -> list:
        """Return list of available competitions."""
        data = self._get("competitions")
        if not data:
            return self._demo_leagues()
        leagues = []
        for c in data.get("competitions", []):
            leagues.append({
                "id": str(c.get("id", "")),
                "name": c.get("name", ""),
                "country": c.get("area", {}).get("name", ""),
                "flag": "",
                "logo": c.get("emblem"),
            })
        return leagues

    # ─── Demo fallbacks ────────────────────────────────────────────────

    def _demo_leagues(self) -> list:
        return [
            {"id": "PL", "name": "Premier League", "country": "England", "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "logo": ""},
            {"id": "PD", "name": "La Liga", "country": "Spain", "flag": "🇪🇸", "logo": ""},
            {"id": "BL1", "name": "Bundesliga", "country": "Germany", "flag": "🇩🇪", "logo": ""},
            {"id": "SA", "name": "Serie A", "country": "Italy", "flag": "🇮🇹", "logo": ""},
            {"id": "FL1", "name": "Ligue 1", "country": "France", "flag": "🇫🇷", "logo": ""},
            {"id": "PPL", "name": "Primeira Liga", "country": "Portugal", "flag": "🇵🇹", "logo": ""},
            {"id": "DED", "name": "Eredivisie", "country": "Netherlands", "flag": "🇳🇱", "logo": ""},
            {"id": "CL", "name": "Champions League", "country": "Europe", "flag": "🏆", "logo": ""},
        ]

    def _demo_matches(self, date: str) -> list:
        import random
        rng = random.Random(date)
        demo_data = [
            ("Arsenal", "Liverpool", "Premier League", "PL", "England"),
            ("Barcelona", "Real Madrid", "La Liga", "PD", "Spain"),
            ("Bayern Munich", "Borussia Dortmund", "Bundesliga", "BL1", "Germany"),
            ("AC Milan", "Inter Milan", "Serie A", "SA", "Italy"),
            ("PSG", "Marseille", "Ligue 1", "FL1", "France"),
            ("Ajax", "PSV", "Eredivisie", "DED", "Netherlands"),
            ("Benfica", "Porto", "Primeira Liga", "PPL", "Portugal"),
            ("Galatasaray", "Fenerbahce", "Super Lig", "TR", "Turkey"),
            ("Man City", "Man United", "Premier League", "PL", "England"),
            ("Atletico Madrid", "Sevilla", "La Liga", "PD", "Spain"),
        ]
        matches = []
        for i, (home, away, league, league_id, country) in enumerate(demo_data):
            finished = rng.choice([True, False])
            score_h = rng.randint(0, 4) if finished else None
            score_a = rng.randint(0, 4) if finished else None
            matches.append({
                "external_id": f"demo_{date}_{i}",
                "date": date,
                "time": f"{rng.randint(12, 21):02d}:{rng.choice(['00','30'])}",
                "home_team": home,
                "away_team": away,
                "home_team_id": None,
                "away_team_id": None,
                "home_score": score_h,
                "away_score": score_a,
                "league": league,
                "league_id": league_id,
                "country": country,
                "flag": "",
                "status": "finished" if finished else "upcoming",
                "venue": None,
            })
        return matches
