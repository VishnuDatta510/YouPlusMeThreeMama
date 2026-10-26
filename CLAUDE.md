# Mini-Rayyan: Claude notes

Hackathon Track 1 (Oct 24 2026, 72 h). A small Rayyan for systematic reviews. The pipeline:
question → query → fetch → database → dedupe → screen → PICO → review and export.
Full spec: `mini-rayyan-claude-code-prompt.md`. User-facing docs: `README.md`.

## Rules from the problem statement (do not break)
- Nothing is ever deleted. Duplicates and exclusions are hidden and marked, never removed.
- Machine outputs (`machine_results`, tagged with `method_version`) are stored apart from human decisions (`human_decisions`, append-only).
- A human can override any duplicate, exclusion or PICO span, and every change is logged. Effective state is the latest human decision, else the latest machine result. Revert means appending an earlier value again.
- Every exclusion has a visible reason, and each criterion can be switched off (`SCREENING_CRITERIA`).
- A later report of the same study is not a duplicate. Only the same record is.
- Working beats clever. Judges run unseen queries, so nothing may be hardcoded to the demo query.

## Level 2 loop
- Editing a query creates a new query version (`parent_version_id`). Versions are never edited.
- Fetch is incremental: only PMIDs not yet stored are fetched. `record_query_links` is many-to-many.
- Dedupe reruns on the combined set. Groups are rebuilt each run, with the lowest id as representative.
  - Exact DOI or PMID match first, then fuzzy title within year + first author.
  - A score of 95 or more groups automatically; 85–95 is flagged `needs_review`.
- Screening and PICO rerun only on records that are new or whose `method_version` changed.
- Decisions follow the group. A conflict badge shows when reviewers disagree.
- Diff view lists added, removed and newly merged records. Reverting to v1 must give the same records and groups.
- Each pipeline step writes a `run_log` row.

## Sources
- PubMed E-utilities: at most 3 requests/s, 10 with `NCBI_API_KEY`. Send `NCBI_TOOL` and `NCBI_EMAIL`. Keep the NCBI disclaimer in the footer.
- Europe PMC (`europepmc.py`) is the second source; no key needed, with retries and backoff.
- PICO is rule-based (`pico.py`, rules-v5). `PICO_METHOD` is the hook for an LLM tagger, which is also not built yet.

## Deliverables
A README a stranger can rerun, a report of at most 3 pages, a one-page loop design, and a 5-minute demo.

## Stack and commands
- `backend/`: FastAPI, SQLAlchemy 2, Alembic, Postgres only (JSONB, DISTINCT ON). Not Mongo, not SQLite.
- `frontend/`: Next.js 16 App Router, React 19, Tailwind v4. Read `frontend/AGENTS.md`; the Next APIs differ from older versions.
- Start the database: `docker compose up -d db`.
- Backend checks: `cd backend && ruff check . && ruff format --check . && python -m pytest`. Tests run offline: respx mocks PubMed against a real Postgres test DB.
- Frontend checks: `cd frontend && npm run lint && npx next typegen && npx tsc --noEmit && npm run build`.

## Workflow
- Commit after each feature, once tests and linters pass.
- Git author is Vishnu Datta <vishnudatta2004@gmail.com>. Never add a `Co-Authored-By` trailer.
- Do not push unless the user says to. Every push to `main` deploys.
- Keep it minimal. Mark deliberate shortcuts with a `# ponytail:` comment.

## Deploy (live)
- API: https://mini-rayyan-api.onrender.com
  - Render service `srv-dbfpctajnfac73fq1jc0`: Docker, Singapore, free plan, auto-deploys on every commit.
  - At startup the container runs migrations, then the seed, then uvicorn.
- DB: Render Postgres `dpg-dbfpcl0m7kps7389gvn0-a`, free, **expires 2026-11-25**. Workspace `tea-d456389r0fns73di2450`.
- Web: https://mini-rayyan.vercel.app
  - Vercel project `mini-rayyan`, root directory `frontend`.
  - `NEXT_PUBLIC_API_URL` is baked in at build time.
  - `vercel.json` skips builds that change nothing under `frontend/`.
- `.github/workflows/keep-awake.yml` pings `/health` every 10 minutes so the free instance does not sleep. The 750 free hours are shared across the whole workspace.
- The API refuses to start on Render while `JWT_SECRET` is the default. `CORS_ORIGINS` and `CORS_ORIGIN_REGEX` allow the Vercel production and preview URLs.
- Demo login: `demo@minirayyan.dev`. The production password is in `SEED_PASSWORD` on Render.
- `render.yaml` is unused (the services were created by hand). Applying it would create a second DB.

## Gotchas
- Windows Git Bash: prefix `vercel api /path` with `MSYS_NO_PATHCONV=1`. Write files with LF line endings.
- `uvicorn --reload` is unreliable here, so restart it by hand.
- Right after a deploy, Render can return `x-render-routing: no-server` 404s for about a minute. That is not a code bug.
