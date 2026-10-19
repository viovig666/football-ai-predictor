# data/api_football.py — RapidAPI API-Football client

import requests
import config
from datetime import datetime, timedelta


class APIFootball:
    """Client for the Free Live Football Data API on RapidAPI."""

    BASE_URL = "https://free-football-api-v1.p.rapidapi.com"

    def __init__(self):
        self.key = config.API_FOOTBALL_KEY
        self.host = config.API_FOOTBALL_HOST
        self.session = requests.Session()
        self.session.headers.update({
            "x-rapidapi-key": self.key,
            "x-rapidapi-host": self.host,
        })

    def _get(self, endpoint: str, params: dict = None) -> dict | None:
        """Make a GET request with error handling."""
        if self.key == "YOUR_RAPIDAPI_KEY_HERE":
            return None  # Not configured

        try:
            r = self.session.get(f"{self.BASE_URL}/{endpoint}", params=params, timeout=10)
            r.raise_for_status()
            return r.json().get("response")
        except Exception as e:
            print(f"[APIFootball] Error calling {endpoint}: {e}")
            return None

    def get_leagues(self) -> list:
        """Return list of available leagues."""
        data = self._get("leagues", {"current": "true"})
        if not data:
            return self._demo_leagues()
        leagues = []
        for item in data[:50]:
            league = item.get("league", {})
            country = item.get("country", {})
            leagues.append({
                "id": league.get("id"),
                "name": league.get("name"),
                "country": country.get("name"),
                "flag": country.get("flag"),
                "logo": league.get("logo"),
            })
        return leagues

    def get_matches_by_date(self, date: str) -> list:
        """Get all matches for a given date (YYYY-MM-DD)."""
        data = self._get("/fixtures", {"date": date})
        if not data:
            return self._demo_matches(date)
        return [self._parse_free_api_fixture(f) for f in data]

    def _parse_free_api_fixture(self, f: dict) -> dict:
        """Convert free-football-api response to our standard format."""
        # Free API uses flat keys: homeTeam, awayTeam, league, country, date, etc.
        return {
            "external_id": str(f.get("id", "")),
            "date": f.get("date", "")[:10],
            "time": f.get("date", "")[11:16] if len(f.get("date", "")) > 11 else "",
            "home_team": f.get("homeTeam", ""),
            "away_team": f.get("awayTeam", ""),
            "home_team_id": None,
            "away_team_id": None,
            "home_score": f.get("score", {}).get("home") if isinstance(f.get("score"), dict) else None,
            "away_score": f.get("score", {}).get("away") if isinstance(f.get("score"), dict) else None,
            "league": f.get("league", ""),
            "league_id": None,
            "country": f.get("country", ""),
            "flag": "",
            "status": "upcoming",
            "venue": None,
        }

    def _parse_fixture(self, f: dict) -> dict:
        """Convert API fixture response to our standard format."""
        fixture = f.get("fixture", {})
        league = f.get("league", {})
        teams = f.get("teams", {})
        goals = f.get("goals", {})
        score = f.get("score", {})

        status_map = {
            "1H": "live", "2H": "live", "HT": "live",
            "FT": "finished", "ET": "finished", "P": "upcoming",
            "NS": "upcoming",
        }

        return {
            "external_id": fixture.get("id"),
            "date": fixture.get("date", "")[:10],
            "time": fixture.get("date", "")[11:16],
            "home_team": teams.get("home", {}).get("name"),
            "away_team": teams.get("away", {}).get("name"),
            "home_team_id": teams.get("home", {}).get("id"),
            "away_team_id": teams.get("away", {}).get("id"),
            "home_score": goals.get("home"),
            "away_score": goals.get("away"),
            "league": league.get("name"),
            "league_id": league.get("id"),
            "country": f.get("league", {}).get("country"),
            "status": status_map.get(fixture.get("status", ""), "upcoming"),
            "venue": fixture.get("venue", {}).get("name"),
        }

    def _demo_leagues(self) -> list:
        """Demo leagues when API key is not set."""
        return [
            {"id": "39", "name": "Premier League", "country": "England", "flag": "🇬🇧", "logo": ""},
            {"id": "140", "name": "La Liga", "country": "Spain", "flag": "🇪🇸", "logo": ""},
            {"id": "78", "name": "Bundesliga", "country": "Germany", "flag": "🇩🇪", "logo": ""},
            {"id": "135", "name": "Serie A", "country": "Italy", "flag": "🇮🇹", "logo": ""},
            {"id": "61", "name": "Ligue 1", "country": "France", "flag": "🇫🇷", "logo": ""},
            {"id": "88", "name": "Eredivisie", "country": "Netherlands", "flag": "🇳🇱", "logo": ""},
            {"id": "94", "name": "Primeira Liga", "country": "Portugal", "flag": "🇵🇹", "logo": ""},
            {"id": "144", "name": "Super Lig", "country": "Turkey", "flag": "🇹🇷", "logo": ""},
            {"id": "203", "name": "Super League", "country": "Switzerland", "flag": "🇨🇭", "logo": ""},
            {"id": "218", "name": "Jupiler Pro League", "country": "Belgium", "flag": "🇧🇪", "logo": ""},
        ]

    def _demo_matches(self, date: str) -> list:
        """Demo matches when API key is not set."""
        import random
        rng = random.Random(date)  # deterministic per date

        demo_data = [
            ("Arsenal", "Liverpool", "Premier League", "39", "England", "🇬🇧"),
            ("Barcelona", "Real Madrid", "La Liga", "140", "Spain", "🇪🇸"),
            ("Bayern Munich", "Borussia Dortmund", "Bundesliga", "78", "Germany", "🇩🇪"),
            ("AC Milan", "Inter Milan", "Serie A", "135", "Italy", "🇮🇹"),
            ("PSG", "Marseille", "Ligue 1", "61", "France", "🇫🇷"),
            ("Ajax", "PSV", "Eredivisie", "88", "Netherlands", "🇳🇱"),
            ("Benfica", "Porto", "Primeira Liga", "94", "Portugal", "🇵🇹"),
            ("Galatasaray", "Fenerbahce", "Super Lig", "144", "Turkey", "🇹🇷"),
            ("Man City", "Man United", "Premier League", "39", "England", "🇬🇧"),
            ("Atletico Madrid", "Sevilla", "La Liga", "140", "Spain", "🇪🇸"),
            ("RB Leipzig", "Bayer Leverkusen", "Bundesliga", "78", "Germany", "🇩🇪"),
            ("Juventus", "Napoli", "Serie A", "135", "Italy", "🇮🇹"),
            ("Monaco", "Lyon", "Ligue 1", "61", "France", "🇫🇷"),
            ("Sporting CP", "Braga", "Primeira Liga", "94", "Portugal", "🇵🇹"),
        ]

        times = ["12:00", "14:00", "16:00", "18:00", "20:00", "21:00"]
        matches = []
        for i, (home, away, league, league_id, country, flag) in enumerate(demo_data[:10]):
            h_score = rng.randint(0, 3)
            a_score = rng.randint(0, 3)
            status = rng.choice(["upcoming", "upcoming", "upcoming", "finished"])
            matches.append({
                "id": i + 1,
                "external_id": f"demo_{date}_{i}",
                "date": date,
                "time": rng.choice(times),
                "home_team": home,
                "away_team": away,
                "home_score": h_score if status == "finished" else None,
                "away_score": a_score if status == "finished" else None,
                "league": league,
                "league_id": league_id,
                "country": country,
                "flag": flag,
                "status": status,
            })
        return matches
