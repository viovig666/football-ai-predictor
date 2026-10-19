// app.js — FootPredict AI Frontend Logic

// ─── State ────────────────────────────────────────────────────────────
const state = {
  currentDate: 'today',
  currentMarket: 'all',
  currentLeague: '',
  searchQuery: '',
  matches: [],
  predictions: {},
  platformAccuracy: null,
};

// ─── API Helpers ─────────────────────────────────────────────────────
const API_BASE = '';

async function fetchMatches(date) {
  const params = new URLSearchParams({ date });
  if (state.currentLeague) params.set('league_id', state.currentLeague);
  const res = await fetch(`${API_BASE}/api/matches?${params}`);
  return res.json();
}

async function fetchPrediction(matchId) {
  const res = await fetch(`${API_BASE}/api/predict/${matchId}`);
  const data = await res.json();
  return data.prediction;
}

async function fetchAccuracy() {
  const res = await fetch(`${API_BASE}/api/accuracy`);
  const data = await res.json();
  return data;
}

async function fetchLeagues() {
  const res = await fetch(`${API_BASE}/api/leagues`);
  const data = await res.json();
  return data.leagues || [];
}

async function submitFeedback(matchId, homeScore, awayScore) {
  await fetch(`${API_BASE}/api/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ match_id: matchId, home_score: homeScore, away_score: awayScore }),
  });
}

// ─── Init ────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  setupEventListeners();
  await loadInitialData();
});

async function loadInitialData() {
  showLoading(true);
  try {
    const [matchesData, accuracyData, leaguesData] = await Promise.all([
      fetchMatches('today'),
      fetchAccuracy(),
      fetchLeagues(),
    ]);

    state.matches = matchesData.matches || [];
    state.platformAccuracy = accuracyData;

    renderAccuracy(accuracyData);
    renderLeagues(leaguesData);
    renderStatsBanner();
    await renderAllMatches();
  } catch (err) {
    console.error('Failed to load initial data:', err);
    showError('Failed to load data. Please refresh.');
  } finally {
    showLoading(false);
  }
}

// ─── Event Listeners ─────────────────────────────────────────────────
function setupEventListeners() {
  // Tab navigation
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.currentDate = btn.dataset.filter;
      showLoading(true);
      try {
        const data = await fetchMatches(state.currentDate === 'today' ? 'today' : state.currentDate);
        state.matches = data.matches || [];
        await renderAllMatches();
        renderStatsBanner();
      } finally {
        showLoading(false);
      }
    });
  });

  // Quick filters
  document.querySelectorAll('.qf-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.qf-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.currentMarket = btn.dataset.market;
      renderAllMatches();
    });
  });

  // League filter
  document.getElementById('leagueSelect').addEventListener('change', async (e) => {
    state.currentLeague = e.target.value;
    showLoading(true);
    try {
      const dateStr = state.currentDate === 'today' ? 'today' : state.currentDate;
      const data = await fetchMatches(dateStr);
      state.matches = data.matches || [];
      await renderAllMatches();
      renderStatsBanner();
    } finally {
      showLoading(false);
    }
  });

  // Search
  let searchTimeout;
  document.getElementById('searchInput').addEventListener('input', (e) => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      state.searchQuery = e.target.value.toLowerCase().trim();
      renderAllMatches();
    }, 300);
  });

  // Modal close
  document.getElementById('modalOverlay').addEventListener('click', (e) => {
    if (e.target === document.getElementById('modalOverlay')) {
      closeModal();
    }
  });
  document.getElementById('modalClose').addEventListener('click', closeModal);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
  });
}

// ─── Rendering ───────────────────────────────────────────────────────
async function renderAllMatches() {
  const grid = document.getElementById('matchGrid');

  let filtered = state.matches;

  // Filter by search query
  if (state.searchQuery) {
    filtered = filtered.filter(m =>
      (m.home_team || '').toLowerCase().includes(state.searchQuery) ||
      (m.away_team || '').toLowerCase().includes(state.searchQuery) ||
      (m.league || '').toLowerCase().includes(state.searchQuery)
    );
  }

  // Filter by market
  if (state.currentMarket !== 'all') {
    // These filters require predictions to be loaded
    filtered = filtered.filter(m => {
      const pred = state.predictions[m.id];
      if (!pred) return true; // show if no prediction yet
      switch (state.currentMarket) {
        case 'over25': return (pred.over_25_prob || 0) > 0.55;
        case 'btts': return (pred.btts_yes_prob || 0) > 0.55;
        case 'high-conf': return (pred.confidence || 0) >= 75;
        default: return true;
      }
    });
  }

  // Filter by league
  if (state.currentLeague) {
    filtered = filtered.filter(m => String(m.league_id) === String(state.currentLeague));
  }

  if (filtered.length === 0) {
    grid.innerHTML = '';
    document.getElementById('emptyState').style.display = 'grid';
    document.getElementById('emptyState').style.gridColumn = '1 / -1';
    return;
  }

  document.getElementById('emptyState').style.display = 'none';

  // Build cards in parallel with predictions
  const cards = await Promise.allSettled(
    filtered.map(m => buildMatchCard(m))
  );

  grid.innerHTML = '';
  cards.forEach((result, i) => {
    if (result.status === 'fulfilled') {
      grid.insertAdjacentHTML('beforeend', result.value);
    }
  });

  // Attach click listeners for modals
  grid.querySelectorAll('.match-card').forEach(card => {
    card.addEventListener('click', () => {
      const matchId = parseInt(card.dataset.matchId);
      openMatchModal(matchId);
    });
  });
}

async function buildMatchCard(match) {
  // Ensure we have a prediction
  let pred = state.predictions[match.id];
  if (!pred) {
    try {
      pred = await fetchPrediction(match.id);
      state.predictions[match.id] = pred;
    } catch {
      pred = {
        prediction: 'home',
        home_prob: 0.45,
        draw_prob: 0.28,
        away_prob: 0.27,
        confidence: 45,
        over_25_prob: 0.52,
        under_25_prob: 0.48,
        btts_yes_prob: 0.50,
        btts_no_prob: 0.50,
      };
    }
  }

  const id = match.id;
  const leagueFlag = match.flag || '⚽';
  const time = match.time || '--:--';
  const status = match.status || 'upcoming';

  // Score display
  let scoreHtml;
  if (status === 'finished' || match.home_score !== null) {
    const hs = match.home_score ?? 0;
    const as = match.away_score ?? 0;
    scoreHtml = `<div class="score-display">${hs} - ${as}</div>`;
  } else if (status === 'live') {
    const hs = match.home_score ?? 0;
    const as = match.away_score ?? 0;
    scoreHtml = `<div class="score-display">${hs} - ${as}</div>`;
  } else {
    scoreHtml = `<div class="score-display upcoming">VS</div>`;
  }

  // Time display
  const timeClass = status === 'live' ? 'live' : status === 'finished' ? 'finished' : '';
  const timeDisplay = status === 'live' ? '🔴 LIVE' : status === 'finished' ? 'FT' : time;

  // Prediction badge
  const predBadge = makePredBadge(pred.prediction, pred.confidence);

  // Probability bars
  const homePct = Math.round(pred.home_prob * 100);
  const drawPct = Math.round(pred.draw_prob * 100);
  const awayPct = Math.round(pred.away_prob * 100);

  // Tips
  const overTip = pred.over_25_prob > 0.55
    ? `<div class="tip-chip">O2.5 <span class="tip-val">${Math.round(pred.over_25_prob * 100)}%</span></div>`
    : `<div class="tip-chip">U2.5 <span class="tip-val">${Math.round(pred.under_25_prob * 100)}%</span></div>`;
  const bttsTip = pred.btts_yes_prob > 0.55
    ? `<div class="tip-chip">BTTS-Yes <span class="tip-val">${Math.round(pred.btts_yes_prob * 100)}%</span></div>`
    : `<div class="tip-chip">BTTS-No <span class="tip-val">${Math.round(pred.btts_no_prob * 100)}%</span></div>`;

  // Logo initials
  const homeInitial = (match.home_team || 'H')[0];
  const awayInitial = (match.away_team || 'A')[0];

  return `
  <article class="match-card" data-match-id="${id}">
    <div class="card-header">
      <div class="league-info">
        <span class="league-flag">${leagueFlag}</span>
        <span>${match.league || 'Unknown League'}</span>
      </div>
      <div class="match-time ${timeClass}">${timeDisplay}</div>
    </div>

    <div class="teams-row">
      <div class="team">
        <div class="team-logo">${homeInitial}</div>
        <div class="team-name">${match.home_team || 'Home Team'}</div>
      </div>

      ${scoreHtml}

      <div class="team">
        <div class="team-logo">${awayInitial}</div>
        <div class="team-name">${match.away_team || 'Away Team'}</div>
      </div>
    </div>

    <div class="prediction-box">
      <div class="pred-main">
        ${predBadge}
        <div class="confidence-val">AI Conf: <span>${pred.confidence}%</span></div>
      </div>

      <div class="prob-bars">
        <div class="prob-row">
          <span class="prob-label">1</span>
          <div class="prob-bar-track">
            <div class="prob-bar-fill home" data-width="${homePct}"></div>
          </div>
          <span class="prob-pct">${homePct}%</span>
        </div>
        <div class="prob-row">
          <span class="prob-label">X</span>
          <div class="prob-bar-track">
            <div class="prob-bar-fill draw" data-width="${drawPct}"></div>
          </div>
          <span class="prob-pct">${drawPct}%</span>
        </div>
        <div class="prob-row">
          <span class="prob-label">2</span>
          <div class="prob-bar-track">
            <div class="prob-bar-fill away" data-width="${awayPct}"></div>
          </div>
          <span class="prob-pct">${awayPct}%</span>
        </div>
      </div>

      <div class="tips-row">
        ${overTip}
        ${bttsTip}
        ${pred.confidence >= 80 ? '<div class="tip-chip">⭐ High Confidence</div>' : ''}
      </div>
    </div>
  </article>`;
}

function makePredBadge(prediction, confidence) {
  const labels = { home: 'HOME WIN', draw: 'DRAW', away: 'AWAY WIN' };
  const icons = { home: '✅', draw: '⚖️', away: '✅' };
  const label = labels[prediction] || 'N/A';
  const icon = icons[prediction] || '';
  return `<span class="prediction-badge ${prediction}">${icon} ${label} ${confidence}%</span>`;
}

// ─── Modal ───────────────────────────────────────────────────────────
async function openMatchModal(matchId) {
  const match = state.matches.find(m => m.id === matchId);
  if (!match) return;

  let pred = state.predictions[matchId];
  if (!pred) {
    try {
      pred = await fetchPrediction(matchId);
      state.predictions[matchId] = pred;
    } catch {
      // Use existing
    }
  }

  const overlay = document.getElementById('modalOverlay');
  const content = document.getElementById('modalContent');

  const homeInitial = (match.home_team || 'H')[0];
  const awayInitial = (match.away_team || 'A')[0];
  const hs = match.home_score ?? '-';
  const as = match.away_score ?? '-';

  const predBadge = pred ? makePredBadge(pred.prediction, pred.confidence) : '';

  const homePct = pred ? Math.round(pred.home_prob * 100) : 0;
  const drawPct = pred ? Math.round(pred.draw_prob * 100) : 0;
  const awayPct = pred ? Math.round(pred.away_prob * 100) : 0;

  content.innerHTML = `
    <div class="modal-match-header">
      <div class="modal-team">
        <div class="modal-team-logo">${homeInitial}</div>
        <div class="modal-team-name">${match.home_team}</div>
      </div>
      <div class="modal-score">${hs} - ${as}</div>
      <div class="modal-team">
        <div class="modal-team-logo">${awayInitial}</div>
        <div class="modal-team-name">${match.away_team}</div>
      </div>
    </div>

    ${pred ? `
    <div class="modal-section">
      <div class="modal-section-title">🤖 AI Prediction</div>
      <div class="modal-prediction">
        <div class="modal-pred-result">
          ${predBadge}
          <span style="color:var(--text-secondary);font-size:13px;">Confidence: <strong style="color:var(--accent-green)">${pred.confidence}%</strong></span>
        </div>
        <div class="modal-pred-probs">
          <div class="modal-pred-prob">
            <span class="label">Home (1)</span>
            <span class="value" style="color:var(--accent-green)">${homePct}%</span>
          </div>
          <div class="modal-pred-prob">
            <span class="label">Draw (X)</span>
            <span class="value" style="color:var(--accent-yellow)">${drawPct}%</span>
          </div>
          <div class="modal-pred-prob">
            <span class="label">Away (2)</span>
            <span class="value" style="color:var(--accent-red)">${awayPct}%</span>
          </div>
        </div>
      </div>
    </div>

    <div class="modal-section">
      <div class="modal-section-title">📊 Secondary Markets</div>
      <div class="stats-grid">
        <div class="stat-card">
          <span class="label">Over 2.5</span>
          <span class="value home">${Math.round(pred.over_25_prob * 100)}%</span>
        </div>
        <div class="stat-card">
          <span class="label">Under 2.5</span>
          <span class="value away">${Math.round(pred.under_25_prob * 100)}%</span>
        </div>
        <div class="stat-card">
          <span class="label">BTTS Yes</span>
          <span class="value home">${Math.round(pred.btts_yes_prob * 100)}%</span>
        </div>
        <div class="stat-card">
          <span class="label">BTTS No</span>
          <span class="value away">${Math.round(pred.btts_no_prob * 100)}%</span>
        </div>
      </div>
    </div>
    ` : '<p style="color:var(--text-secondary)">No prediction data available.</p>'}

    <div class="modal-section">
      <div class="modal-section-title">🏆 ${match.league || 'League'}</div>
      <p style="color:var(--text-secondary);font-size:14px;">
        ${match.country || ''} &bull; ${match.date || ''} ${match.time || ''}
      </p>
    </div>

    <div class="modal-section">
      <div class="modal-section-title">📋 Head to Head (Last 5)</div>
      <p style="color:var(--text-muted);font-size:13px;">H2H data requires API key configuration.</p>
    </div>
  `;

  overlay.classList.add('open');
  document.body.style.overflow = 'hidden';
}

function closeModal() {
  document.getElementById('modalOverlay').classList.remove('open');
  document.body.style.overflow = '';
}

// ─── UI Helpers ──────────────────────────────────────────────────────
function showLoading(show) {
  const loading = document.getElementById('loadingState');
  const empty = document.getElementById('emptyState');
  if (show) {
    loading.style.display = 'flex';
    empty.style.display = 'none';
  } else {
    loading.style.display = 'none';
  }
}

function showError(msg) {
  const grid = document.getElementById('matchGrid');
  grid.innerHTML = `<div class="empty-state" style="display:grid;grid-column:1/-1;">
    <span class="empty-icon">⚠️</span>
    <h3>Error</h3>
    <p>${msg}</p>
  </div>`;
}

function renderAccuracy(data) {
  const el = document.getElementById('accuracyValue');
  if (data && data.accuracy_percent !== null) {
    el.textContent = data.accuracy_percent + '%';
  } else {
    el.textContent = 'N/A';
  }
}

function renderLeagues(leagues) {
  const select = document.getElementById('leagueSelect');
  // Keep the first "All Leagues" option
  const first = select.options[0];
  select.innerHTML = '';
  select.appendChild(first);

  leagues.forEach(l => {
    const opt = document.createElement('option');
    opt.value = l.id;
    opt.textContent = `${l.flag || ''} ${l.name} (${l.country})`;
    select.appendChild(opt);
  });
}

function renderStatsBanner() {
  const total = state.matches.length;
  document.getElementById('totalMatches').textContent = total;

  // Average confidence
  const preds = Object.values(state.predictions);
  let avgConf = 0;
  if (preds.length > 0) {
    avgConf = Math.round(preds.reduce((s, p) => s + (p.confidence || 0), 0) / preds.length);
  }
  document.getElementById('avgConfidence').textContent = avgConf > 0 ? avgConf + '%' : '—';

  // Platform accuracy
  const acc = state.platformAccuracy;
  document.getElementById('platformAccuracy').textContent =
    (acc && acc.accuracy_percent !== null) ? acc.accuracy_percent + '%' : '—';
}

// ─── Animate probability bars on scroll into view ────────────────────
const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.querySelectorAll('.prob-bar-fill').forEach(bar => {
        const w = bar.dataset.width || 0;
        bar.style.width = w + '%';
      });
      observer.unobserve(entry.target);
    }
  });
}, { threshold: 0.1 });

// Re-observe after render
const gridObserver = new MutationObserver(() => {
  document.querySelectorAll('.match-card').forEach(card => {
    observer.observe(card);
  });
});

gridObserver.observe(document.getElementById('matchGrid'), { childList: true });
