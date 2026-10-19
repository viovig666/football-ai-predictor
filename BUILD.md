# FootPredict AI — Build & Setup Documentation

> **How we got from zero to live AI-powered football predictions.**  
> Last updated: 2026-10-19

---

## Overview

FootPredict AI is a Flask-based web app that:
1. **Fetches real football matches** from the football-data.org API
2. **Generates AI predictions** using an ensemble ML model (Logistic Regression + Random Forest + XGBoost)
3. **Serves predictions** via a clean dark-mode web interface
4. **Tracks accuracy** by comparing predictions against actual results

**Live site:** https://football-ai-predictor-production-b94b.up.railway.app

---

## Architecture

```
Browser
  └── Flask app (Railway)
        ├── /api/matches?date=YYYY-MM-DD   → football-data.org API
        ├── /api/predict/<id>               → AI model (sklearn/xgboost)
        └── SQLite DB                        → predictions + results
```

**Stack:**
- Backend: Python 3 + Flask + Gunicorn
- AI/ML: scikit-learn, XGBoost, pandas, numpy
- Data: football-data.org v4 API (free tier)
- Database: SQLite (built-in, no setup)
- Hosting: Railway (GitHub-triggered auto-deploy)
- Scraper fallback: DrissionPage 4.x (headless Chromium)

---

## Step-by-Step Setup

### Step 1 — Project Skeleton

Created the initial Flask project structure:

```
football-ai-predictor/
├── app.py              # Flask routes
├── config.py           # API keys + settings
├── requirements.txt    # Python dependencies
├── railway.json        # Railway deployment config
├── ai/
│   ├── predictor.py    # AI prediction engine
│   └── features.py     # Feature engineering
├── data/
│   ├── api_football.py # API client (changed later)
│   ├── flashscore.py   # Scraper fallback
│   └── db.py           # SQLite manager
├── templates/
│   └── index.html      # Main SPA
└── static/css/style.css
```

### Step 2 — AI Model Training (synthetic data)

Since no historical API was connected yet, the `FootballPredictor` class generates **synthetic training data** using random but realistic patterns:

```python
# ai/predictor.py — Simplified
class FootballPredictor:
    def __init__(self):
        # Generate synthetic historical matches
        X, y = self._generate_synthetic_data(n=5000)
        # Train ensemble
        self.lr  = LogisticRegression(max_iter=1000).fit(X, y)
        self.rf  = RandomForest(n_estimators=100).fit(X, y)
        self.xgb = XGBoostClassifier(n_estimators=100).fit(X, y)

    def predict(self, features: dict) -> dict:
        # Ensemble average of 3 models
        probs = (self.lr_proba + self.rf_proba + self.xgb_proba) / 3
        winner = ['home', 'draw', 'away'][probs.argmax()]
        confidence = probs.max()
        return {'prediction': winner, 'confidence': confidence, 'probabilities': probs}
```

**Results:** `lr accuracy: 0.482 | rf accuracy: 0.511 | xgb accuracy: 0.545`

> ⚠️ These low accuracy numbers are expected with synthetic random data. Once connected to real historical match data from the API, accuracy improves significantly.

### Step 3 — Choosing a Football Data API

**Initial attempt:** RapidAPI "Free Football API"  
❌ Blocked — required RapidAPI subscription

**Second attempt:** SofaScore API  
❌ Blocked — 403 Forbidden

**Third attempt:** football-data.org ✅  
✅ Works with free tier! No credit card needed.

**football-data.org free tier limits:**
- Competitions list
- Matches by date (limited competitions)
- No odds, no detailed stats
- Rate limit: ~10 requests/minute

### Step 4 — Connecting football-data.org API

**Registration:** https://www.football-data.org/register  
- Free account, no credit card
- Get API token immediately
- Token format: `XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX`

**API client** (`data/api_football.py`):

```python
import requests

class APIFootball:
    BASE_URL = "https://api.football-data.org/v4"
    API_KEY = "YOUR_TOKEN_HERE"          # ← Set this

    def _get(self, endpoint, params=None):
        headers = {"X-Auth-Token": self.API_KEY}
        r = requests.get(f"{self.BASE_URL}/{endpoint}",
                         headers=headers, params=params, timeout=15)
        r.raise_for_status()
        return r.json()

    def get_matches_by_date(self, date):
        data = self._get("matches", {"date": date})
        return [self._parse_fixture(f) for f in data.get("matches", [])]
```

**API v4 response format:**
```json
{
  "resultSet": {"count": 6},
  "matches": [{
    "id": "558576",
    "utcDate": "2026-10-19T18:00:00Z",
    "status": "FINISHED",
    "homeTeam": {"shortName": "Monza", "id": 109},
    "awayTeam": {"shortName": "Cagliari", "id": 110},
    "score": {"fullTime": {"homeGoals": 2, "awayGoals": 1}},
    "competition": {"name": "Serie A", "area": {"name": "Italy"}}
  }]
}
```

### Step 5 — Securing the API Key (Railway Environment Variables)

**Problem:** Hardcoding the API key in `api_football.py` would expose it in the public GitHub repo.

**Solution:** Use Railway's environment variables.

**How to add in Railway:**
1. Open Railway dashboard → your project
2. Go to **Variables** tab
3. Add: `FOOTBALL_DATA_API_KEY` = `your_token_here`
4. Redeploy

Then in `api_football.py`:

```python
import os

class APIFootball:
    BASE_URL = "https://api.football-data.org/v4"
    API_KEY = os.environ.get("FOOTBALL_DATA_API_KEY", "")  # ← From Railway env
```

Now the key is:
- Stored securely in Railway's environment
- Never committed to GitHub
- Loaded at runtime

### Step 6 — Deploying to Railway

**Railway setup:**

1. Go to https://railway.app
2. Create new project → **Deploy from GitHub**
3. Connect `viovig666/football-ai-predictor`
4. Railway auto-detects Python (NIXPACKS builder)
5. Add environment variable: `FOOTBALL_DATA_API_KEY`
6. Railway builds and deploys automatically on every GitHub push

**Railway config** (`railway.json`):
```json
{
  "build": {"builder": "NIXPACKS"},
  "deploy": {
    "startCommand": "gunicorn --bind 0.0.0.0:${PORT:-8000} app:app",
    "restartPolicyType": "ON_FAILURE"
  }
}
```

**Railway build output** (what you see in logs):
```
[inf]  Starting Container
[inf]  [Predictor] Generating synthetic training data...
[inf]  [Predictor] lr accuracy: 0.482
[inf]  [Predictor] rf accuracy: 0.511
[inf]  [Predictor] xgb accuracy: 0.545
[inf]  [Predictor] Models saved to /app/ai/models.pkl
```

### Step 7 — Debugging the Railway Deployment Cache Problem

**Problem encountered:** After pushing code changes, Railway kept running the old container.

**Symptoms:**
- `/api/debug` endpoint returned 404 (not in old code)
- `/api/matches` still returned demo data
- Railway logs showed new container starting

**Root cause:** Railway was using a cached Docker image from an earlier build that didn't reflect the latest GitHub commit.

**How we fixed it:**
1. Added a debug endpoint `/api/debug` to diagnose
2. Confirmed the API key was correct by testing the direct API call
3. Added environment variable to Railway (forcing a fresh env read)
4. Redeployed → ✅ New container picked up all changes

**Lesson:** When Railway seems stuck on old code, add a tiny visible change (like a comment in app.py) and redeploy to force a complete fresh build.

### Step 8 — Adding Scraping Fallback (DrissionPage)

**When needed:** When the football-data.org free tier doesn't cover a league.

**DrissionPage 4.x correct usage:**
```python
from DrissionPage import ChromiumOptions, ChromiumPage

opts = ChromiumOptions()
opts.headless(True)
opts.set_argument('--no-sandbox')
opts.set_argument('--disable-dev-shm-usage')
opts.set_argument('--disable-gpu')

page = ChromiumPage(addr_or_opts=opts, timeout=20)
page.get('https://www.flashscore.com/', timeout=15)
# ... scrape match data ...
page.quit()
```

**Important:** `ChromiumPage(addr_or_opts=opts)` — not `options=opts` (that was the old 3.x API).

### Step 9 — API Endpoints Reference

| Endpoint | Description |
|----------|-------------|
| `GET /` | Main web UI |
| `GET /api/matches?date=YYYY-MM-DD` | Matches for date + AI predictions |
| `GET /api/matches/<id>` | Single match detail |
| `GET /api/predict/<match_id>` | Full AI prediction with probabilities |
| `GET /api/leagues` | Available competitions |
| `GET /api/accuracy` | Rolling platform accuracy stats |

**Example match response:**
```json
{
  "date": "2026-10-19",
  "matches": [
    {
      "external_id": "558576",
      "date": "2026-10-19",
      "time": "18:00",
      "home_team": "Monza",
      "away_team": "Cagliari",
      "league": "Serie A",
      "country": "Italy",
      "status": "finished",
      "home_score": 2,
      "away_score": 1,
      "prediction": {
        "prediction": "home",
        "confidence": 0.52,
        "probabilities": {"home": 0.52, "draw": 0.28, "away": 0.20}
      }
    }
  ]
}
```

### Step 10 — Improving AI Accuracy

The current model uses synthetic data (48-55% accuracy). To improve:

1. **Connect historical match data** from football-data.org API:
   - `GET /matches?date=YYYY-MM-DD&status=FINISHED` for past results
   - Store in SQLite, train on real outcomes

2. **Add more features:**
   - Head-to-head record (last 5 meetings)
   - Home vs away form
   - League table position
   - Goals scored/conceded per match
   - Days since last match (rest factor)

3. **Retrain monthly** with accumulated real data

4. **Target accuracy:** 65-75% for real-world football prediction (which is genuinely hard!)

---

## Common Issues & Fixes

| Issue | Cause | Fix |
|-------|-------|-----|
| API returns 0 matches | Wrong date format | Use `YYYY-MM-DD` |
| API returns 403 | Wrong/missing API key | Check `X-Auth-Token` header |
| Railway 404 on new route | Cached Docker image | Add tiny change + redeploy |
| Demo data instead of real | API key not in Railway env | Add `FOOTBALL_DATA_API_KEY` in Railway Variables |
| DrissionPage import error | Wrong version | Use `from DrissionPage import ChromiumOptions, ChromiumPage` (v4.x) |
| CORS errors | Missing Flask-CORS | `from flask_cors import CORS; CORS(app)` |

---

## File Summary

| File | Purpose |
|------|---------|
| `app.py` | Flask routes — all API endpoints |
| `config.py` | Database path, Flask secret |
| `requirements.txt` | Python dependencies |
| `railway.json` | Railway deployment config |
| `ai/predictor.py` | Ensemble ML model + prediction logic |
| `data/api_football.py` | football-data.org API client |
| `data/db.py` | SQLite read/write for predictions |
| `data/flashscore.py` | Browser scraper fallback (v4.x API) |
| `templates/index.html` | Main single-page app |
| `static/css/style.css` | Dark-mode sports dashboard styling |
| `SPEC.md` | Design spec & component inventory |
| `BUILD.md` | This file — step-by-step build log |

---

## What's Next?

- [ ] Connect to a bookmaker API for live odds → enable "VALUE BET" indicator
- [ ] Add head-to-head history scraping
- [ ] Store real historical matches in SQLite for model retraining
- [ ] Implement model retraining on a schedule
- [ ] Add email/notification when high-confidence prediction is ready
- [ ] Add more leagues (currently limited on free tier)
