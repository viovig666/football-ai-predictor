
const API_BASE = '';
const state = {
  currentDate: 'today', currentMarket: 'all', currentLeague: '',
  searchQuery: '', matches: [], predictions: {}, platformAccuracy: null,
};

let refreshTimer = null;

function startAutoRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(async () => {
    try {
      const data = await fetchMatches(state.currentDate === 'today' ? 'today' : state.currentDate);
      const newMatches = data.matches || [];
      const changed = newMatches.some((nm, i) => {
        const om = state.matches[i];
        return om && (om.home_score !== nm.home_score || om.away_score !== nm.away_score || om.status !== nm.status);
      });
      if (changed) {
        state.matches = newMatches;
        renderAllMatches();
        document.querySelectorAll('.match-card').forEach(c => { c.classList.add('updated'); setTimeout(() => c.classList.remove('updated'), 800); });
      }
    } catch (_) {}
  }, 30000);
}

async function fetchMatches(date) {
  const p = new URLSearchParams({ date });
  if (state.currentLeague) p.set('league_id', state.currentLeague);
  return fetch(`${API_BASE}/api/matches?${p}`).then(r => r.json());
}
async function fetchPrediction(id) { return fetch(`${API_BASE}/api/predict/${id}`).then(r => r.json()).then(d => d.prediction); }
async function fetchAccuracy() { return fetch(`${API_BASE}/api/accuracy`).then(r => r.json()); }
async function fetchLeagues() { return fetch(`${API_BASE}/api/leagues`).then(r => r.json()).then(d => d.leagues || []); }

document.addEventListener('DOMContentLoaded', async () => {
  setupEventListeners();
  await loadInitialData();
  startAutoRefresh();
});

async function loadInitialData() {
  // Show loading state while fetching initial data — but render matches as soon as we have them
  showLoading(true);
  try {
    const md = await fetchMatches('today').catch(e => { console.warn('matches failed:', e); return { matches: [] }; });
    state.matches = md.matches || [];
    renderAccuracy({});
    renderStatsBanner();
    renderAllMatches();
  } catch (e) { console.warn('loadInitialData error:', e); }
  finally { showLoading(false); }

  // Fetch remaining data in background, update UI when ready
  fetchAccuracy().then(ad => {
    state.platformAccuracy = ad;
    renderAccuracy(ad);
  }).catch(() => {});

  fetchLeagues().then(ld => {
    renderLeagues(ld.leagues || []);
  }).catch(() => {});
}

function setupEventListeners() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.currentDate = btn.dataset.filter;
      showLoading(true);
      try {
        state.matches = (await fetchMatches(state.currentDate === 'today' ? 'today' : state.currentDate)).matches || [];
        renderAllMatches(); renderStatsBanner();
      } finally { showLoading(false); }
    });
  });

  document.querySelectorAll('.qf-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.qf-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.currentMarket = btn.dataset.market;
      renderAllMatches();
    });
  });

  document.getElementById('leagueSelect').addEventListener('change', async e => {
    state.currentLeague = e.target.value;
    showLoading(true);
    try {
      state.matches = (await fetchMatches(state.currentDate === 'today' ? 'today' : state.currentDate)).matches || [];
      renderAllMatches(); renderStatsBanner();
    } finally { showLoading(false); }
  });

  let st; document.getElementById('searchInput').addEventListener('input', e => { clearTimeout(st); st = setTimeout(() => { state.searchQuery = e.target.value.toLowerCase().trim(); renderAllMatches(); }, 250); });
  document.getElementById('modalOverlay').addEventListener('click', e => { if (e.target === document.getElementById('modalOverlay')) closeModal(); });
  document.getElementById('modalClose').addEventListener('click', closeModal);
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
}

async function renderAllMatches() {
  const grid = document.getElementById('matchGrid');
  let list = [...state.matches];

  if (state.searchQuery) {
    list = list.filter(m =>
      (m.home_team||'').toLowerCase().includes(state.searchQuery) ||
      (m.away_team||'').toLowerCase().includes(state.searchQuery) ||
      (m.league||'').toLowerCase().includes(state.searchQuery)
    );
  }
  if (state.currentMarket !== 'all') {
    list = list.filter(m => {
      const p = state.predictions[m.id];
      if (!p) return state.currentMarket === 'high-conf';
      switch (state.currentMarket) {
        case 'over25': return (p.over_25_prob||0) > 0.55;
        case 'btts': return (p.btts_yes_prob||0) > 0.55;
        case 'high-conf': return (p.confidence||0) >= 72;
        case 'htft': return p.ht_ft_probs != null;
        case 'cs': return p.correct_score_probs != null;
        default: return true;
      }
    });
  }
  if (state.currentLeague) list = list.filter(m => String(m.league_id) === String(state.currentLeague));

  if (list.length === 0) {
    grid.innerHTML = '';
    const e = document.getElementById('emptyState');
    if (e) { e.style.display = 'grid'; e.style.gridColumn = '1 / -1'; }
    return;
  }
  // Prefetch predictions in parallel with per-match timeout; render cards immediately with defaults, update as results arrive
  grid.innerHTML = '';
  const predFutures = list.map(m => {
    return new Promise(resolve => {
      const tid = setTimeout(() => resolve({ id: m.id, pred: makeDefaultPred() }), 3000);
      fetchPrediction(m.id)
        .then(pred => { clearTimeout(tid); resolve({ id: m.id, pred }); })
        .catch(() => { clearTimeout(tid); resolve({ id: m.id, pred: makeDefaultPred() }); });
    });
  });

  // Render all match cards immediately with default predictions
  list.forEach(m => {
    state.predictions[m.id] = makeDefaultPred();
    const card = buildMatchCard(m);
    grid.insertAdjacentHTML('beforeend', card);
  });
  grid.querySelectorAll('.match-card').forEach(c => c.addEventListener('click', () => openMatchModal(+c.dataset.matchId)));
  grid.querySelectorAll('.share-btn').forEach(btn => btn.addEventListener('click', e => { e.stopPropagation(); handleShare(btn); }));
  setTimeout(() => {
    grid.querySelectorAll('.prob-bar-fill').forEach(bar => { bar.style.width = (bar.dataset.width || 0) + '%'; });
  }, 100);

  // Update cards as real predictions arrive — replace card HTML when prediction arrives
  Promise.allSettled(predFutures).then(results => {
    results.forEach(r => {
      if (r.status !== 'fulfilled') return;
      const { id, pred } = r.value;
      state.predictions[id] = pred;
      const card = grid.querySelector(`[data-match-id="${id}"]`);
      if (!card) return;
      const newCardHtml = buildMatchCard(list.find(m => m.id === id));
      const tmp = document.createElement('div');
      tmp.innerHTML = newCardHtml;
      const newCard = tmp.firstElementChild;
      if (newCard) {
        newCard.querySelectorAll('.share-btn').forEach(btn => btn.addEventListener('click', e => { e.stopPropagation(); handleShare(btn); }));
        newCard.querySelectorAll('.prob-bar-fill').forEach(bar => { bar.style.width = (bar.dataset.width || 0) + '%'; });
        newCard.addEventListener('click', () => openMatchModal(+newCard.dataset.matchId));
        grid.replaceChild(newCard, card);
      }
    });
  });

async function buildMatchCard(match) {
  const pred = state.predictions[match.id] || makeDefaultPred();

  const status = match.status || 'upcoming';
  const isLive = status === 'live';
  const isFinished = status === 'finished';

  // Score display
  let scoreHtml;
  if (isFinished || match.home_score !== null) {
    const hs = match.home_score ?? 0, as = match.away_score ?? 0;
    scoreHtml = `<div class="score-display">${hs} – ${as}</div>`;
  } else {
    scoreHtml = `<div class="score-display upcoming">VS</div>`;
  }

  // League / time / weather header
  const leagueFlag = match.flag || '⚽';
  const leagueName = match.league || 'Unknown';
  const timeStr = match.time || '--:--';
  const weatherIcon = match.weather_icon || '';
  const temp = match.temperature ? match.temperature + '°' : '';

  // 1X2 probs
  const hp = Math.round((pred.home_prob||0.33)*100);
  const dp = Math.round((pred.draw_prob||0.28)*100);
  const ap = Math.round((pred.away_prob||0.32)*100);

  // Pred badge
  const predVal = pred.prediction || 'home';
  const conf = pred.confidence || 50;
  const predLabel = {home:'HOME WIN',draw:'DRAW',away:'AWAY WIN'}[predVal] || 'N/A';
  const predIcon = {home:'⚽',draw:'⚖️',away:'⚽'}[predVal] || '';
  const badgeClass = predVal;

  // Odds
  const ho = pred.home_odds ? +pred.home_odds.toFixed(2) : null;
  const do_ = pred.draw_odds ? +pred.draw_odds.toFixed(2) : null;
  const ao = pred.away_odds ? +pred.away_odds.toFixed(2) : null;
  const hasOdds = ho && do_ && ao;

  // Correct score — top 3
  const cs = pred.correct_score_probs || {};
  const topCs = Object.entries(cs).sort((a,b) => b[1]-a[1]).slice(0,3);
  const hasCs = topCs.length > 0;

  // HT/FT — top 3
  const htft = pred.ht_ft_probs || {};
  const topHtft = Object.entries(htft).sort((a,b) => b[1]-a[1]).slice(0,3);
  const hasHtft = topHtft.length > 0;

  // Tips
  const over25 = Math.round((pred.over_25_prob||0)*100);
  const bttsYes = Math.round((pred.btts_yes_prob||0)*100);
  const tips = [];
  if (over25 > 55) tips.push({l:'O2.5',v:over25+'%'});
  else tips.push({l:'U2.5',v:(100-over25)+'%'});
  if (bttsYes > 55) tips.push({l:'BTTS-Yes',v:bttsYes+'%'});
  else tips.push({l:'BTTS-No',v:(100-bttsYes)+'%'});
  if (conf >= 72) tips.push({l:'⭐ High Conf',v:conf+'%',high:true});

  // Live status
  const liveHtml = isLive ? '<div class="live-badge"><span class="live-dot" style="width:6px;height:6px;background:var(--accent-red);border-radius:50%;display:inline-block;"></span> LIVE</div>' : '';
  const timeClass = isLive ? 'live' : isFinished ? 'finished' : 'upcoming';
  const timeDisplay = isLive ? '🔴 LIVE' : isFinished ? 'FT' : timeStr;
  const countdownHtml = !isLive && !isFinished ? `<span class="countdown" id="cd-${match.id}"></span>` : '';

  // Team initials
  const homeInit = (match.home_team||'H')[0].toUpperCase();
  const awayInit = (match.away_team||'A')[0].toUpperCase();

  // Odds chips
  const oddsHtml = hasOdds ? `
  <div class="odds-row">
    <div class="odds-chip home"><span class="odds-label">1</span><span class="odds-value">${ho}</span></div>
    <div class="odds-chip draw"><span class="odds-label">X</span><span class="odds-value">${do_}</span></div>
    <div class="odds-chip away"><span class="odds-label">2</span><span class="odds-value">${ao}</span></div>
  </div>` : '';

  // Correct score row
  const csRowHtml = hasCs ? `
  <div class="cs-row">
    <span class="cs-label">CS</span>
    <div class="cs-items">
      ${topCs.map(([score,p]) => `<div class="cs-chip">${score}<span class="cs-pct">${Math.round(p*100)}%</span></div>`).join('')}
    </div>
  </div>` : '';

  // HT/FT row
  const htftRowHtml = hasHtft ? `
  <div class="htft-row">
    <span class="htft-label">HT/FT</span>
    <div class="htft-items">
      ${topHtft.map(([k,p]) => `<div class="htft-chip${k===topHtft[0][0]?' top':''}">${k}<span class="htft-pct">${Math.round(p*100)}%</span></div>`).join('')}
    </div>
  </div>` : '';

  // Tips row
  const tipsRowHtml = tips.length ? `
  <div class="tips-row">
    ${tips.map(t => `<div class="tip-chip${t.high?' high-conf':''}">${t.l} <span class="tip-val">${t.v}</span></div>`).join('')}
  </div>` : '';

  // Conf bar
  const confPct = Math.min(conf, 100);

  return `
  <article class="match-card" data-match-id="${match.id}">
    <div class="card-topbar">
      <div class="league-info">
        <span class="league-badge">${leagueFlag}</span>
        <span>${leagueName}</span>
      </div>
      <div class="match-meta">
        ${weatherIcon ? `<span class="weather-chip"><span class="weather-icon">${weatherIcon}</span>${temp}</span>` : ''}
        ${countdownHtml}
        <div class="match-status">
          <div class="match-time ${timeClass}">${timeDisplay}</div>
          ${liveHtml}
        </div>
      </div>
    </div>

    <div class="teams-row">
      <div class="team">
        <div class="team-logo">${homeInit}</div>
        <div class="team-name">${match.home_team||'Home'}</div>
      </div>
      ${scoreHtml}
      <div class="team">
        <div class="team-logo">${awayInit}</div>
        <div class="team-name">${match.away_team||'Away'}</div>
      </div>
    </div>

    <div class="prediction-section">
      <div class="pred-main-row">
        <span class="pred-badge ${badgeClass}">${predIcon} ${predLabel} ${conf}%</span>
        <button class="share-btn" data-id="${match.id}">🔗 Share</button>
      </div>

      ${oddsHtml}

      <div class="prob-bars">
        <div class="prob-row">
          <span class="prob-label">1</span>
          <div class="prob-bar-track"><div class="prob-bar-fill home" data-width="${hp}"></div></div>
          <span class="prob-pct">${hp}%</span>
        </div>
        <div class="prob-row">
          <span class="prob-label">X</span>
          <div class="prob-bar-track"><div class="prob-bar-fill draw" data-width="${dp}"></div></div>
          <span class="prob-pct">${dp}%</span>
        </div>
        <div class="prob-row">
          <span class="prob-label">2</span>
          <div class="prob-bar-track"><div class="prob-bar-fill away" data-width="${ap}"></div></div>
          <span class="prob-pct">${ap}%</span>
        </div>
      </div>

      ${csRowHtml}
      ${htftRowHtml}
      ${tipsRowHtml}

      <div class="conf-bar">
        <span class="conf-label">AI Conf.</span>
        <div class="conf-bar-track"><div class="conf-bar-fill" style="width:${confPct}%"></div></div>
        <span class="conf-value">${conf}%</span>
      </div>
    </div>
  </article>`;
}

function makeDefaultPred() {
  return { prediction:'home', home_prob:0.40, draw_prob:0.28, away_prob:0.32, confidence:50,
    over_25_prob:0.52, under_25_prob:0.48, btts_yes_prob:0.50, btts_no_prob:0.50,
    ht_ft_probs:{}, correct_score_probs:{} };
}

// ─── Modal ───
async function openMatchModal(id) {
  const match = state.matches.find(m => m.id === id);
  if (!match) return;
  let pred = state.predictions[id];
  if (!pred) { try { pred = await fetchPrediction(id); state.predictions[id] = pred; } catch { pred = makeDefaultPred(); } }

  const status = match.status || 'upcoming';
  const isLive = status === 'live', isFinished = status === 'finished';
  const hs = isFinished || match.home_score !== null ? (match.home_score ?? 0) : '-';
  const as_ = isFinished || match.home_score !== null ? (match.away_score ?? 0) : '-';
  const homeInit = (match.home_team||'H')[0].toUpperCase();
  const awayInit = (match.away_team||'A')[0].toUpperCase();
  const hp = Math.round((pred.home_prob||0.33)*100);
  const dp = Math.round((pred.draw_prob||0.28)*100);
  const ap = Math.round((pred.away_prob||0.32)*100);
  const predVal = pred.prediction||'home';
  const conf = pred.confidence||50;
  const predLabel = {home:'HOME WIN',draw:'DRAW',away:'AWAY WIN'}[predVal]||'N/A';

  // Correct score table
  const cs = pred.correct_score_probs || {};
  const topCs = Object.entries(cs).sort((a,b)=>b[1]-a[1]).slice(0,8);
  const csRows = topCs.map(([score,p]) =>
    `<tr><td>${score}</td><td>${Math.round(p*100)}%</td></tr>`).join('');

  // HT/FT
  const htft = pred.ht_ft_probs || {};
  const topHtft = Object.entries(htft).sort((a,b)=>b[1]-a[1]);
  const htftCards = topHtft.slice(0,9).map(([k,p]) =>
    `<div class="htft-card${k===topHtft[0][0]?' top':''}"><div class="htft-label">${k}</div><div class="htft-pct">${Math.round(p*100)}%</div></div>`).join('');

  // Odds
  const ho = pred.home_odds ? +pred.home_odds.toFixed(2) : null;
  const do_ = pred.draw_odds ? +pred.draw_odds.toFixed(2) : null;
  const ao = pred.away_odds ? +pred.away_odds.toFixed(2) : null;
  const hasOdds = ho && do_ && ao;

  // Weather
  const weatherIcon = match.weather_icon || '🌤️';
  const weatherDesc = match.weather || 'Clear';
  const temp = match.temperature ? match.temperature + '°C' : '';

  // Expected goals
  const xg = pred.expected_goals ? +pred.expected_goals.toFixed(2) : null;

  const content = document.getElementById('modalContent');
  content.innerHTML = `
    <div class="modal-match-header">
      <div class="modal-team">
        <div class="modal-team-logo">${homeInit}</div>
        <div class="modal-team-name">${match.home_team}</div>
      </div>
      <div>
        <div class="modal-score">${hs} – ${as_}</div>
        <div class="modal-score-label">${isLive?'🔴 LIVE':isFinished?'FT':match.time||''}</div>
      </div>
      <div class="modal-team">
        <div class="modal-team-logo">${awayInit}</div>
        <div class="modal-team-name">${match.away_team}</div>
      </div>
      <div class="modal-actions">
        <button class="share-btn" onclick="handleShare(document.querySelector('.share-btn[data-id=\\'${id}\\']'))">🔗 Share</button>
      </div>
    </div>

    ${!isFinished&&!isLive?`
    <div class="modal-section">
      <div class="modal-section-title"><span class="icon">🤖</span> AI Prediction — ${predLabel} (${conf}% confidence)</div>
      <div class="modal-1x2">
        <div class="modal-1x2-row">
          <div class="modal-1x2-outcome">
            <div class="modal-1x2-label">Home (1)</div>
            <div class="modal-1x2-bar"><div class="modal-1x2-fill home" style="width:${hp}%"></div></div>
            <div class="modal-1x2-pct" style="color:var(--accent-green)">${hp}%</div>
            ${ho?'<div class="modal-1x2-odds">'+ho.toFixed(2)+'</div>':''}
          </div>
          <div class="modal-1x2-outcome">
            <div class="modal-1x2-label">Draw (X)</div>
            <div class="modal-1x2-bar"><div class="modal-1x2-fill draw" style="width:${dp}%"></div></div>
            <div class="modal-1x2-pct" style="color:var(--accent-yellow)">${dp}%</div>
            ${do_?'<div class="modal-1x2-odds">'+do_.toFixed(2)+'</div>':''}
          </div>
          <div class="modal-1x2-outcome">
            <div class="modal-1x2-label">Away (2)</div>
            <div class="modal-1x2-bar"><div class="modal-1x2-fill away" style="width:${ap}%"></div></div>
            <div class="modal-1x2-pct" style="color:var(--accent-red)">${ap}%</div>
            ${ao?'<div class="modal-1x2-odds">'+ao.toFixed(2)+'</div>':''}
          </div>
        </div>
      </div>
    </div>`:''}

    ${xg?`
    <div class="modal-section">
      <div class="modal-section-title"><span class="icon">📊</span> Expected Goals & Markets</div>
      <div class="stats-grid">
        <div class="stat-card"><span class="label">xG Total</span><span class="value blue">${xg}</span></div>
        <div class="stat-card"><span class="label">Over 2.5</span><span class="value home">${Math.round((pred.over_25_prob||0)*100)}%</span></div>
        <div class="stat-card"><span class="label">Under 2.5</span><span class="value away">${Math.round((pred.under_25_prob||0)*100)}%</span></div>
        <div class="stat-card"><span class="label">BTTS Yes</span><span class="value home">${Math.round((pred.btts_yes_prob||0)*100)}%</span></div>
        <div class="stat-card"><span class="label">BTTS No</span><span class="value away">${Math.round((pred.btts_no_prob||0)*100)}%</span></div>
        <div class="stat-card"><span class="label">AI Confidence</span><span class="value blue">${conf}%</span></div>
      </div>
    </div>`:''}

    ${csRows?`
    <div class="modal-section">
      <div class="modal-section-title"><span class="icon">⚽</span> Correct Score Probability</div>
      <table class="cs-table">
        <thead><tr><th>Score</th><th>Probability</th></tr></thead>
        <tbody>${csRows}</tbody>
      </table>
    </div>`:''}

    ${htftCards?`
    <div class="modal-section">
      <div class="modal-section-title"><span class="icon">⏱</span> Half-Time / Full-Time</div>
      <div class="htft-grid">${htftCards}</div>
    </div>`:''}

    ${hasOdds?`
    <div class="modal-section">
      <div class="modal-section-title"><span class="icon">💰</span> Betting Odds (AI Implied)</div>
      <div class="odds-comparison">
        <div class="odds-col home"><div class="odds-outcome">Home (1)</div><div class="odds-val">${ho}</div></div>
        <div class="odds-col draw"><div class="odds-outcome">Draw (X)</div><div class="odds-val">${do_}</div></div>
        <div class="odds-col away"><div class="odds-outcome">Away (2)</div><div class="odds-val">${ao}</div></div>
      </div>
    </div>`:''}

    ${weatherIcon||temp?`
    <div class="modal-section">
      <div class="modal-section-title"><span class="icon">🌤️</span> Weather Conditions</div>
      <div class="weather-card">
        <span class="weather-icon-lg">${weatherIcon}</span>
        <div class="weather-info">
          <div class="weather-desc">${weatherDesc}</div>
          ${temp?<div class="weather-temp">${temp}</div>:''}
        </div>
        <div class="weather-meta">${match.league||''}<br>${match.date||''} ${match.time||''}</div>
      </div>
    </div>`:''}

    <div class="modal-section">
      <div class="modal-section-title"><span class="icon">🏆</span> Match Info</div>
      <div class="stats-grid-2">
        <div class="stat-card"><span class="label">League</span><span class="value blue">${match.league||'N/A'}</span></div>
        <div class="stat-card"><span class="label">Country</span><span class="value blue">${match.country||'N/A'}</span></div>
        <div class="stat-card"><span class="label">Date</span><span class="value blue">${match.date||'N/A'}</span></div>
        <div class="stat-card"><span class="label">Status</span><span class="value blue">${status}</span></div>
      </div>
    </div>
  `;

  document.getElementById('modalOverlay').classList.add('open');
  document.body.style.overflow = 'hidden';
}

function closeModal() {
  document.getElementById('modalOverlay').classList.remove('open');
  document.body.style.overflow = '';
}

function handleShare(btn) {
  const id = btn.dataset.id;
  const url = window.location.origin + '/?match=' + id;
  navigator.clipboard.writeText(url).then(() => {
    btn.textContent = '✅ Copied!';
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = '🔗 Share'; btn.classList.remove('copied'); }, 2000);
  }).catch(() => {
    btn.textContent = '❌ Copy failed';
    setTimeout(() => { btn.textContent = '🔗 Share'; }, 2000);
  });
}

// ─── Helpers ───
function showLoading(show) {
  const l = document.getElementById('loadingState');
  const e = document.getElementById('emptyState');
  if (show) { if(l) l.style.display='flex'; if(e) e.style.display='none'; }
  else { if(l) l.style.display='none'; }
}
function showError(msg) {
  document.getElementById('matchGrid').innerHTML = `<div class="empty-state" style="display:grid;grid-column:1/-1;"><span class="empty-icon">⚠️</span><h3>Error</h3><p>${msg}</p></div>`;
}
function renderAccuracy(data) {
  const el = document.getElementById('accuracyValue');
  if (el) el.textContent = (data&&data.accuracy_percent!=null) ? data.accuracy_percent+'%' : 'N/A';
}
function renderLeagues(leagues) {
  const sel = document.getElementById('leagueSelect');
  const first = sel.options[0];
  sel.innerHTML = ''; sel.appendChild(first);
  leagues.forEach(l => { const o = document.createElement('option'); o.value = l.id; o.textContent = `${l.flag||''} ${l.name} (${l.country||''})`; sel.appendChild(o); });
}
function renderStatsBanner() {
  document.getElementById('totalMatches').textContent = state.matches.length;
  const preds = Object.values(state.predictions);
  const avgConf = preds.length ? Math.round(preds.reduce((s,p)=>s+(p.confidence||0),0)/preds.length) : 0;
  const avgEl = document.getElementById('avgConfidence');
  if (avgEl) avgEl.textContent = avgConf > 0 ? avgConf+'%' : '—';
  const acc = state.platformAccuracy;
  const accEl = document.getElementById('platformAccuracy');
  if (accEl) accEl.textContent = (acc&&acc.accuracy_percent!=null) ? acc.accuracy_percent+'%' : '—';
  const tpEl = document.getElementById('totalPredictions');
  if (tpEl) tpEl.textContent = preds.length || '—';
}
