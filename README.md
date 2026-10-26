# Mini-Rayyan

A small Rayyan-style tool for systematic reviews. It searches PubMed, fetches records, removes duplicates, screens each record as Include, Exclude or Maybe with transparent rules, and tags PICO spans in abstracts. Reviewers can override any machine decision, and every override is logged.

- **Frontend**: Next.js (App Router, TypeScript, Tailwind) in [`frontend/`](frontend/), deployed on Vercel
- **Backend**: FastAPI, SQLAlchemy 2, Alembic, Postgres in [`backend/`](backend/), deployed on Render

Demo login (created on every start): `demo@minirayyan.dev` / `demo1234`

## Run it locally

Step-by-step guide for teammates, including setup without Docker: [SETUP.md](SETUP.md).

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

### Backend (`backend/.env`, Render service environment)

| Variable | Default | Notes |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5432/minirayyan` | `postgres://` and `postgresql://` URLs are also accepted (Render's format works as-is) |
| `JWT_SECRET` | `dev-secret-change-me` | **Set a long random value in production.** The API refuses to start with the default on Render (where `RENDER` is set). The Blueprint generates one for you |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated list of allowed frontend origins |
| `CORS_ORIGIN_REGEX` | empty | Optional regex for extra origins, for example `https://your-app-.*\.vercel\.app` to allow Vercel preview URLs |
| `NCBI_TOOL` | `mini-rayyan` | Sent with every E-utilities request |
| `NCBI_EMAIL` | empty | Your contact email; NCBI asks for it |
| `NCBI_API_KEY` | empty | Optional; raises the rate limit from 3 to 10 requests/s |
| `MAX_FETCH` | `200` | Maximum PMIDs fetched per query version |
| `PICO_METHOD` | `rules` | PICO tagger; `rules` is the only method so far |
| `SCREENING_CRITERIA` | all eight rules | Default active exclusion rules until a reviewer picks them on the Criteria page |
| `SEED_EMAIL` / `SEED_PASSWORD` | `demo@minirayyan.dev` / `demo1234` | Demo reviewer, created if missing on start |
| `PORT` | `8000` | Set by Render |

### Frontend (`frontend/.env.local`, Vercel project env)

| Variable | Example | Notes |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | `https://mini-rayyan-api.onrender.com` | Backend base URL, no trailing slash |

## How it works

```mermaid
flowchart LR
  subgraph Vercel
    UI[Next.js app]
  end
  subgraph Render
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
- Render deploys the backend from [`render.yaml`](render.yaml) on pushes to `main` that touch `backend/**`, only after CI passes (`autoDeployTrigger: checksPass`). Migrations run when the container starts.
- Vercel deploys the frontend through its GitHub integration: a preview for every PR and production on `main`. [`frontend/vercel.json`](frontend/vercel.json) skips builds when nothing under `frontend/` changed.

## Deploy

### 1. Render (backend + Postgres)

1. Push this repository to GitHub.
2. In [render.com](https://render.com), go to **New → Blueprint**, connect the repository and apply [`render.yaml`](render.yaml). It creates the `mini-rayyan-api` web service (Docker, health check `/health`) and the `mini-rayyan-db` Postgres database, and generates `JWT_SECRET`.
3. Render asks for the variables marked `sync: false`:
   - `NCBI_EMAIL` = your email
   - `SEED_PASSWORD` = a password for the demo login (use something other than `demo1234` on a public site)
   - `CORS_ORIGINS` = `http://localhost:3000` for now; the Vercel URL is added in step 3
   - `CORS_ORIGIN_REGEX` = leave empty or see the table above
4. When the deploy is live, check that `https://<service>.onrender.com/health` returns `{"status":"ok"}`.

The free plan sleeps after 15 minutes without traffic (the first request takes about a minute), and a free Postgres database expires after 30 days unless you upgrade it.

### 2. Vercel (frontend)

1. In [vercel.com](https://vercel.com), go to **Add New → Project →** import this repository.
2. Set **Root Directory** to `frontend`. The framework preset is detected as Next.js.
3. Add the environment variable `NEXT_PUBLIC_API_URL` = `https://<service>.onrender.com` (no trailing slash) for Production and Preview.
4. Click **Deploy**.

### 3. Connect them

Set the backend's `CORS_ORIGINS` on Render (**Environment** tab) to include the Vercel URL, for example `https://your-app.vercel.app,http://localhost:3000`. To let Vercel preview deployments call the API too, also set `CORS_ORIGIN_REGEX`. Save and redeploy, then sign in on the Vercel URL with the demo login.

> Records are retrieved from PubMed via the NCBI E-utilities. This product is not endorsed or certified by NCBI.
