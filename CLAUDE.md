# Holos

A fitness, nutrition and mental-wellbeing coach: FastAPI + Postgres backend (`backend/`),
Next.js frontend in JavaScript (`frontend/`), shared generated contracts (`contracts/`). Every
reply and write passes a deterministic safety gate; crisis messages get fixed helplines with no
model call.

## Start here

1. `docs/STATUS.md`: where things stand and what waits on the owner.
2. `docs/QUEUE.md`: the first line that isn't `[x]` is the step to do.
3. `docs/rules/agents.md`: the rules, once per session.
4. The step's file in `docs/steps/`, and only the files its "Read first" list names.

`docs/` is a separate private repo (`vaedlabs/holos-docs`) that the app repo ignores: commit docs
changes with `git -C docs …`, never into the app repo. Code comments cite the docs by ID:
`Plan C.5` is `docs/spec/C05.md`, `Part E #61` is `docs/decisions/E061.md`.

## Hard rules

- Never commit or push without the owner's approval in that turn. Commit messages:
  `docs/rules/commits.md` (no `feat:`/`fix:` before v1.0.0).
- Before building a step: a TL;DR (what, why, how, where) for the owner's approval.
- Never change a value in `backend/app/config/limits.py`, `guardrails/rules.yaml` or
  `guardrails/catalogue.yaml` without the owner.
- `contracts/` is generated: change the Pydantic models or rules, then run the generator.
- No paid model or search calls in tests that run on push. Paid tests (`-m paid`) only when
  announced.
- Back up the dev database before any migration.

## Environment

- Python: conda env `holos`; run every Python command as `conda run -n holos …` from `backend/`.
  Run uvicorn with `conda run --no-capture-output -n holos uvicorn app.main:app --reload`.
- Postgres 16: dev DB `holos_db`, test DB `holos_test` (`TEST_DATABASE_URL` in `backend/.env`);
  the tests refuse to run on the dev DB.
- Frontend: Node 24.11; `frontend/.env.local` uses `http://localhost:8000`, not `127.0.0.1`
  (the session cookie needs the same host).

## Before presenting a commit: the CI steps

```
cd backend && conda run -n holos ruff check .
cd backend && conda run -n holos python -m app.contracts.generate --check
cd backend && conda run -n holos pytest -m "not paid and not load"
cd frontend && npm run lint && npm test && npm run build
```

New migrations must also build an empty database (`alembic upgrade head`).

## Code

- Import direction: `routers` → `orchestration` → `agents`, `providers`, `storage`, `data` →
  `models`; `guardrails/` imports nothing from `app.*`. Map: `docs/spec/C01.md`.
- Chat path async; CRUD routes plain `def` on the sync pool.
- Comments are short and say why; a plan reference goes after the reason, never instead of it.
- Files listed in `backend/ruff.toml` `extend-exclude` are old code: don't copy their style; a
  step that rewrites one removes it from the list.
- Frontend: JavaScript, not TypeScript; `.js` files hold JSX; state updates use `prev => …`.
- Frontend: Next 16 (newer than most training data): before using a Next API or config option,
  read its page in `frontend/node_modules/next/dist/docs/` (matches the installed version);
  record any deprecation warning from `next dev` or `next build` in the step's notes. Next 16
  specifics: `docs/rules/lessons/frontend.md`.
