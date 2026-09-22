# Resume Optimizer

Job-fit score, resume suggestions, skill gaps, learning path and interview prep for students.
Architecture, decisions and phases: see [CLAUDE.md](CLAUDE.md).

| Part | Stack | Deploys to |
|---|---|---|
| `frontend/` | Next.js 16 + Tailwind + shadcn/ui | Vercel |
| `backend/` | FastAPI (Python 3.12, uv) | Render free tier (Dockerfile, `render.yaml`) |
| `supabase/` | Postgres, Auth, Storage migrations | Supabase |

**Live:** https://resume-optimizer-ten-virid.vercel.app (API: https://resume-optimizer-api-jzq4.onrender.com)

## Local development

```bash
# backend (http://localhost:8000)
cd backend
cp .env.example .env          # fill SUPABASE_URL at minimum
uv sync
uv run uvicorn app.main:app --reload --port 8000

# frontend (http://localhost:3000)
cd frontend
cp .env.example .env.local    # fill Supabase URL + anon key
pnpm install
pnpm dev
```

Checks: `uv run ruff check . && uv run mypy app tests && uv run pytest` (backend) and
`pnpm lint && pnpm typecheck && pnpm test` (frontend).

Learning resources live in `ingestion/resources_seed.yaml`. After editing it, sync the
database with `uv run python -m scripts.seed_resources` (in `backend/`).

After changing a backend API schema, regenerate the frontend types:
`uv run python -m scripts.export_openapi` (in `backend/`), then `pnpm gen:api` (in `frontend/`).
CI fails if they are out of date.

## One-time setup

### 1. Supabase
1. Create a project at https://supabase.com/dashboard (free tier).
2. Link and apply migrations:
   ```bash
   npx supabase login
   npx supabase link --project-ref <project-ref>
   npx supabase db push
   ```
3. **Authentication → URL Configuration**
   - Site URL: your Vercel URL (or `http://localhost:3000` while developing)
   - Redirect URLs: `http://localhost:3000/auth/callback`, `https://<your-vercel-domain>/auth/callback`
4. **Authentication → Providers → Google** (optional): create an OAuth client in Google Cloud
   Console with authorized redirect URI `https://<project-ref>.supabase.co/auth/v1/callback`,
   then paste the client ID and secret into Supabase and set `NEXT_PUBLIC_ENABLE_GOOGLE_AUTH=true`.
5. **Project Settings → API**: copy the Project URL and the anon/publishable key.

### 2. GitHub
Create an empty repository and push:
```bash
git remote add origin https://github.com/<you>/resume-optimizer.git
git push -u origin main
```

### 3. Render (backend)
Dashboard → **New → Blueprint** → connect the GitHub repo. Render reads `render.yaml`,
builds `backend/Dockerfile` on the free plan and health-checks `/health`.
`ALLOWED_ORIGINS` and `SUPABASE_URL` live in `render.yaml`. In the service's
**Environment** tab, set these secrets (they are declared with `sync: false`):
```
SUPABASE_SERVICE_ROLE_KEY=<Supabase → Project Settings → API Keys → secret key (sb_secret_...)>
OPENAI_API_KEY=<platform.openai.com → API keys>
OPENAI_MODEL_SMALL=<cheap model, used for extraction>
OPENAI_MODEL_LARGE=<optional; defaults to the small model>
```
(`SUPABASE_JWT_SECRET` only if your project still uses legacy HS256 JWT signing.)
The service URL looks like `https://resume-optimizer-api.onrender.com`.
Free services sleep after ~15 min idle; the first request afterwards takes ~30–60 s.

### 4. Vercel (frontend)
Add New Project → import the repo → set **Root Directory** to `frontend`.
Environment variables:
```
NEXT_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon or publishable key>
NEXT_PUBLIC_API_BASE_URL=https://<your-render-domain>
NEXT_PUBLIC_ENABLE_GOOGLE_AUTH=false   # true once step 1.4 is done
```

### 5. Verify (Phase 0 exit)
Open the Vercel URL → sign up / sign in → **Check backend connection** should show
"Backend verified you as <email>".
