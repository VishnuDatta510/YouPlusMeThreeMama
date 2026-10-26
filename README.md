# Mini-Rayyan

A small Rayyan-style tool for systematic reviews. It searches PubMed, fetches records, removes duplicates, screens each record as Include, Exclude or Maybe with transparent rules, and tags PICO spans in abstracts. Reviewers can override any machine decision, and every override is logged.

- **Frontend**: Next.js (App Router, TypeScript, Tailwind) in [`frontend/`](frontend/), deployed on Vercel
- **Backend**: FastAPI, SQLAlchemy 2, Alembic, Postgres in [`backend/`](backend/), deployed on Railway

Demo login (created on every start): `demo@minirayyan.dev` / `demo1234`

## Run it locally

Prerequisites: Docker, Node 20+, and Python 3.11+ (Python is only needed to run backend tests outside Docker).

```bash
# 1. Postgres + API (runs migrations and seeds the demo reviewer)
docker compose up --build          # API on http://localhost:8000, docs at /docs

# 2. Web app
cd frontend
cp .env.example .env.local         # NEXT_PUBLIC_API_URL=http://localhost:8000
npm install
npm run dev                        # http://localhost:3000
```

To run the backend without Docker (Postgres still from compose):

```bash
docker compose up -d db
cd backend
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env
alembic upgrade head && python -m app.seed
uvicorn app.main:app --reload
```

Setting `NCBI_EMAIL` (and optionally `NCBI_API_KEY`) in your shell before `docker compose up` passes them through to the API.

## Tests

The tests run offline: PubMed is mocked with respx and a saved efetch XML fixture. They need Postgres (not SQLite, because of the JSONB columns). The suite creates a `minirayyan_test` database on whichever server `TEST_DATABASE_URL` points to, defaulting to the compose Postgres on localhost.

```bash
docker compose up -d db
cd backend && ruff check . && ruff format --check . && python -m pytest
cd frontend && npm run lint && npx next typegen && npx tsc --noEmit && npm run build
```

## Environment variables

### Backend (`backend/.env`, Railway service variables)

| Variable | Default | Notes |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5432/minirayyan` | `postgres://` and `postgresql://` URLs are also accepted (Railway's format works as-is) |
| `JWT_SECRET` | `dev-secret-change-me` | **Set a long random value in production.** The API refuses to start with the default when `RAILWAY_ENVIRONMENT` is set |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated list of allowed frontend origins |
| `CORS_ORIGIN_REGEX` | empty | Optional regex for extra origins, for example `https://your-app-.*\.vercel\.app` to allow Vercel preview URLs |
| `NCBI_TOOL` | `mini-rayyan` | Sent with every E-utilities request |
| `NCBI_EMAIL` | empty | Your contact email; NCBI asks for it |
| `NCBI_API_KEY` | empty | Optional; raises the rate limit from 3 to 10 requests/s |
| `MAX_FETCH` | `200` | Maximum PMIDs fetched per query version |
| `PICO_METHOD` | `rules` | PICO tagger; `rules` is the only method so far |
| `SCREENING_CRITERIA` | `non_english,non_human,case_report,simulation` | Active exclusion rules; changing them re-screens on the next run |
| `SEED_EMAIL` / `SEED_PASSWORD` | `demo@minirayyan.dev` / `demo1234` | Demo reviewer, created if missing on start |
| `PORT` | `8000` | Set by Railway |

### Frontend (`frontend/.env.local`, Vercel project env)

| Variable | Example | Notes |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | `https://your-api.up.railway.app` | Backend base URL, no trailing slash |

## How it works

```mermaid
flowchart LR
  subgraph Vercel
    UI[Next.js app]
  end
  subgraph Railway
    API[FastAPI]
    DB[(Postgres)]
  end
  NCBI[(PubMed E-utilities)]
  UI -- JWT / JSON --> API
  API -- esearch / efetch --> NCBI
  API --> DB
```

1. **Preview**: `POST /queries/preview` runs an ESearch count and saves the query as a new **query version**. Each version points to its parent and is never edited.
2. **Fetch and screen**: `POST /queries/{id}/fetch` runs the pipeline. Each step writes a `run_log` row (see `GET /queries/{id}/runs`).
   1. **fetch**: ESearch up to `MAX_FETCH` IDs, then EFetch only PMIDs that are not stored yet. This step is incremental and links every hit to the version.
   2. **dedupe**: exact DOI or PMID match first, then a fuzzy title match (rapidfuzz `token_sort_ratio`) within the same year and first-author block.
      - A score of 95 or more groups the records automatically; 85–95 groups them with a *needs review* flag. The records table marks those representatives with a **review** badge and can filter to them, until a reviewer confirms or rejects the match.
      - The lowest record id is the representative, so results are deterministic.
   3. **screen**: transparent rules (non-English, non-human, case report, simulation). Each result is stored with its `method_version`, so re-runs only screen what is new or what the rules changed.
   4. **pico**: rule-based P/I/C/O spans for included and maybe records with an abstract.
3. **Review**: the records table shows group representatives only. The detail page shows highlighted PICO spans and lets reviewers change status, mark or unmark duplicates (one at a time, or a whole group from its representative), and edit or remove spans. Every action appends a `human_decisions` row and appears in the History panel, where **Restore** re-applies an earlier decision by appending it again. When reviewers' latest screening labels disagree, the record gets a **conflict** badge (and a filter); the newest decision stays in effect until someone resolves it.
4. **Compare versions**: `GET /queries/{id}/diff` (the **Diff** link on the Queries page) lists the records a version gained and lost compared with its parent version.
5. **Export**: `GET /export/included.csv` returns the included studies with PMID, DOI, title, authors, year, journal and PICO text.

**Effective state** is the latest human decision if there is one, otherwise the latest machine result. Nothing is overwritten or deleted, so reverting is just appending an earlier value again.

### Schema

| Table | Purpose |
| --- | --- |
| `reviewers` | Users (bcrypt password hash) |
| `query_versions` | Every query string, date range and hit count, with `parent_version_id` to form a version chain |
| `records` | One row per unique PMID: bibliographic fields, MeSH, publication types, and the raw parsed record (JSONB) |
| `record_query_links` | Which versions returned which records (many to many) |
| `dedup_groups` / `dedup_group_members` | Machine duplicate groups: the representative, plus members with match method, score and `needs_review`. Rebuilt on every run |
| `machine_results` | Append-only screening and PICO outputs per record, tagged with `step` and `method_version` |
| `human_decisions` | Append-only overrides (`screen`, `duplicate`, `pico`) with value, note, reviewer and time. The latest row per record and type wins |
| `run_log` | One row per pipeline step per run: status, timing and details or error |

## CI/CD

- [`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every push and PR.
  - Backend: Python 3.11, ruff, and pytest against a `postgres:16` service.
  - Frontend: Node 20, `npm ci`, lint, `tsc`, and `next build`.
- [`.github/workflows/deploy-backend.yml`](.github/workflows/deploy-backend.yml) runs on pushes to `main` that touch `backend/**`. It reuses the CI workflow, then deploys only if CI passes, using `railway up`. Migrations run when the container starts.
- Vercel deploys the frontend through its GitHub integration: a preview for every PR and production on `main`. [`frontend/vercel.json`](frontend/vercel.json) skips builds when nothing under `frontend/` changed.

## Deploy

### 1. Railway (backend + Postgres)

1. In [railway.com](https://railway.com), create a project with **New Project → Deploy PostgreSQL**.
2. In the project, add the backend with **+ Create → GitHub Repo →** this repository.
3. Open the new service's **Settings**:
   - Set **Source → Root Directory** to `/backend`. Railway then uses `backend/Dockerfile` and `backend/railway.json`, which sets the health check to `/health`.
   - Under **Networking**, click **Generate Domain** and copy the URL.
   - Optional: under **Source**, disconnect the repo, or enable **Wait for CI**. Otherwise Railway's own GitHub auto-deploy runs alongside the GitHub Action, and every push deploys twice.
4. On the service's **Variables** tab, set:
   - `DATABASE_URL` = `${{Postgres.DATABASE_URL}}` (use the reference variable picker)
   - `JWT_SECRET` = a long random string (for example the output of `openssl rand -hex 32`)
   - `NCBI_EMAIL` = your email
   - `CORS_ORIGINS` = `http://localhost:3000` for now; the Vercel URL is added in step 3
   - Optional: `NCBI_API_KEY`, `SEED_PASSWORD` (change the demo password for a public deployment)
5. Create a token: **Project Settings → Tokens →** create a token for the `production` environment.
6. In GitHub, go to **Settings → Secrets and variables → Actions** and add:
   - Secret `RAILWAY_TOKEN` = the project token
   - Secret (or variable) `RAILWAY_SERVICE` = the backend service name as shown in Railway (for example `backend`)
7. Push to `main`, or re-run **Deploy backend** in the Actions tab. Then check that `https://<railway-domain>/health` returns `{"status":"ok"}`.

### 2. Vercel (frontend)

1. In [vercel.com](https://vercel.com), go to **Add New → Project →** import this repository.
2. Set **Root Directory** to `frontend`. The framework preset is detected as Next.js.
3. Add the environment variable `NEXT_PUBLIC_API_URL` = `https://<railway-domain>` (no trailing slash) for Production and Preview.
4. Click **Deploy**.

### 3. Connect them

Set the backend's `CORS_ORIGINS` on Railway to include the Vercel URL, for example `https://your-app.vercel.app,http://localhost:3000`. To let Vercel preview deployments call the API too, also set `CORS_ORIGIN_REGEX` (see the table above). Railway redeploys automatically when variables change. Sign in on the Vercel URL with the demo login.

> Records are retrieved from PubMed via the NCBI E-utilities. This product is not endorsed or certified by NCBI.
