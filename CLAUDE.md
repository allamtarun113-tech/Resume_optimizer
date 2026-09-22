# CLAUDE.md — Resume Optimizer

This file guides Claude Code (and humans) working in this repository. The original product brief is in `Idea.txt`. This file holds the **decisions** made from that brief. If they conflict, this file wins, unless the user says otherwise.

---

## 1. What we are building

Resume Optimizer is a job-readiness app for students. It takes:

- **Resume** (PDF)
- **Job Description** (text)
- **Additional skills / experience** (free text)
- **Supporting documents** (PDF, DOCX or pasted text), such as projects or experience missing from the resume

It produces:

1. **Job Fit Score (%)**, which must be deterministic. The LLM only extracts facts, and Python computes the score.
2. **Resume improvement suggestions**. These cover things the student *already has* (found in the supplementary material) but hasn't shown in the resume. Each suggestion comes with a **projected score increase**.
3. **Skill gaps**: JD requirements with *no evidence anywhere* in the student's profile. These are kept strictly separate from #2.
4. **Learning path**: ordered topics (prerequisites first) with curated resources, tied to the target JD.
5. **"Prepare Me for Interview"**: questions (no answers) in three groups: Personal/Background (with *very deep* project drill-downs), Job-Specific Technical, and General/Behavioral. Questions are **retrieved from real sources** (RAG + MCP), not freely invented by an LLM.

### Non-negotiable product rules
- **Never fabricate qualifications.** Every resume suggestion must point to a source snippet from the student's own inputs. A Python validator rejects any suggestion whose cited evidence is not found in the source text.
- **"Missing from resume" ≠ "Skill gap".** If there is evidence in the supplementary material, it goes to *resume suggestion*. If there is no evidence anywhere, it goes to *skill gap → learning path*.
- **The score must be reproducible.** The same inputs must always give the same score (see §5).
- **Use as few LLM calls as possible.** Use Python whenever a task does not truly need language understanding.

---

## 2. Tech stack (decided)

| Layer | Choice |
|---|---|
| Frontend | **Next.js (App Router) + TypeScript + Tailwind CSS + shadcn/ui**, deployed on **Vercel** |
| Backend | **Python 3.12 + FastAPI**, deployed on **Render** free web service (single Docker service; sleeps when idle, so the first request after ~15 min is slow) |
| Agent orchestration | **Plain Python async orchestrator** (no LangGraph/CrewAI). Each agent is a small class with a typed input/output |
| LLM | **OpenAI API** through the official `openai` SDK, with **Structured Outputs** (JSON schema / Pydantic) |
| Embeddings | **OpenAI `text-embedding-3-small`** (1536 dims) |
| DB / Auth / Storage | **Supabase**: Postgres + **pgvector**, Supabase Auth (email + Google), Supabase Storage for uploaded files |
| MCP | Our own **FastMCP server** (Python, mounted in the FastAPI app) + the **GitHub MCP server** for ingesting question repos |
| Source control / CI / CD | **GitHub** repo. GitHub Actions for lint and tests. Vercel and Render auto-deploy from `main` |
| Python tooling | `uv` for dependencies, `ruff` (lint + format), `mypy`, `pytest` |
| Frontend tooling | `pnpm`, ESLint, Prettier, Vitest (unit), Playwright (optional e2e) |

### LLM model policy
- Model names are **never hard-coded**. Each agent reads its model from env/config (`OPENAI_MODEL_SMALL`, `OPENAI_MODEL_LARGE`).
- The default is the **small/cheap OpenAI model** for everything. The larger model is used only where testing shows it is needed (likely the Resume Advisor and project deep-dive question adaptation).
- For determinism, use `temperature=0` (when the model supports it), a fixed `seed`, and strict JSON schema output. Also **cache every LLM result** by input hash (§7).

---

## 3. Repository layout (target)

```
resume-optimizer/
├── CLAUDE.md
├── Idea.txt
├── frontend/                     # Next.js app (Vercel root dir = frontend)
│   ├── app/                      # routes: /, /login, /analyze, /analysis/[id], /interview/[id], /history
│   ├── components/               # shadcn/ui + feature components
│   ├── lib/                      # supabase client, api client, types
│   └── ...
├── backend/                      # FastAPI app (Render root dir = backend, see render.yaml)
│   ├── app/
│   │   ├── main.py               # FastAPI app, routers, MCP mount
│   │   ├── api/                  # routers: uploads, analyses, interview, resources, health
│   │   ├── core/                 # config (pydantic-settings), auth (Supabase JWT verify), logging
│   │   ├── agents/               # one module per agent (see §4)
│   │   ├── orchestrator/         # pipeline that runs agents in order / in parallel
│   │   ├── scoring/              # deterministic scoring engine (pure Python, 100% unit-tested)
│   │   ├── parsing/              # PDF/DOCX/text extraction (no LLM)
│   │   ├── skills/               # taxonomy (data/skills_taxonomy.json), normalization (no LLM)
│   │   ├── rag/                  # embeddings, pgvector search, rerank
│   │   ├── mcp_server/           # FastMCP tools: question bank + learning resources
│   │   ├── llm/                  # OpenAI wrapper: caching, token accounting, retries, schemas
│   │   ├── db/                   # Supabase/Postgres access (repositories)
│   │   └── schemas/              # Pydantic models shared across agents & API
│   ├── tests/
│   └── pyproject.toml
├── ingestion/                    # offline scripts (run locally or via GitHub Action)
│   ├── fetch_question_repos.py   # uses GitHub MCP to pull question markdown
│   ├── parse_questions.py        # markdown -> normalized question records
│   ├── embed_and_load.py         # embeddings -> Supabase pgvector
│   ├── sources.yaml              # allow-listed repos + licenses
│   └── resources_seed.yaml       # curated learning resources
├── supabase/
│   ├── migrations/               # SQL migrations (tables, pgvector, RLS)
│   └── seed.sql
└── .github/workflows/            # ci.yml (lint+test both apps), ingest.yml (manual trigger)
```

---

## 4. Multi-agent architecture

The orchestrator is plain Python (`asyncio`). "Agent" means a unit with **one responsibility**, a **Pydantic input and output**, and an explicit flag for whether it uses the LLM. Agents that don't use the LLM are ordinary Python.

| # | Agent | LLM? | Responsibility |
|---|---|---|---|
| 1 | **DocumentParser** | ❌ | Extract text from PDF (`pdfplumber`, falling back to `pypdf`), DOCX (`python-docx`) and pasted text. Split into sections (Education, Experience, Projects, Skills…) using heuristics |
| 2 | **ProfileExtractor** | ✅ small | Resume and supplementary text → `StudentProfile` JSON (skills, projects with full technical detail, experience, education, certifications). Each item is tagged with its **source** (`resume` \| `supplementary:<doc_id>`) and a verbatim **evidence snippet** |
| 3 | **JDAnalyzer** | ✅ small | JD text → `JobRequirements` JSON: each requirement has `name`, `category` (skill/tool, domain knowledge, experience, education, soft skill), `importance` (must/nice), and `min_years` if stated |
| 4 | **SkillNormalizer** | ❌ | Map extracted skills and requirements to canonical IDs using `skills_taxonomy.json` + `rapidfuzz`. Items it can't map go to Matcher |
| 5 | **Matcher** | ⚠️ minimal | Requirement ↔ evidence matching. Order: exact canonical match → fuzzy → embedding cosine similarity → **one batched LLM call** only for the remaining ambiguous pairs |
| 6 | **Scorer** | ❌ | Deterministic Job Fit Score + per-suggestion projected uplift (§5) |
| 7 | **GapClassifier** | ❌ | Put each requirement in one bucket: `strong_in_resume`, `weak_in_resume`, `missing_from_resume_but_evidenced`, or `true_gap` |
| 8 | **ResumeAdvisor** | ✅ | Writes suggestions **only** for the `weak_in_resume` and `missing_from_resume_but_evidenced` buckets. Must cite evidence IDs. Output goes through the **EvidenceValidator** (Python) |
| 9 | **LearningPathPlanner** | ✅ small | For `true_gap` items: build the prerequisite order (taxonomy graph first, LLM only to break ties or fill gaps), then attach resources via the MCP tool `get_learning_resources`. The LLM **never writes URLs** |
| 10 | **InterviewPrep** | ✅ | Runs when the user clicks "Prepare Me for Interview" (lazy, separate endpoint). Retrieves questions via MCP tools (§6). The LLM only **selects, dedupes and fills templates** with the student's project details. Every question keeps its `source` |

**Pipeline (POST /analyses):**
```
Parser ─┬─> ProfileExtractor ─┐
        └─> JDAnalyzer ───────┴─> SkillNormalizer → Matcher → Scorer → GapClassifier
                                                                         ├─> ResumeAdvisor
                                                                         └─> LearningPathPlanner   (parallel)
```
ProfileExtractor and JDAnalyzer run in parallel. ResumeAdvisor and LearningPathPlanner also run in parallel. InterviewPrep runs only on demand.

**Execution model:** the analysis runs as a FastAPI background task. Its status (`queued → parsing → extracting → scoring → advising → done|failed`) is stored in `analyses.status`. The frontend listens with **Supabase Realtime** on that row, or falls back to polling.

---

## 5. Deterministic Job Fit Score

The LLM gives **facts**. Python gives **numbers**.

For each requirement `r` from the JD:

- Weight: `w_r = importance_weight × category_weight`
  - importance: `must = 3`, `nice = 1`
  - category: skill/tool `1.0`, domain `0.9`, experience `1.0`, education `0.6`, soft skill `0.4`
- Evidence strength in the **resume** `s_r`:
  - `1.0`: explicitly listed **and** shown in a project or experience
  - `0.7`: explicitly listed only (skills section)
  - `0.4`: implied or weakly stated in the resume
  - `0.0`: not in the resume
- Experience years: `s_r = min(1, candidate_years / min_years)`

**Job Fit Score** = `round(100 × Σ w_r·s_r / Σ w_r)`

**Projected uplift for a suggestion:** recompute the score with `s_r` raised to the level the supplementary evidence supports (usually `1.0`). Uplift = `new_score − current_score`. Show the uplift for each suggestion and a total "potential score".

Rules:
- All constants live in `backend/app/scoring/weights.py`, versioned (`SCORING_VERSION`). Every stored analysis records the version used.
- `scoring/` is pure Python with **no I/O**. It gets 100% unit-test coverage, including property tests (e.g. adding evidence never lowers the score).
- LLM extraction results are cached by `sha256(normalized_input + prompt_version + model)`. The same resume and JD therefore give the same extraction and the same score.

---

## 6. RAG + MCP for interview questions and learning resources

### Question corpus (ingestion, offline)
- `ingestion/sources.yaml` lists allow-listed public GitHub repos of interview questions. Only use repos with permissive licenses, and record each repo's license. Examples to evaluate: general/behavioral banks, role-specific banks (ML, backend, frontend, data, DevOps), and system-design banks.
- `fetch_question_repos.py` uses the **GitHub MCP server** (tools like `get_file_contents` / `search_code`) to pull the markdown files.
- `parse_questions.py` normalizes each record: `{text, category: personal|technical|general|project_template, topics[], role_tags[], difficulty, source_repo, source_path, license}`. Deduplicate using normalized-text hashes plus embedding similarity above 0.95.
- `embed_and_load.py` embeds with `text-embedding-3-small` and upserts into `interview_questions` (pgvector).
- Also add a hand-curated **project deep-dive template bank** (e.g. "Why did you choose {tech} over alternatives for {project}?", "How did you evaluate {model} in {project}?", "What would break first if {project} had 100× traffic?"). Deep project questions come from these templates, filled with the student's real project details. Aim for 8–15 questions per project, across architecture, data, trade-offs, failures, metrics, testing, deployment and "what would you change".
- Ingestion runs manually (a `workflow_dispatch` GitHub Action or a local script), **never** during user requests.

### Our MCP server (`backend/app/mcp_server/`, FastMCP, mounted at `/mcp`)
Tools:
- `search_interview_questions(query, category, role_tags, topics, k)`: pgvector similarity + metadata filters
- `get_project_question_templates(project_facets)`: returns deep-dive templates relevant to the project's tech and domain
- `get_general_questions(k, seed)`: behavioral/HR questions, sampled deterministically per analysis
- `get_learning_resources(skill_ids)`: curated resources from the `learning_resources` table
- `get_skill_prerequisites(skill_id)`: prerequisite graph from the taxonomy

The InterviewPrep and LearningPathPlanner agents call these through an **MCP client**. That keeps the data sources swappable and lets the same tools be used from Claude Desktop or other MCP clients for debugging. The MCP server is in-process, so it adds no extra hosting cost.

### Learning resources
- The `learning_resources` table is seeded from `ingestion/resources_seed.yaml`. It prefers free, reputable sources: official docs, freeCodeCamp, MIT OCW, fast.ai, Kaggle Learn, roadmap.sh, CS50, Google/Microsoft free courses.
- Fields: `skill_id, title, url, type (docs/course/video/book/practice), level, est_hours, free (bool)`.
- The LLM orders topics and writes short "why this next" notes. URLs always come from the DB.

---

## 7. Cost and token-efficiency rules (enforce in code review)

1. **Python first.** Parsing, normalization, matching, scoring, gap classification and dedup never use the LLM.
2. **Structured Outputs only.** No free-form LLM text that needs parsing afterwards.
3. **Cache everything.** Keep an `llm_cache` table keyed by `(prompt_version, model, input_hash)`. Cache embeddings by text hash too.
4. **Send only what's needed.** Agents get the relevant sections or JSON, never whole raw documents when extracted JSON exists. Downstream agents get the `StudentProfile` JSON, not raw resume text.
5. **Batch.** Handle ambiguous matches and suggestion drafting in single calls, not one call per item.
6. **Lazy features.** InterviewPrep runs only on button click, and its output is stored for reuse.
7. **Budgets.** Each agent has a `max_output_tokens`. Each user has a daily analysis limit (`DAILY_ANALYSIS_LIMIT`, default 10).
8. **Accounting.** Every LLM call logs `{agent, model, input_tokens, output_tokens, cached, latency_ms, analysis_id}` to `llm_calls`. The target is **< $0.01 per analysis** on the small model.
9. **Prompt versions.** Prompts live in `backend/app/agents/prompts/*.md` with a `PROMPT_VERSION`. Changing a prompt means bumping the version.

---

## 8. Data model (Supabase, with RLS on every user table)

- `profiles` (id = auth.users.id, name, created_at)
- `documents` (id, user_id, kind: resume|supporting|jd|extra_text, storage_path, extracted_text, text_hash, created_at)
- `analyses` (id, user_id, resume_doc_id, jd_doc_id, supporting_doc_ids[], status, fit_score, potential_score, scoring_version, prompt_versions jsonb, created_at)
- `analysis_results` (analysis_id, student_profile jsonb, job_requirements jsonb, matches jsonb, suggestions jsonb, gaps jsonb, learning_path jsonb)
- `interview_sets` (id, analysis_id, questions jsonb (each with category + source), created_at)
- `interview_questions` (id, text, category, topics[], role_tags[], difficulty, source_repo, source_path, license, embedding vector(1536))
- `learning_resources` (id, skill_id, title, url, type, level, est_hours, free)
- `llm_cache` (key, response jsonb, created_at), `llm_calls` (usage log)

Storage bucket `uploads/` is private and keyed by `user_id/`. The backend reads it with the service role, and the frontend uses signed URLs only.

**Auth flow:** the frontend signs in with Supabase Auth and sends `Authorization: Bearer <supabase_jwt>` to FastAPI. FastAPI verifies the JWT (Supabase JWKS / JWT secret) and scopes every query to `user_id`.

---

## 9. API (FastAPI)

- `POST /documents` (multipart): upload a resume or supporting doc, or send pasted text → `document_id`
- `POST /analyses` `{resume_doc_id, jd_text, extra_text?, supporting_doc_ids[]}` → `analysis_id` (202)
- `GET /analyses/{id}`: status + results
- `GET /analyses`: user history
- `POST /analyses/{id}/interview`: "Prepare Me for Interview" (idempotent, returns the stored set if it already exists)
- `GET /health`
- `/mcp`: MCP server endpoint (protected by a service token)

Limits: PDF/DOCX ≤ 5 MB, ≤ 5 supporting docs, JD ≤ 15k chars. Reject scanned PDFs that have no text layer, with a clear message (OCR is out of scope for v1).

---

## 10. Implementation phases

Each phase ends with working, deployed software plus tests. **Don't start a phase until the previous phase's exit criteria pass.** At the start of each phase, confirm open questions with the user before writing code.

**Status:** Phases 0–5 ✅ done (2026-09-23). Phase 6 in progress.
Phase 1 live baseline (`gpt-4o-mini`): ~3.4k input / 2.3k output tokens, ~28 s, ≈ $0.002 per analysis; identical re-run = 2/2 cache hits in ~2 s.

**Live:** frontend https://resume-optimizer-ten-virid.vercel.app · backend https://resume-optimizer-api-jzq4.onrender.com · Supabase project ref `toesvlmefyvghivevjie`. The Vercel project's Root Directory must be `frontend`. `ALLOWED_ORIGINS` lives in `render.yaml`.

### Phase 0: Foundation ✅
- Monorepo scaffold (§3). `git init`, GitHub repo, `.gitignore`, `.env.example` files.
- Next.js + Tailwind + shadcn scaffold. FastAPI scaffold with `/health`.
- Supabase project, first migration (profiles, documents, analyses), RLS, Storage bucket.
- Supabase Auth (email + Google) in the frontend. JWT verification in the backend.
- CI: ruff + mypy + pytest, and eslint + typecheck + vitest.
- Deploy the skeleton: Vercel (frontend) and Render (backend) connected to GitHub.
- **Exit:** a logged-in user hits an authenticated `/health/me` from the deployed frontend.

### Phase 1: Input and extraction ✅
Implementation notes (decided during Phase 1):
- The backend talks to Supabase through its REST APIs (PostgREST + Storage) with the secret key (`SUPABASE_SERVICE_ROLE_KEY`, an `sb_secret_...` key), via `app/db/supabase.py`. Every user-facing query filters by `user_id`. `DATABASE_URL` is unused so far.
- Text is extracted at upload time (`POST /documents`), so scanned PDFs are rejected immediately. The JD and the extra-skills text are stored as `documents` rows (`jd`, `extra_text`); `extra_text` doc ids go into `analyses.supporting_doc_ids`.
- ProfileExtractor labels documents `RESUME`, `S1`, `S2`… (supplementary ordered by content hash), so re-uploading identical files gives an identical prompt and a cache hit. Labels are mapped back to `resume` / `supplementary:<doc_id>` in Python; items citing an unknown label are dropped.
- OpenAI calls use the Responses API (`responses.parse`) with `store=False`. `temperature=0` and `reasoning.effort` (`OPENAI_REASONING_EFFORT`) are both sent; whichever one a model rejects is dropped and remembered (`app/llm/client.py`).
- The cache key also includes the output JSON schema, so a schema change never returns stale cached data.
- The frontend polls `GET /analyses/{id}` every 2 s (no Realtime yet). API types are generated: `scripts/export_openapi.py` → `frontend/lib/openapi.json` → `pnpm gen:api` → `lib/api-schema.d.ts`.
- Upload UI: resume PDF, JD textarea, extra-skills textarea, supporting docs (PDF/DOCX/text).
- DocumentParser (no LLM) + unit tests on sample resumes.
- OpenAI wrapper (`llm/`): structured outputs, caching, token logging, retries.
- ProfileExtractor + JDAnalyzer agents with Pydantic schemas and prompt files.
- **Exit:** uploading a resume and JD shows the extracted profile and requirements JSON in a debug view. A second identical run is 100% cache hits.

### Phase 2: Matching and deterministic Job Fit Score ✅
Implementation notes (decided during Phase 2):
- The taxonomy lives at `backend/app/skills/data/skills_taxonomy.json` (inside the Docker build context), not `data/`. Each skill has `aliases`, `prerequisites` (for Phase 4) and `implies` (PostgreSQL implies SQL). `Taxonomy` validates it on load: unique ids and aliases, known references, no prerequisite cycles.
- **No embeddings in the Matcher (for now).** Order: taxonomy id (direct, then `implies` = implied) → fuzzy name → one batched `evidence_matcher` LLM call for every requirement without direct evidence, plus all `experience` requirements. The LLM cites catalog ids (K/P/X/E/C); Python maps them back and computes strength. Embeddings arrive with RAG in Phase 5.
- The strength rules, including category overrides (education, soft skills, years) and the fact that demonstrated-only also scores 0.7, are documented in `app/scoring/weights.py`. Years count only jobs the matcher cites as direct evidence; "present" resolves to the analysis date.
- Requirements with alternatives ("Java, C++ or R") are kept as one requirement (jd_analyzer prompt v2). If at least two alternatives are known skills, any one of them matches through the taxonomy; otherwise the requirement goes to the LLM matcher (scoring v2).
- Golden cases are in `backend/tests/golden/` (inputs in `cases.py`, snapshots in `*.json`). After an intended change, regenerate with `UPDATE_GOLDEN=1 uv run pytest tests/test_golden.py` and review the diff. CI enforces 100% line and branch coverage on `app/scoring`.
- `skills_taxonomy.json` (start with ~300–500 common tech skills, aliases and prerequisites).
- SkillNormalizer, Matcher (with embedding + batched LLM fallback), Scorer, GapClassifier.
- Results page: score gauge, per-requirement breakdown (matched / weak / missing).
- **Exit:** the scoring engine has full unit and property tests. The same input gives the same score across 5 runs. Golden-file tests pass on 5+ sample resume/JD pairs.

### Phase 3: Resume suggestions and skill gaps ✅
Implementation notes (decided during Phase 3):
- Eligible for advice: `weak_in_resume` / `missing_from_resume_but_evidenced` requirements whose `best_strength > resume_strength`. So every suggestion has a real, positive uplift; with nothing eligible the advisor makes no LLM call. Uplift = `scoring.engine.uplift` with the addressed requirements raised to `best_strength`.
- The advisor sees numbered evidence (Q1…, supplementary first) with verbatim snippets. The `EvidenceValidator` (`app/agents/evidence_validator.py`) rejects drafts that: address no eligible requirement; cite unknown or unrelated evidence; quote text not found (case/space/quote-style-insensitive, `…` fragments in order) in the cited evidence's document; or name a technical skill (`Taxonomy.find_in_text`) not present in the student's raw documents or implied by them. Rejections are stored and their count shown in the UI.
- Results: `analysis_results.suggestions` = `{suggestions, rejected}`, `analysis_results.gaps` = true gaps.
- ResumeAdvisor + EvidenceValidator (rejects any suggestion without verbatim evidence).
- Per-suggestion uplift and potential score.
- UI: "Already have it, add to resume" cards (with evidence + uplift) vs. "Skill gaps" list.
- **Exit:** no suggestion references a skill without evidence (tested with adversarial fixtures). Uplift numbers match a recomputed score.

### Phase 4: Learning path ✅
Implementation notes (decided during Phase 4):
- `ingestion/resources_seed.yaml` is the source of truth (about 200 free, reputable resources; each URL was checked when added). Sync it with `uv run python -m scripts.seed_resources` (backend/): it upserts on `(skill_id, url)` and deletes rows no longer in the file. A test validates skill ids, https and duplicates.
- MCP server (`app/mcp_server/server.py`, fastmcp 4): tools `get_learning_resources` (free first, easier first, shorter first, max 3 per skill) and `get_skill_prerequisites`. Agents use it in-process via `open_tools(server)` (in-memory transport). It is mounted at `/mcp` (streamable HTTP, stateless JSON) **only when `MCP_SERVICE_TOKEN` is set**, behind `Authorization: Bearer <token>`.
- Planner: targets = `true_gap` requirements in categories skill/domain (education, experience and soft skills are not "learnable" steps); alternatives use the first known alternative; gaps the taxonomy doesn't know become steps without resources. Skills the student shows, their `implies`, and all their prerequisites count as known. Prerequisites are pulled in up to 2 levels deep, and ordering uses the full prerequisite closure among included steps. The LLM may only reorder independent steps (checked; otherwise the deterministic order is used) and writes "why" notes. If the LLM fails, default notes are used.
- `learning_resources` table + seed file. MCP server skeleton with `get_learning_resources` and `get_skill_prerequisites`.
- LearningPathPlanner (taxonomy-ordered, LLM for rationale and ordering ties only).
- UI: ordered steps timeline with resources, estimated hours and "why this first".
- **Exit:** every resource URL in the output exists in the DB, and prerequisite order respects the taxonomy graph.

### Phase 5: Interview preparation (RAG + MCP) ✅
Implementation notes (decided during Phase 5):
- Ingestion code lives in `backend/app/ingestion/` and one command runs every stage: `uv run python -m scripts.ingest_questions` (in backend/; `--dry-run` for fetch + parse only). The config stays in `ingestion/sources.yaml`, which lists 24 permissively licensed repos (MIT/Apache-2.0/CC0/CC-BY-4.0/Unlicense, checked via the GitHub API) with exact file paths and per-file topics. Files are fetched through GitHub's remote MCP server (`https://api.githubcopilot.com/mcp/readonly`, `get_file_contents`) and cached in `ingestion/.cache/` (gitignored). The parser handles headings, lists, tables, bold lines, links and `<summary>`; each source can restrict `markers`. Dedupe is by normalized-text hash, then embedding cosine > 0.95 (numpy, earlier sources win). Behavioral questions that name a company ("Why Amazon?") are dropped. Answers are never stored. Loading pages through existing rows (PostgREST caps responses at 1000 rows) and retries batches.
- Tables: `interview_questions` (pgvector 1536, HNSW cosine index), RPC `match_interview_questions` (service role only), `embedding_cache` (query embeddings), `interview_sets` (one per analysis).
- The project deep-dive bank is `backend/app/rag/data/project_templates.yaml`: 50 templates, 12 dimensions, with facets derived from the project's technologies. Placeholders are `{project}`, `{tech}`, `{tech2}` and `{metric}`.
- MCP tools added: `search_interview_questions`, `get_project_question_templates`, `get_general_questions` (seeded by analysis id).
- InterviewPrep (`POST /analyses/{id}/interview`, idempotent; `GET` returns the stored set) retrieves technical questions per top requirement (topic filter, then an unfiltered semantic fallback with similarity ≥ 0.35). One `large`-tier LLM call selects question ids and fills templates. Python drops unknown ids, rejects fills that aren't faithful to the template or don't mention the project/its tech, and pads each group to its minimum (technical 8, general 5, personal 3, per project 8 across dimensions). If the LLM fails, the whole set is selected deterministically.
- `sources.yaml` + ingestion scripts using the GitHub MCP server. Parse, dedupe, embed, load into pgvector.
- Project deep-dive template bank.
- MCP tools: `search_interview_questions`, `get_project_question_templates`, `get_general_questions`.
- InterviewPrep agent + "Prepare Me for Interview" button. UI groups questions by category, with the source shown on each question and per-project drill-down sections.
- **Exit:** 100% of questions have a `source`. Technical questions change according to the JD. Each resume project gets deep, specific questions.

### Phase 6: History, polish and hardening
Implementation notes (decided during Phase 6):
- API: `GET /analyses` (history with role title/company, newest first, max 50), `POST /analyses/{id}/rerun` (same resume and supporting docs incl. notes, new JD; profile extraction is a cache hit), `DELETE /analyses/{id}` (cascades results and the interview set; documents are kept because re-runs share them), `GET /analyses/{id}/export` (Markdown report incl. the interview set). PDF = browser print with `print:hidden` on UI chrome.
- Limits: `DAILY_ANALYSIS_LIMIT` (re-runs count) and `DAILY_UPLOAD_LIMIT` (default 40 files/pasted texts per 24 h). Upload file names are reduced to a printable base name (display only; storage paths are UUIDs).
- Cost: view `llm_usage_daily`; `uv run python -m scripts.cost_report` (prices from `OPENAI_PRICE_INPUT_PER_M` / `OPENAI_PRICE_OUTPUT_PER_M`, target `COST_TARGET_PER_ANALYSIS`). Live baseline on gpt-4o-mini: about $0.0012 per analysis including interview prep.
- Security: RLS on all 10 public tables (audited with `supabase db query`); `handle_new_user` no longer executable via REST (`supabase db advisors --type security` is clean except "leaked password protection", which needs a paid plan). No secrets in git history. Production CORS allows only the Vercel origin. Frontend sends security headers (X-Frame-Options DENY, nosniff, Referrer-Policy, Permissions-Policy, HSTS).
- History page, re-run an analysis against a new JD with the same profile, export results (PDF/markdown).
- Rate limits, daily quotas, a cost dashboard query over `llm_calls`, error states, empty states, mobile layout.
- Security pass: RLS audit, upload validation, secrets, CORS locked to the Vercel domain.
- Auth email: set up custom SMTP (e.g. Resend free tier) and **turn Supabase "Confirm email" back on**. It is turned off during development because Supabase's built-in email is rate-limited.
- **Exit:** a full end-to-end Playwright test on production, and the average cost per analysis is logged and under target.

---

## 11. Environment variables

**backend/.env**
```
OPENAI_API_KEY=
OPENAI_MODEL_SMALL=            # cheap model for extraction
OPENAI_MODEL_LARGE=            # used sparingly
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_REASONING_EFFORT=low    # sent to reasoning models only
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=     # secret key (sb_secret_...), server only
SUPABASE_JWT_SECRET=
DATABASE_URL=                  # Supabase Postgres (pooler) connection string
MCP_SERVICE_TOKEN=
ALLOWED_ORIGINS=http://localhost:3000
DAILY_ANALYSIS_LIMIT=10
```
**frontend/.env.local**
```
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```
**ingestion** additionally needs `GITHUB_PERSONAL_ACCESS_TOKEN` (read-only, public repos) for the GitHub MCP server.

Never commit `.env*` files. Keep `.env.example` files up to date.

---

## 12. Commands

```bash
# backend
cd backend && uv sync
uv run uvicorn app.main:app --reload --port 8000
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy app

# frontend
cd frontend && pnpm install
pnpm dev
pnpm lint && pnpm typecheck && pnpm test

# database
supabase start                  # local stack (optional)
supabase migration new <name>
supabase db push

# ingestion (Phase 5): fetch via GitHub MCP, parse, dedupe, embed, load
cd backend && uv run python -m scripts.ingest_questions
# learning resources (Phase 4)
cd backend && uv run python -m scripts.seed_resources
```

---

## 13. Coding conventions

- **Python:** typed everywhere, Pydantic v2 models for all agent I/O, `async` for I/O, no business logic in routers. Agents are pure with respect to their input (DB writes happen in the orchestrator).
- **TypeScript:** strict mode, server components by default, API types in `frontend/lib/types.ts` kept in sync with the backend Pydantic schemas (generate them from the FastAPI OpenAPI spec with `openapi-typescript`).
- **Tests:** every agent has tests with a **mocked LLM** (recorded fixtures). Tests never call OpenAI in CI.
- **Prompts:** in markdown files, versioned, with the output schema defined in Pydantic rather than in prose.
- Keep dependencies minimal. Adding a new service or library needs a one-line justification in the PR.
- Commit messages: conventional commits (`feat:`, `fix:`, `chore:`…). One phase = a series of small PRs into `main`.

---

## 14. Out of scope for v1
- OCR for scanned PDFs
- Generating answers to interview questions
- Auto-rewriting or exporting a modified resume file (we suggest changes, we don't produce the resume)
- Job scraping or JD fetching from URLs
- Paid tiers and payments
