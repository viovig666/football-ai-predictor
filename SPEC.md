# Football AI Predictor — SPEC.md

## 1. Concept & Vision

A sophisticated football match prediction platform inspired by Forebet.com, but powered by a **real AI engine** that analyzes live data from multiple sources. The platform aggregates historical stats, team form, head-to-head records, and uses machine learning to generate predictions with accuracy rates between **80%–95%**. Clean, data-rich interface that makes complex AI predictions feel accessible and trustworthy.

**Name:** FootPredict AI
**Tagline:** "AI-Powered Football Intelligence"

---

## 2. Design Language

### Aesthetic Direction
Dark-mode sports analytics dashboard — think Bloomberg Terminal meets Sky Sports. Dense with data but visually organized. Bold accent colors for predictions, clean probability bars, and subtle card-based layout.

### Color Palette
```
--bg-primary:     #0f1419      /* Deep navy-black */
--bg-secondary:   #1a2332      /* Card backgrounds */
--bg-tertiary:    #243044      /* Hover states */
--accent-green:   #00d084      /* Win/Over predictions */
--accent-red:     #ff4757      /* Lose/Under predictions */
--accent-yellow:  #ffc107      /* Draw/Both teams */
--accent-blue:    #3b82f6      /* Links, highlights */
--text-primary:   #ffffff
--text-secondary: #8899a6
--border-color:   #2f3f54
```

### Typography
- **Primary:** Inter (Google Fonts) — clean, modern, excellent for data
- **Monospace numbers:** JetBrains Mono — for odds, percentages
- **Fallback:** system-ui, sans-serif

### Spatial System
- Base unit: 8px
- Card padding: 16px
- Section gaps: 24px
- Max content width: 1400px

### Motion Philosophy
- Subtle fade-ins on card load (opacity 0→1, 300ms ease-out)
- Probability bars animate from 0% to target on load (600ms ease-out)
- Hover: cards lift slightly (translateY -2px, shadow increase)
- Tab switches: smooth crossfade (200ms)

---

## 3. Layout & Structure

### Header
- Logo (left)
- Navigation tabs: Today | Tomorrow | This Week | Leagues
- Search bar (teams/matches)
- Settings icon

### Main Content Area

#### Filter Bar
- Country dropdown → League dropdown → Time filter
- Quick filter chips: All, Top Leagues, Both Teams To Score, Over 2.5

#### Match Grid
- Card per match containing:
  - League badge + country flag
  - Match time (or "LIVE", "FT")
  - Home team vs Away team with logos
  - **AI Prediction Box** (the hero element):
    - Prediction: HOME WIN / DRAW / AWAY WIN
    - Confidence bar (animated, percentage)
    - Probability breakdown (3 radial/bars: Home/Draw/Away)
  - Form indicators (sparkline or dots)
  - Additional tips: Over/Under 2.5, BTTS

#### Match Detail Modal
- Opens on card click
- Full stats breakdown, H2H history, league table position
- All AI prediction factors weighted and displayed

### Footer
- Data sources attribution
- Prediction accuracy disclaimer
- Links

### Responsive Strategy
- Desktop: 3-column match grid
- Tablet: 2-column
- Mobile: 1-column, collapsible filters

---

## 4. Features & Interactions

### Core Features

#### 4.1 AI Prediction Engine
- **Inputs:** Team form (last 10 matches), H2H record, home/away performance, league position, goals scored/conceded, injuries/suspensions flag
- **Model:** Ensemble of:
  - Logistic Regression (probability calibration)
  - Random Forest (feature interaction)
  - XGBoost (gradient boosting)
- **Output:** Home Win / Draw / Away Win with probability percentages and confidence score
- **Accuracy tracking:** Store predictions vs actual results, calculate rolling accuracy

#### 4.2 Match Data Pipeline
- **Primary:** API-Football (RapidAPI) — live odds, stats, fixtures
- **Fallback scraping:** Flashscore, SofaScore (stealth browser)
- **Data points per match:**
  - Team form (W/D/L last 10)
  - Home form vs away form
  - H2H last 5 meetings
  - Goals: scored/conceded (home & away)
  - League table position
  - Weather (optional)
  - Expected lineup flags

#### 4.3 Prediction Display
- Animated confidence bar (0-100%)
- Color-coded result badge
- Secondary tips: Over 2.5, Under 2.5, BTTS-Yes, BTTS-No
- Value bet indicator (when odds > AI probability → "VALUE")

#### 4.4 League & Filter System
- 50+ leagues from API
- Filter by: Today/Tomorrow/This Week
- Filter by: League, Country, Market (1X2, O/U, BTTS)

### Interactions
- **Hover on match card:** Subtle lift + show "View Details" overlay
- **Click match card:** Open detail modal with full breakdown
- **Tab navigation:** Instant filter of match list
- **Search:** Live filter as user types
- **Odds click:** Opens bookmaker link (affiliate placeholder)

### Error Handling
- API failure → fall back to scraping
- No data for match → show "Insufficient data" with manual input option
- Rate limit → queue requests, show stale data with "Updated X min ago"

---

## 5. Component Inventory

### MatchCard
```
States: default | hover | live | finished | no-prediction
Contents:
  - League indicator (flag + name)
  - Match time / LIVE minute / FT score
  - Home team | logo | prediction | logo | Away team
  - Confidence bar (animated)
  - Secondary tips row
```

### PredictionBadge
```
States: home-win (green) | draw (yellow) | away-win (red)
Appearance: Rounded pill with icon + text + percentage
```

### ConfidenceBar
```
Animated fill bar, color matches prediction
Tooltip: "AI Confidence: 87%"
```

### TeamFormDots
```
5-10 dots: green=W, yellow=D, red=L
```

### StatBar
```
Labeled bar for goals, corners, etc.
Home value | bar | away value
```

### LeagueTable (in modal)
```
Compact table: Pos | Team | P | W | D | L | GF | GA | Pts
Highlighted row for the two teams in match
```

### H2HChart
```
Last 5 meetings: date | home | score | away | result-badge
```

---

## 6. Technical Approach

### Stack
- **Backend:** Python Flask
- **AI/ML:** scikit-learn, XGBoost, pandas, numpy
- **Data:** API-Football (RapidAPI), flashscore scraping (DrissionPage/stealth-browser)
- **Frontend:** Vanilla HTML/CSS/JS (no framework needed for MVP)
- **Database:** SQLite for storing predictions + results (for accuracy tracking)
- **Live updates:** Server-Sent Events (SSE) or polling

### Project Structure
```
football-ai-predictor/
├── app.py                      # Flask main
├── config.py                   # API keys, settings
├── requirements.txt
├── SPEC.md
│
├── ai/
│   ├── __init__.py
│   ├── predictor.py            # AI prediction engine
│   ├── features.py             # Feature engineering
│   ├── model.pkl               # Trained model file
│   └── train.py                # Model training script
│
├── data/
│   ├── __init__.py
│   ├── api_football.py         # RapidAPI client
│   ├── flashscore.py           # Scraper fallback
│   ├── flashscore2.py          # Scraper fallback
│   └── db.py                   # SQLite manager
│
├── templates/
│   └── index.html              # Main SPA
│
└── static/
    ├── css/
    │   └── style.css
    └── js/
        └── app.js
```

### API Endpoints
```
GET  /                         # Serve main page
GET  /api/matches?date=today   # Get matches for date
GET  /api/matches/<id>          # Get single match detail
GET  /api/predict/<match_id>    # Get AI prediction
GET  /api/accuracy              # Get platform accuracy stats
POST /api/feedback              # Submit prediction result feedback
GET  /api/leagues               # List available leagues
```

### Data Model
```
Match:
  - id, date, time
  - home_team, away_team
  - home_score, away_score (null until finished)
  - league, country
  - status: upcoming|live|finished

Prediction:
  - match_id
  - predicted_outcome (home/draw/away)
  - home_prob, draw_prob, away_prob
  - confidence
  - over_25_prob, btts_yes_prob
  - model_version
  - created_at

Result:
  - match_id
  - actual_outcome
  - correct (boolean)
```

### AI Model Training
- Training data: 50,000+ historical matches
- Features: 20+ engineered features per match
- Retrain monthly or when accuracy drops below 75%
- Store model version in DB for audit

### Accuracy Target
- **80-95% accuracy** on 1X2 predictions
- Achieved through: ensemble model + comprehensive feature set + proper calibration
- Display rolling accuracy on homepage

---

*Last updated: 2026-10-17*
