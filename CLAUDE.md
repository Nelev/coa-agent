# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

CoA agent: a 5-day proof of concept that shows what an AI agent adds over a fixed extraction-and-rules pipeline when checking a supplier Certificate of Analysis. Two independently developed packages, laid out like `../medas`: `coa-api` (FastAPI, Python 3.14, uv) and `coa-ui` (Next.js 16, React 19, Yarn 4). The root `README.md` is the source of truth for scenarios, env vars, API surface and known gaps; keep it in sync when changing a contract. `coa-agent-poc-plan.pdf` (outside the repo) is the spec; `SCAFFOLD.md` records the review of it and the decisions taken.

## Commands

API (run from `coa-api/`):

```bash
uv sync --group dev
uv run fastapi dev main.py                      # :8000, docs at /docs
uv run ruff check . && uv run ruff format --check . && uv run pytest -q
uv run pytest tests/test_main.py::test_name -q  # single test
uv run python -m dataset.make_data              # regenerate the 8 PDFs and the CSVs
uv run python -m dataset.eval.check_extraction  # billable: read_coa on the 8 PDFs vs ground truth
uv run python -m dataset.eval.run_scenario 2    # billable: agent + baseline on scenario 2 (none = all 8), trace printed
uv run python -m dataset.eval.evaluate          # billable: 3 agent runs + 1 baseline per CoA
```

UI (run from `coa-ui/`):

```bash
yarn install
yarn dev                                        # :3000, needs the API running
yarn lint && yarn format:check && yarn tsc --noEmit && yarn test
yarn next typegen                               # before tsc on a fresh checkout
```

Whole demo: `docker compose up` (needs `coa-api/.env`). Pre-commit hook: `git config core.hooksPath .githooks` (already set by `git init` here, per clone otherwise).

## Architecture

- **The agent reads, investigates and explains; only deterministic code decides pass or fail.** `tools/rules.py::decide_status` is the single place status is computed. `submit` ignores the model's proposed status, reads what actually ran from the run's state, and refuses a mismatch. A FAIL → REVIEW downgrade (`likely_coa_error`) is honoured only if `get_lot_history` output in state shows an outlier. Nothing is ever sent: drafts are stored and shown.
- **Tools.** `tools/code_tools.py` (identify, normalize, check_spec, check_supplier, get_lot_history) are plain functions over `dataset/*.csv`; `tools/ai_tools.py` has `read_coa` (PyMuPDF text + page images to the model, then each row is grounded against the text layer: not found means confidence capped at 0.3 and a REVIEW) and `draft_supplier_request`. `agent/registry.py` wraps them as `@tool`s returning `Command`s that write `RunState`. Findings have a `kind` (`oos`, `missing`, `expired`, `unapproved`, `unreadable`); only `oos` can be downgraded, and `tools/code_tools.get_lot_history` decides what an outlier is (decimal shift or |z| ≥ 6), never the model. Qualitative identification passes only if the printed result starts with conforms, complies or positive.
- **The model never chooses what it can't be trusted with.** `pdf_id`, previous tool outputs and the call count live in `agent/state.py::RunState` and are read from injected state, not tool arguments (the same pattern as medas's `record_id`). Text from the PDF is data: `Extraction` has no free-text field except `document_notes`, which the prompt marks untrusted.
- **Layers, one way:** `controller → agent → tools`. `tools/` never imports `agent/`. `schema/schema.py` imports nothing from the project. ORM classes are in `model/`.
- **Agent.** An explicit LangGraph `StateGraph` in `agent/orchestrator.py` (not `create_agent`, unlike medas): `agent` → `tools` (the registry's ToolNode) → `account` → back to `agent` until `submit` is accepted. `account` counts every call, refused ones too, and consecutive failures per tool. Two failures of one tool, the 12-call budget (a batch that would overshoot is not run), or the model answering without a tool after two nudges all route to `force_submit`, which submits REVIEW (never PASS) with the findings so far. `ask_user` pauses via `interrupt()`; `controller/runs.py::Runner.resume` continues with `Command(resume=answer)`. Tools are bound with parallel calls off. Model `openai/gpt-4.1` through OpenRouter (`OPENROUTER_MODEL`, temperature 0). `build_agent()` is lazy so importing never needs a key. `submit(summary, draft_id, claims)` has no status argument: `agent/guard.py` builds the result from the state through `tools/rules.py`.
- **Baseline** (`baseline.py`) runs the same tools in a fixed order, including `check_supplier`: no lot history, drafts or questions. Any difference from the agent comes from the agent's choices.
- **Trace.** `agent/callbacks.py::TraceHandler` records every step (tool, input, output, the reasoning text that led to it, tokens, ms) through `tracing.py`; a tool's nested model call (`read_coa`) is added to its step, a reply with no tool is a step with `tool=null`, an `ask_user` pause is a step with `waiting_for_user` and its answer another step. `GET /runs/{id}/events` (day 4) tails the `steps` table by `seq` and honours `Last-Event-ID`. The module is `tracing.py`, not `trace.py`, which would shadow the standard library.
- **The browser never calls the API.** Server Actions in `coa-ui/api/` do the fetches; the one exception in shape is the route handler `app/runs/[id]/events/route.ts`, which proxies the event stream. `API_BASE_URL` is server-only: never add a `NEXT_PUBLIC_` variant.
- **State.** SQLite via async SQLAlchemy (`database/`), `create_all` at boot, no migrations. Files under `STATE_DIR`: `trace.db`, `checkpoints.db`, `uploads/` (generated ids, never the client filename).
- **Two vocabularies:** result status `PASS | REVIEW | FAIL` (baseline adds `ERROR`); run phase `running | waiting | done | error`.

## Testing conventions

Unit-only: no network, no model, no browser. Route tests patch `controller.runs.run_agent` / `resume_agent` / `run_baseline`; graph tests drive it with `tests/helpers.py` (`ScriptedModel`, or `FakeChat`, a real chat model that fires callbacks, and `ideal(n)`, the calls a good agent makes per scenario). `tests/test_imports.py` pins that every module imports without credentials. `conftest.py` clears the settings cache and removes `Settings` env vars; account for that when adding cached settings. `evaluate.py` is the live check and is billable.

UI: Vitest + jsdom + Testing Library; `api/runs.test.ts` stubs `globalThis.fetch`; response shapes in `test/fixtures.ts`; `test/setup.ts` resets the zustand store between tests.

## Gotchas

- `coa-ui` uses a Next.js version newer than training data. Read `coa-ui/AGENTS.md` and `node_modules/next/dist/docs/` before writing Next code (`RouteContext`, async `params`).
- Injected state is validated against `RunState`'s types, so a field a tool sets to `None` (to invalidate it) must allow `None`.
- `interrupt()` re-runs its node from the top on resume, so `ask_user` must do nothing before it.
- Pass `invariant=1` to reportlab so regenerating the PDFs doesn't change their bytes.
- PyMuPDF is AGPL; fine for synthetic data, a decision before any real-data step.
- Formatting: ruff for Python; prettier (no semicolons, double quotes, trailing commas) for TS/CSS/JSON/Markdown.
