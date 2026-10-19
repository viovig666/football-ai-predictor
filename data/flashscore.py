# data/flashscore.py — Fallback scraper using DrissionPage/stealth browser
# Used when API-Football is unavailable or rate-limited

from DrissionPage._common import ChromiumOptions, ChromiumDriver
import time


class FlashscoreScraper:
    """
    Fallback scraper for flashscore.com.tr using DrissionPage.
    Retrieves match data when API is not available.
    
    Note: DrissionPage 4.1.1.2 is already installed and confirmed working.
    """

    BASE_URL = "https://www.flashscore.com.tr"

    def __init__(self):
        self.driver = None

    def _get_driver(self):
        """Lazily initialize the browser driver."""
        if self.driver is None:
            opts = ChromiumOptions()
            opts.set_argument("--headless")
            opts.set_argument("--no-sandbox")
            opts.set_argument("--disable-dev-shm-usage")
            opts.set_argument("--disable-gpu")
            self.driver = ChromiumDriver(addr=9222, options=opts)
        return self.driver

    def get_matches_by_date(self, date: str) -> list:
        """
        Scrape matches for a given date.
        date format: YYYY-MM-DD
        """
        driver = self._get_driver()

        # Navigate to flashscore with date parameter
        url = f"{self.BASE_URL}/futbol/{date}/"
        try:
            driver.get(url, timeout=15)
            time.sleep(5)  # Wait for JS to render

            matches = []
            events = driver.eles(".event__match")

            for event in events:
                try:
                    time_elem = event.ele(".event__time")
                    home_elem = event.ele(".event__home")
                    away_elem = event.ele(".event__away")
                    league_elem = event.ele(".event__league")

                    match = {
                        "date": date,
                        "time": time_elem.text if time_elem else "",
                        "home_team": home_elem.text if home_elem else "",
                        "away_team": away_elem.text if away_elem else "",
                        "league": league_elem.text if league_elem else "",
                        "source": "flashscore",
                    }
                    matches.append(match)
                except Exception:
                    continue

            return matches

        except Exception as e:
            print(f"[Flashscore] Error scraping {url}: {e}")
            return []

    def get_team_form(self, team_name: str) -> list:
        """
        Get last 10 match results for a team.
        Returns list of W/D/L strings.
        """
        driver = self._get_driver()
        try:
            search_url = f"{self.BASE_URL}/futbol/{team_name.lower().replace(' ', '-')}/"
            driver.get(search_url, timeout=15)
            time.sleep(4)

            results = []
            form_items = driver.eles(".form__item")[:10]

            for item in form_items:
                text = item.text.strip().upper()
                if "W" in text or "L" in text or "D" in text:
                    if "W" in text and "L" not in text:
                        results.append("W")
                    elif "L" in text and "W" not in text:
                        results.append("L")
                    else:
                        results.append("D")

            return results

        except Exception as e:
            print(f"[Flashscore] Error getting form for {team_name}: {e}")
            return []

    def quit(self):
        """Clean up the browser driver."""
        if self.driver:
            self.driver.quit()
            self.driver = None
