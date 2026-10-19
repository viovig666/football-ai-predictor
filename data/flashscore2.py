# data/flashscore2.py — SofaScore scraper as secondary fallback

import requests
from bs4 import BeautifulSoup
import time


class SofaScoreScraper:
    """
    Secondary fallback using SofaScore's public pages + simple requests.
    SofaScore is more accessible than Flashscore for scraping.
    """

    BASE_URL = "https://www.sofascore.com"

    def get_matches_by_date(self, date: str) -> list:
        """
        date: YYYY-MM-DD
        Returns list of match dicts.
        """
        url = f"{self.BASE_URL}/football/{date}"
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml",
            }
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code != 200:
                return []

            soup = BeautifulSoup(r.text, "lxml")
            matches = []

            # SofaScore uses JS-heavy rendering, fallback to API
            return self._get_from_api(date)

        except Exception as e:
            print(f"[SofaScore] Error: {e}")
            return []

    def _get_from_api(self, date: str) -> list:
        """
        Use SofaScore's internal API which is publicly accessible.
        """
        try:
            import json
            url = f"https://www.sofascore.com/api/v1/sport/football/scheduled-events/{date}"
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get(url, headers=headers, timeout=15)
            data = r.json()

            matches = []
            for event in data.get("events", [])[:30]:
                matches.append({
                    "id": event.get("id"),
                    "date": date,
                    "time": event.get("startTime", "")[11:16],
                    "home_team": event.get("homeTeam", {}).get("name"),
                    "away_team": event.get("awayTeam", {}).get("name"),
                    "league": event.get("tournament", {}).get("name"),
                    "country": event.get("tournament", {}).get("category", {}).get("country"),
                    "status": "upcoming",
                    "source": "sofascore",
                })
            return matches

        except Exception as e:
            print(f"[SofaScore API] Error: {e}")
            return []

    def get_h2h(self, home_team: str, away_team: str) -> list:
        """Get head-to-head records between two teams."""
        try:
            url = f"{self.BASE_URL}/api/v1/search/team/{home_team.lower().replace(' ', '-')}"
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get(url, headers=headers, timeout=10)
            # Simplified — real implementation would resolve team ID first
            return []
        except Exception:
            return []
