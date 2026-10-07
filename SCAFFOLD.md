# CoA agent: scaffold plan

Source: `coa-agent-poc-plan.pdf` (Oct 7, 2026). This file maps the plan's 11 components (C1–C11) onto a repository laid out like `../medas`, and lists what to settle in the plan first. The scaffold now exists; section 9 records what was built and the decisions taken.

## 1. Review of the plan

The plan is tight and the split is right: the agent investigates, only code decides. Eight points to settle before coding, most important first.

### Must settle (they change the design)

1. **`submit` must not trust the model for status.** As written, `submit(status, summary, findings, draft_id)` takes the status and the findings from the model, and FR3 "must run `check_spec` and `check_supplier`" is only enforceable if the guard knows what ran. Fix: the guard reads the run's state (which tools ran, their raw outputs), computes the status itself, and refuses a `status` that disagrees. The model supplies only the summary, the draft id and, per finding, a `likely_coa_error` claim with evidence.
2. **The FAIL → REVIEW downgrade is an assertion by the model.** The rule "unless the agent marks it as a likely CoA error with evidence" lets a wrong or injected model turn any FAIL into REVIEW. Accept the claim only when state backs it: `get_lot_history` was called for that test, and its output shows the value is an outlier against the history (a threshold in code, e.g. 10× or more than 3σ from the mean). Otherwise `submit` refuses, and FAIL stands. This also makes scenario 2 deterministic.
3. **The baseline numbers don't add up.** The table has the baseline correct on scenarios 1, 3, 7 (and 4 if "FAIL" rather than a crash) = 3–4 of 8, not "about 5". Scenario 5 is "PASS (not checked)", so the baseline skips `check_supplier`. FR9 says it reuses the same tools, which contradicts that. Decide which story you tell. Recommended: the baseline runs every code check, including `check_supplier`; the agent's value is then the 2, 3, 4, 6 and 8 gaps and nothing looks rigged. Define a baseline status set that includes `ERROR` (scenario 4 "crash" must be a caught error, not a stack trace).
4. **Scenario 8 has no scripted answer.** Add to `expected.csv`: `answer` (which material), `final_status`. `evaluate.py` needs both, as it must resume the run automatically. The second material also needs spec rows, or the "other" answer dead-ends.
5. **Unit conversion is per test, not global.** `aliases.csv` as `supplier_term, internal_test, unit_factor` can't tell impurities in ppm (→ %, ×0.0001) from residual solvents in ppm (stays ppm, limit 5000 ppm). Use `supplier_term, internal_test, supplier_unit, internal_unit, factor`, and have `normalize` report a mapping note per row. Add a unit test for each pair.
6. **No tool resolves the supplier.** FR6 says ambiguous "material or supplier", but `identify_material` only returns a material code, and `check_supplier` / `get_lot_history` take free-text names. Make `identify_material` also return `supplier_id` (or add `identify_supplier`) and key everything else on ids.

### Should settle (they save debugging time)

7. **State-injected arguments, as medas does with `record_id`.** `read_coa(pdf_id)` should take no model-chosen argument: the run's `pdf_id` is read from state, so the model can't open another upload. Same for the `normalize` / `check_spec` inputs where the previous tool's output is already in state, which also cuts tokens and typing errors.
8. **Low confidence has no consequence.** The glossary says low confidence goes to review, but the submit rules never use it. Add: a field used in a check with confidence below a threshold (0.8) either gets verified (a second read of that page) or forces REVIEW. Also add a deterministic grounding check in `read_coa`: each `source_text` must appear in the PyMuPDF text of the stated page, else confidence is capped.
9. **Prompt injection reaches the extractor first.** `read_coa` feeds the PDF to a model, so the footer text hits that model before the agent sees anything. The extraction schema must have no free-text field the agent will read as instructions. Keep one `document_notes: str` field if the demo should show the injected text, and wrap it in the tool output as `<untrusted_document_text>`. Say so in the system prompt.
10. **Interrupt and parallel calls.** `interrupt()` re-runs its node from the top on resume, so `ask_user` must do nothing before it. Bind tools with parallel calls off, or the model can emit `ask_user` next to other calls and the budget count gets muddy. Also decide what counts: the plan's "clean CoA in 6" is exactly read, identify, normalize, check_spec, check_supplier, submit, so zero slack. Say whether `ask_user` and rejected `submit` calls count (suggest: yes, all calls).
11. **Cost and tokens.** FR8 and the score table need tokens and cost per CoA, and `read_coa` makes a nested model call. Record usage with one LangChain callback handler on the graph config (it sees nested calls), not per tool. Cost needs a price table per model in `.env`, or OpenRouter's usage accounting; pick one now.
12. **`expected_findings` must be structured** (`test:severity;...`), not prose, or `evaluate.py` can't compare it.

### Smaller notes

- **Time:** under 60 s for a clean CoA means about 7 model calls including a vision call. Check the chosen model's latency on day 2, not day 5.
- **Stability:** temperature 0 is not determinism, and some reasoning models ignore it. The 3-run stability criterion is a measurement, not a guarantee. Keep the model pinned in `.env`.
- **Day 4 is the risk day** (API + SSE + full UI). The plan builds the CLI first, which is right. Cut line if late: no PDF viewer highlighting, baseline as a button that fills a column.
- **PyMuPDF is AGPL** (commercial licence otherwise). Fine for a synthetic-data POC; record it as a decision before any real-data step.
- **SQLModel is optional.** medas uses plain async SQLAlchemy. With SQLite and no migrations, SQLAlchemy 2 plus `create_all` at startup is one dependency fewer and matches the repo it will sit next to.
- **Uploads:** store under a generated id, never the client's filename; cap size; check the `%PDF` header (medas returns 413 / 415 for these).

## 2. Conventions taken from medas

| Area            | medas                                                                             | Here                                                       |
| --------------- | --------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| Layout          | `medas-api/` (flat modules, `pythonpath = ["."]`) and `medas-ui/` at the root     | `coa-api/` and `coa-ui/`, not the plan's `app/` and `web/` |
| Python          | 3.14, `uv`, `uv sync --locked --group dev`                                        | same; verify PyMuPDF and LangGraph wheels on 3.14 first    |
| Lint            | ruff, rule set pinned in `pyproject.toml` (F E W I UP B ASYNC S SIM RUF)          | copy the block unchanged                                   |
| Tests           | pytest, `asyncio_mode = "auto"`, unit-only, one patched agent seam                | same; the model is faked, the live run is `evaluate`       |
| Web             | Next 16, React 19, Tailwind 4, shadcn, zustand, Vitest, Yarn 4                    | same                                                       |
| Formatting      | prettier (no semicolons, double quotes, trailing commas), `.githooks`             | copy `.prettierrc.json`, `.githooks/pre-commit`            |
| CI              | `api.yml` and `ui.yml`, path-filtered, `--locked` / `--immutable`                 | same, renamed                                              |
| Browser → API   | never directly; Server Actions and Server Components only, `API_BASE_URL` private | same, see the SSE note below                               |
| Layers          | `controller → langchain_agent → rag_pipeline`, one way                            | `controller → agent → tools`                               |
| Schema          | `schema/schema.py` imports nothing from the project                               | same for the Pydantic types                                |
| Lazy model      | `build_agent()` under `lru_cache`; import never needs credentials                 | same                                                       |
| Errors          | domain exceptions mapped once in `main.py` (404, 503, 413, 415)                   | same                                                       |
| Source of truth | root `README.md`, package READMEs defer to it                                     | same                                                       |

Deliberate departures:

- **Explicit `StateGraph`, not `create_agent`.** medas uses `create_agent`. This plan needs a `force_submit` node, budget routing and a guarded `submit`, so build the graph by hand. Keep medas's habit of passing run data (`pdf_id`, `supplier_id`, tool outputs) through the state schema and reading it from `runtime.state`.
- **No auth, no Postgres, no Alembic, no rate limiting.** Out of scope per the plan; `create_all` at startup, SQLite files under one state directory.
- **SSE needs a route handler.** medas's rule is that the browser never calls the API. A Server Action can't stream, so add one Next route handler that proxies the API's event stream (`new Response(upstream.body, …)`). `EventSource` hits the same origin, and the API still needs no CORS.

## 3. Target tree

```
coa/
├── CLAUDE.md                     # commands, architecture, gotchas (like medas)
├── README.md                     # source of truth: setup, env, API, data, eval, known gaps
├── SCAFFOLD.md                   # this file; delete once built
├── docker-compose.yml            # api + ui, one named volume for state (NF1)
├── .env.example                  # OPENROUTER_API_KEY, OPENROUTER_MODEL, ...
├── .gitignore  .gitattributes  .prettierrc.json  .prettierignore
├── .githooks/pre-commit
├── .github/workflows/{api,ui}.yml
├── .claude/launch.json           # coa-api :8000, coa-ui :3000
├── coa-api/
│   ├── pyproject.toml  .python-version  uv.lock  Dockerfile  .env.example
│   ├── main.py                   # C9  routes + SSE, exception handlers, lifespan
│   ├── settings.py               # pydantic-settings: key, model, budget, paths
│   ├── schema/                   # C2  Extraction, Result, Finding, ToolCall, RunResult, exceptions
│   │   └── schema.py
│   ├── tools/
│   │   ├── ai_tools.py           # C3  read_coa, draft_supplier_request
│   │   ├── code_tools.py         # C4  identify_material, normalize, check_spec,
│   │   │                         #     check_supplier, get_lot_history, ask_user
│   │   ├── rules.py              # decide_status(...): the pure submit rules, no LangGraph
│   │   └── data.py               # cached CSV loaders (stdlib csv; pandas only in make_data)
│   ├── agent/
│   │   ├── registry.py           # C5  @tool wrappers + args schemas, error-to-message ToolNode
│   │   ├── orchestrator.py       # C6  build_agent(): agent, tools, force_submit, router
│   │   ├── prompt.py             #     system prompt
│   │   ├── state.py              #     RunState: messages, extraction, findings, calls_used, ...
│   │   ├── guard.py              #     submit guard: reads state, calls tools.rules
│   │   └── callbacks.py          #     one handler: steps, tokens, time -> trace
│   ├── baseline.py               # C8  fixed read → normalize → check, same tools
│   ├── model/                    # C7  ORM: Run, Step
│   ├── database/                 #     async engine, create_all, WAL
│   ├── trace.py                  #     write_step, tail(run_id, after_seq) for SSE
│   ├── controller/runs.py        #     start, resume, events: the one agent seam
│   ├── dataset/                  # C1  inputs and ground truth, all invented
│   │   ├── README.md             #     what each scenario plants
│   │   ├── make_data.py          #     C1  reportlab (invariant=1) + CSVs, deterministic
│   │   ├── *.csv                 #     spec, materials, suppliers, lot_history, aliases, expected
│   │   ├── coa/coa_0{1..8}_*.pdf #     committed, marked binary
│   │   └── eval/evaluate.py      # C11  python -m dataset.eval.evaluate
│   └── tests/
├── coa-ui/
│   ├── package.json  yarn.lock  .yarnrc.yml  tsconfig.json  next.config.ts
│   ├── eslint.config.mjs  vitest.config.mts  components.json  AGENTS.md
│   ├── app/
│   │   ├── layout.tsx  page.tsx  globals.css
│   │   └── runs/[id]/events/route.ts   # SSE proxy to the API
│   ├── api/runs.ts               # Server Actions: start, baseline, answer, get
│   ├── components/
│   │   ├── demo-banner.tsx       # NF5: "Demo on synthetic data; not a GMP system"
│   │   ├── upload-panel.tsx  pdf-viewer.tsx
│   │   ├── trace-list.tsx  trace-step.tsx
│   │   ├── baseline-panel.tsx  result-card.tsx  ask-box.tsx
│   │   └── ui/                   # shadcn
│   ├── hooks/use-run-events.ts   # EventSource, reconnect with Last-Event-ID
│   ├── store/run-store.ts        # zustand: steps, run state, pending question
│   ├── model/                    # Run.ts, Step.ts, Finding.ts
│   └── test/                     # fixtures.ts, setup.ts
└── state/                        # gitignored at runtime: trace.db, checkpoints.db, uploads/
```

## 4. Component map

| Plan | Where                                       | Test seam                                                                          |
| ---- | ------------------------------------------- | ---------------------------------------------------------------------------------- |
| C1   | `coa-api/dataset/make_data.py`              | a test that regenerates and asserts the planted value in each PDF's text           |
| C2   | `coa-api/schema/schema.py`                  | round trip and validation tests                                                    |
| C3   | `coa-api/tools/ai_tools.py`                 | fake chat model returns a canned `Extraction`; no network                          |
| C4   | `coa-api/tools/code_tools.py`, `rules.py`   | pure tests: every limit, unit pair, expired supplier, ambiguous material           |
| C5   | `coa-api/agent/registry.py`                 | tool errors come back as messages; two failures of one tool → REVIEW               |
| C6   | `coa-api/agent/orchestrator.py`, `guard.py` | scripted fake model: budget → `force_submit`, interrupt and resume, refused submit |
| C7   | `coa-api/model/`, `database/`, `trace.py`   | in-memory SQLite: step order, tail from `after_seq`                                |
| C8   | `coa-api/baseline.py`                       | the 8 PDFs' extractions stubbed; asserts baseline statuses                         |
| C9   | `coa-api/main.py`, `controller/runs.py`     | patch `controller.runs.run_agent`; route and SSE tests                             |
| C10  | `coa-ui/`                                   | Vitest: stub `fetch` as in medas; store reset in `test/setup.ts`                   |
| C11  | `coa-api/dataset/eval/evaluate.py`          | pure scoring functions tested; the run itself is billable and manual               |

## 5. Backend notes

- **Run lifecycle.** `POST /runs` saves the upload, creates a `Run`, starts the graph as an `asyncio` task and returns `run_id`. The callback handler writes each step to `trace.db`. `GET /runs/{id}/events` tails that table by `seq` and honours `Last-Event-ID`, so a dropped connection resumes and a finished run replays for the demo.
- **Pause and resume.** `ask_user` calls `interrupt()`; the run state becomes `waiting`; `POST /runs/{id}/answer` resumes with `Command(resume=...)`. Use `AsyncSqliteSaver` (`langgraph-checkpoint-sqlite`) in its own file, apart from the trace DB.
- **Two vocabularies.** Result status is `PASS | REVIEW | FAIL`; run state is `running | waiting | done | error`. The plan's "WAITING" is a run state.
- **Budget.** Count tool calls in state; the router goes to `force_submit` (REVIEW) at 12. Set `recursion_limit` to roughly 2 × budget + 4 as a backstop only.
- **Settings.** `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, optional `EXTRACTION_MODEL`, `TOOL_BUDGET=12`, `STATE_DIR`. Never logged; `.env` ignored, `.env.example` committed.
- **Determinism of the data.** Pass `invariant=1` to reportlab so regenerating doesn't change PDF bytes; mark `*.pdf` binary in `.gitattributes`.

## 6. Frontend notes

- Next 16 differs from training data. Per medas's `AGENTS.md`, read the relevant guide in `node_modules/next/dist/docs/` before writing Next code (route handlers, streaming, Server Action body limit for the PDF upload).
- One page: upload, PDF on the left, trace in the middle, baseline and result on the right, answer box when a run is `waiting`.
- PDF viewer: start with an `<iframe src={blobUrl}#page=N>`, which needs no worker setup. Move to `react-pdf` only if highlighting the source text is wanted; its worker config under Next is a known time sink.
- Score table (demo step 6): printed by `evaluate.py` and saved as markdown. No new endpoint.

## 7. Scaffold order

1. `git init`; copy from medas: `.gitattributes`, `.prettierrc.json`, `.prettierignore`, root `.gitignore`, `.githooks/pre-commit` (rename paths), then `git config core.hooksPath .githooks`.
2. `coa-api`: `uv init`, set Python 3.14, copy the `[tool.ruff]` and `[tool.pytest.ini_options]` blocks, `uv add` the runtime packages (fastapi, langgraph, langgraph-checkpoint-sqlite, langchain, langchain-openai, pymupdf, pydantic-settings, sqlalchemy, aiosqlite, python-dotenv, python-multipart) and `--group dev` (ruff, pytest, pytest-asyncio, reportlab if only the generator uses it). Resolve versions at that point.
3. `coa-ui`: Next 16 app, Yarn 4 (`.yarnrc.yml` incl. the `npmMinimalAgeGate` comment), Tailwind 4, `shadcn init`, zustand, Vitest and Testing Library, ESLint config as medas.
4. Empty module skeletons with the signatures above, one passing test each, so CI is green from the first commit.
5. `docker-compose.yml`, both Dockerfiles, `.github/workflows`, `.claude/launch.json`, `CLAUDE.md`, `README.md` skeleton.
6. Day 1 of the plan starts here: `dataset/make_data.py`.

## 8. Decisions taken

- Folders are `coa-api` and `coa-ui`.
- The baseline includes `check_supplier` (review point 3). Expected baseline results are in the README and are measured by `evaluate.py`, not assumed.
- Model: `openai/gpt-4.1` via OpenRouter, set in `OPENROUTER_MODEL`.

## 9. What was built

- Repo: `git init`, config copied from medas (`.gitattributes`, `.prettierrc.json`, `.githooks/pre-commit`, CI workflows, `.claude/launch.json`), `core.hooksPath` set.
- `coa-api`: uv project on Python 3.14 with the planned dependencies, ruff and pytest config from medas, `settings.py`, `schema/` (types and exceptions), `database/` and `model/` (SQLite trace store), `main.py` (lifespan, error handlers, `/health`), `agent/state.py`, `agent/prompt.py` (first draft), and docstring-only stubs for every other component. 24 tests, ruff clean.
- `coa-ui`: Next 16, Tailwind 4, Vitest. Server Actions (`api/runs.ts`), SSE proxy route handler, zustand store, `useRunEvents` hook, demo banner. Lint, types, 5 tests and `next build` pass.
- Root: `docker-compose.yml`, both Dockerfiles, `CLAUDE.md`, `README.md`.

Not built (plan days 1–5): data generator, tools, `decide_status`, orchestrator, API routes, UI panels, `evaluate.py`.

## 10. Day 2 (tools)

- `schema/`: tool input and output types; findings carry a `kind`; `ExtractedResult.result_text` holds the printed result so qualitative tests can be judged.
- `tools/code_tools.py`, `tools/rules.py` (`decide_status`: the model's status is not an input; a FAIL becomes REVIEW only when a claim is backed by an outlier in the run's own lot history), `tools/ai_tools.py` (`read_coa` with grounding against the text layer, `draft_supplier_request`), `tools/llm.py` (OpenRouter client).
- `agent/registry.py`: eight `@tool`s fed from `RunState` through `InjectedState` (the model types only names, a test, an issue). `submit` and its guard are day 3.
- Tests: 152 (was 45). The deterministic path reproduces `expected.csv` for all 8 scenarios without a model, and the registry tests run the tools through a `ToolNode` graph with a checkpointer, including `ask_user` pausing and resuming, which was the main day-3 risk.
- Not verified: `read_coa` against the real model. `uv run python -m dataset.eval.check_extraction` does it once `OPENROUTER_API_KEY` is set.
- Open for day 3: count failed tool calls toward the budget (a refused call currently returns an error message without updating `calls_used`), and the two-failures-of-one-tool rule.
