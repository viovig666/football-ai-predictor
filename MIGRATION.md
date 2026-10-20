# Platform Migration Research — Football AI Predictor
*Started: 2026-10-20 | Railway outage context*

---

## What We're Working With

**Stack:**
- Flask 3.0 + Gunicorn (Python 3.11)
- ML: scikit-learn 1.3.2, XGBoost 2.1.3, pandas, numpy
- Data: SQLite (`data/predictions.db`)
- External APIs: football-data.org (env var `FOOTBALL_DATA_API_KEY`)
- Browser scraping: DrissionPage 4.x (headless Chromium)
- Current Dockerfile: `python:3.11-slim` base

**Current config (railway.json):**
```json
{
  "build": { "builder": "DOCKERFILE" },
  "deploy": {
    "startCommand": "gunicorn --bind 0.0.0.0:${PORT:-8080} --timeout 120 app:app",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

**Key constraints:**
1. **SQLite file persistence** — DB must survive restarts (Railway Persistent Disk)
2. **DrissionPage headless Chromium** — needs browser installed in image
3. **Secrets** — `FOOTBALL_DATA_API_KEY` must stay in env vars, never in repo
4. **PORT env var** — Railway injects `${PORT}`, gunicorn listens on it
5. **Startup timeout 300s** — models train on first boot

---

## Platform Comparison

### Render (⭐ RECOMMENDED)

| Factor | Details |
|--------|---------|
| **Free tier** | 750 hrs/month shared CPU, expires Feb 2026 |
| **Docker** | ✅ Full Docker support |
| **Persistent disk** | ✅ Render Disks — attach to service |
| **Health checks** | ✅ Built-in `/health` endpoint support |
| **CLI deploy** | `render deploy` — different code path than Railway |
| **SQLite** | ✅ Works with Persistent Disk |
| **DrissionPage** | ✅ Full browser in Docker, no sandbox restrictions |
| **Secrets** | ✅ Encrypted env vars in dashboard |
| **Auto-deploy** | ✅ GitHub push triggers rebuild |
| **Downtime on migrate** | Zero — blue/green, no old container killed until new is up |

**Migrate effort:** Low. Swap `railway.json` → `render.yaml`. Attach disk. Set env vars. Done.

**Start command:** `gunicorn --bind 0.0.0.0:10000 --timeout 300 app:app`
*(Render exposes service on port 10000 by default)*

**.render.yaml example:**
```yaml
services:
  - type: web
    name: football-ai-predictor
    env: docker
    region: frankfurt
    plan: free
    dockerfilePath: ./Dockerfile
    healthCheckPath: /
    envVars:
      - key: FOOTBALL_DATA_API_KEY
        sync: false  # enter value manually in dashboard
    disk:
      - name: data
        mountPath: /app/data
        sizeGB: 1
```

**Issues:** DrissionPage logs show it can be heavy — may need to tune `startupTimeout` and `timeouts` in the scraper code. Also, Render's free tier is "shared CPU" — fine for this workload. ⚠️ **NOTE:** Render free tier auto-sleeps after 15 min of inactivity. Add a uptime monitor or cron ping to keep it warm.

---

### Vercel

| Factor | Details |
|--------|---------|
| **Free tier** | 100GB bandwidth/month, serverless functions |
| **Docker** | ❌ No native Docker support (uses serverless functions) |
| **Python** | ✅ Python via Flask + serverless adapter |
| **SQLite** | ❌ Ephemeral filesystem — DB wipes on cold start |
| **DrissionPage** | ❌ No headless browser in serverless |
| **Auto-deploy** | ✅ GitHub push |
| **Downtime** | Zero — serverless |

**Verdict:** ❌ Ruled out. DrissionPage + SQLite both need persistent filesystem. Can't work.

---

### DigitalOcean App Platform

| Factor | Details |
|--------|---------|
| **Free tier** | $0/month for 30 days, then $5/month minimum |
| **Docker** | ✅ App Platform supports Dockerfile deploy |
| **Persistent storage** | ✅ Spaces (S3-compatible) for DB, or bind mount |
| **DrissionPage** | ✅ Full Docker with browser |
| **Auto-deploy** | ✅ GitHub integration |
| **CLI deploy** | `doctl apps create` / `doctl apps update` |
| **SQLite** | ✅ Bind mount to volume |

**Migrate effort:** Medium. Need to set up App Spec YAML, create DO account, migrate env vars.

**app.yaml example:**
```yaml
alerts:
  - rule: DEPLOYMENT_FAILED
  - rule: DOMAIN_NOT_RESOLVED
services:
  - name: web
    github:
      repo: viovig666/football-ai-predictor
      branch: main
      deploy_on_push: true
    dockerfile_path: ./Dockerfile
    instance_count: 1
    instance_size_slug: basic-xxs
    region: ams
    envs:
      - key: FOOTBALL_DATA_API_KEY
        type: SECRET
      - key: PORT
        value: 8080
    routes:
      - path: /
    health_check:
      path: /
    volumes:
      - mount_path: /app/data
        volume_name: data
        size_gb: 1
```

**Verdict:** ✅ Viable. More setup than Render but reliable and predictable pricing.

---

### Fly.io

| Factor | Details |
|--------|---------|
| **Free tier** | 3 shared VMs, 160GB outbound bandwidth |
| **Docker** | ✅ Native Docker support |
| **Persistent storage** | ✅ Fly Volumes (attach to VM) |
| **DrissionPage** | ✅ Full browser in Docker VM |
| **Auto-deploy** | ✅ `fly deploy` from CLI |
| **CLI** | Great CLI, good docs |
| **SQLite** | ✅ Fly Volume persistence |

**Migrate effort:** Medium. Need Fly.io account + `flyctl` CLI + volume setup.

**Verdict:** ✅ Viable and robust. Better than Render for long-running Flask apps. Slightly steeper learning curve than Render.

---

### Railway (current)

| Factor | Details |
|--------|---------|
| **Status** | Platform-wide build outage since Oct 20, 17:18 UTC |
| **Recovery** | Unknown ETA |
| **Free tier** | $5 credit/month, then paid |
| **Reliability** | ⚠️ Known for间歇性 outages |
| **Docker** | ✅ Full support |
| **SQLite** | ✅ Persistent Disks |
| **DrissionPage** | ✅ Full browser |
| **Auto-deploy** | ✅ GitHub push |

**Verdict:** Railway is convenient but unreliable for production. Good for hobbyist projects, poor for anything with real users.

---

## Migration Path Recommendation

### Option A — Render (Fastest, recommended for now)
- Already supports Docker, Flask, persistent disk, env vars
- `render.yaml` is ~15 lines, essentially a drop-in replacement for `railway.json`
- Zero-code-change migration
- CLI uses `render deploy` which bypasses Railway's throttle issues entirely
- **Downside:** Free tier sleeps after 15min inactive (need uptime monitor or cron)

### Option B — DigitalOcean App Platform (Most stable long-term)
- Predictable $5/month after trial
- Better uptime SLA than Render free
- App Spec YAML is more verbose than Render but well-documented
- No auto-sleep issue
- **Downside:** Requires DO account, slightly more setup

### Option C — Fly.io (Most "pro")
- Best for apps that need real VMs without the overhead of full Kubernetes
- Volumes = proper persistent SQLite
- Great CLI, no GitHub integration required
- **Downside:** Steeper learning curve, needs `flyctl` setup

---

## Immediate Action Items (Before Migrating)

1. **DrissionPage timeout issue** — Current logs show `[DrissionPage] WARNING: [api_predict] match_id=1 enrichment` with timeouts. Check `data/flashscore.py` and `data/team_stats.py` for hardcoded 15-20s timeouts that may fail on slow boot.

2. **Model version mismatch** — Build logs show `InconsistentVersionWarning: Trying to unpickle estimator LogisticRegression from version 1.8.0 when using version 1.3.2`. Retrain models in-container or pin sklearn==1.8.0 in requirements.txt. **Predictions are degraded right now on the live site.**

3. **PORT env var** — Gunicorn bind must use `${PORT:-8080}` for Railway but Render uses port `10000`. Set `PORT=10000` in the new platform's env vars, or hardcode `8080` if the platform injects it differently.

4. **`/api/retrain` endpoint** — This endpoint exists at `app.py` but triggers model rebuild at runtime. On a persistent-disk platform this works fine. On ephemeral storage it would lose models on restart.

---

## Migration Checklist (Render as example)

- [ ] Create Render account at render.com
- [ ] Create new Web Service → Deploy from GitHub repo
- [ ] Select `Dockerfile` as build type
- [ ] Add env var: `FOOTBALL_DATA_API_KEY` (sync: false, enter manually)
- [ ] Add Persistent Disk: mount at `/app/data`, 1GB
- [ ] Set start command: `gunicorn --bind 0.0.0.0:10000 --timeout 300 app:app`
- [ ] Set health check path: `/` or `/api/matches`
- [ ] Remove `FOOTBALL_DATA_API_KEY` from Railway env vars (security cleanup)
- [ ] Update `BUILD.md` and `MIGRATION.md` with new platform notes
- [ ] Test locally first: `docker build -t footpredict . && docker run -p 8080:8080 -e FOOTBALL_DATA_API_KEY=xxx footpredict`

---

## Verdict

**If Railway comes back today** → Deploy fix `b7e480b`, then plan migration to Render/DO in parallel.

**If Railway stays down** → Migrate to Render. It takes ~30 minutes to have a fully working deployment with persistent disk, no code changes needed.

**The ONE non-negotiable fix before any platform work:** Retrain models with the correct scikit-learn version. The current live site is running degraded predictions due to the version mismatch.

