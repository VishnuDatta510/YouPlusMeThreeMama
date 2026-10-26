# Setup guide for the team

How to get Mini-Rayyan running on your own machine. Pick the path that matches what you're working on.

| You want to work on | You need | Go to |
|---|---|---|
| Only the frontend (pages, design) | Node 20+ | [Path A](#path-a-frontend-only-no-docker-no-python) |
| The backend, or everything | Node 20+, Python 3.11+, and Postgres (Docker or installed) | [Path B](#path-b-full-stack) |

Just want to look at the app? Open https://mini-rayyan.vercel.app. Nothing needs installing.

```bash
git clone <repo-url>
cd <repo-folder>
```

## Path A: frontend only (no Docker, no Python)

Your local frontend talks to the live API on Render.

```bash
cd frontend
echo NEXT_PUBLIC_API_URL=https://mini-rayyan-api.onrender.com > .env.local
npm install
npm run dev
```

Open http://localhost:3000 and sign in with `demo@minirayyan.dev`. Ask Vishnu for the password.

> **Careful:** this is the real production data. Every fetch, screening decision or PICO edit you make is saved there for good, because nothing is ever deleted. To experiment freely, use Path B.

The first request after a quiet spell can take about 30 seconds while Render wakes up.

## Path B: full stack

### 1. Postgres

You need a Postgres 14+ server with a database called `minirayyan`. SQLite will **not** work, because the backend uses Postgres-only features. Choose one option:

**Option 1, Docker (easiest).** Install Docker Desktop and start it, then run this from the repo root:
```bash
docker compose up -d db
```
That gives you `postgres:postgres@localhost:5432/minirayyan`, which matches the defaults, so there's nothing to configure.

**Option 2, Postgres installed directly (no Docker).**
- Windows: the installer from https://www.postgresql.org/download/windows/. Set the password to `postgres` to keep the defaults.
- macOS: `brew install postgresql@16 && brew services start postgresql@16`
- Linux: `sudo apt install postgresql`

Then create the database:
```bash
psql -U postgres -c "CREATE DATABASE minirayyan;"
```
If your user or password isn't `postgres`/`postgres`, set `DATABASE_URL` in `backend/.env` (see step 2).

**Option 3, a free hosted Postgres** (Neon, Supabase and similar). Put its connection string in `DATABASE_URL` in `backend/.env`.

> Never point your local backend at the Render production database.

### 2. Backend (http://localhost:8000)

```bash
cd backend
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env        # optional: the defaults already work with Option 1
alembic upgrade head        # create the tables
python -m app.seed          # create the demo login: demo@minirayyan.dev / demo1234
uvicorn app.main:app --port 8000
```

Check it's up: http://localhost:8000/health should return ok, and http://localhost:8000/docs shows every endpoint.

Put your own email in `NCBI_EMAIL` in `.env` (PubMed asks for it). An `NCBI_API_KEY` is optional: it raises PubMed's limit from 3 to 10 requests a second.

`uvicorn --reload` is unreliable on Windows, so restart uvicorn by hand after backend changes.

### 3. Frontend (http://localhost:3000)

```bash
cd frontend
npm install
npm run dev
```

With no `.env.local`, the frontend talks to `http://localhost:8000`. Sign in with `demo@minirayyan.dev` / `demo1234`.

### 4. Try it

1. On **Searches**, type `metformin AND type 2 diabetes`, set a date range, and click **Count hits**.
2. Click **Fetch and screen**.
3. Open **Records** to review the results.

## Before you commit

Run the same checks as CI. Both need to pass.

```bash
# backend (needs Postgres running; tests create their own minirayyan_test database)
cd backend && ruff check . && ruff format --check . && python -m pytest

# frontend
cd frontend && npm run lint && npx next typegen && npx tsc --noEmit && npm run build
```

The backend tests run offline: PubMed and Europe PMC are mocked.

## Pushing

**Every push to `main` deploys** to Render (API) and Vercel (web), so only push work that passes the checks above. For anything bigger, use a branch and a PR.

## Common problems

| Problem | Fix |
|---|---|
| `connection refused` on port 5432 | Postgres isn't running. Start Docker Desktop and run `docker compose up -d db`, or start your installed Postgres service. |
| `database "minirayyan" does not exist` | Run `psql -U postgres -c "CREATE DATABASE minirayyan;"` |
| `password authentication failed` | Your Postgres login isn't `postgres`/`postgres`. Set `DATABASE_URL` in `backend/.env`. |
| Login fails locally | Run `python -m app.seed` in `backend/`. |
| Browser shows a CORS error | The frontend must run on http://localhost:3000, or add your origin to `CORS_ORIGINS` in `backend/.env`. |
| Port 5432 already in use when starting Docker | You already have a Postgres installed. Use that one (Option 2) or stop it. |
