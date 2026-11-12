# Execution ledger

Chronological record so a later session can resume without repeating work.
Each entry states the action and what it proved.

## Phase 0 — environment verification

1. Read `README.md`, `docs/ARCHITECTURE.md`, `docs/VERIFICATION.md`,
   `docs/SUBMISSION.md`, `CHANGELOG.md`, `VERSION`, `.gitignore`,
   `MANIFEST.sha256`, `pyproject.toml`, `alembic.ini`, `requirements*.txt`.
2. `git status` → **no Git repository**. Baseline must be taken manually.
3. Created `research/.baseline/pre-20261108/` containing a copy of `backend/`,
   `tests/`, `scripts/`, `migrations/`, `docs/`, `frontend/src`, `frontend/types`,
   `evaluation/`, `validation/`, `submission/`, `study/`, `data/`, `deploy/` and
   the top-level config files (1.2 MB). `research/.baseline/` is gitignored, so it
   is a local rollback net, not a deliverable.
4. First test run failed with `sqlite3.OperationalError: attempt to write a
   readonly database`. Diagnosed as a Windows sandbox permission gap on
   `.data/`. Repaired with the bundled `diagnose-windows-sandbox-acl` skill; the
   script granted the signed-in user full control on `.data` and printed a
   verifiable rollback command (`_acl-recovery/acl-backup-*.json.ps1`).
   Residual: the confined token still could not write `.data`, so all test and
   server runs in this cycle used an explicit `DATABASE_URL` under
   `research/.tmp/`. This is an agent-environment limitation, not a product
   defect; the developer's own shell writes `.data` normally.

## Phase 1 — codebase audit (verified by reading every backend module)

5. Read all 79 backend modules, `tests/*`, `scripts/*`, migrations, frontend.
6. **Defect A (critical, verified by execution).** Reconciliation is broken:
   `backend/work/reconciliation.py` uses `row.resulting_execution_status`,
   `details_json`, `details_hash`, `record_hash`,
   `ReconciliationMethod.AUTO_PAYPAL_STATE`, `ReconciliationMethod.MANUAL_PAYPAL_DASHBOARD`,
   `ReconciliationOutcome.INCONCLUSIVE` — none exist. Proven with a direct
   constructor call: `TypeError: 'resulting_execution_status' is an invalid
   keyword argument for ActionReconciliation`.
   Also `ReconciliationResponse` declares `before_status/after_status/detail`
   while the service passes `observed_snapshot_hash/details/reconciled_by/
   execution_status`, and `ManualReconciliationRequest` declares `outcome` while
   the service reads `req.decision`.
7. **Defect B (critical, verified by execution).** FastAPI parameter binding on
   the approval/execution routes. Proven with a live `uvicorn` on port 8021:
   `POST /api/cases/{id}/actions/approve` → `422 {"detail":[{"type":"missing",
   "loc":["query","req"],...}]}`.
8. **Defect C (high, verified by reading tests).** `tests/action_fixtures.py`
   calls `create_all()` at import against `settings.database_url`, and test files
   call `Base.metadata.drop_all(engine)` in autouse fixtures — against
   `.data/casegraph.db`, the application's own database.
9. **Defect D (high, verified by test).** `test_jwks_client_refreshes_when_new_kid_appears`
   failed: PyJWT's default 30 s cooldown means a rotated signing key is rejected
   for up to 30 s after the previous JWKS fetch.
10. **Defect E (medium, verified by reading).** `scripts/integration_gate.py`
    compared `expected_head_revision()` against a second hard-coded literal
    `"20261025_0008"` that had already drifted from the real head `20261025_0009`,
    so the gate could not pass on a correctly migrated database.
11. **Defect F (medium, verified by test run).**
    `scripts/freeze_validation_protocol.py` wrote Windows backslash paths into the
    protocol lock, so a lock frozen on Windows cannot be verified elsewhere.
12. Observed but not changed: `list_cases` performs an N+1 `detail()` query per
    case; `paypal/http.py` accepted an `idempotent` flag it never used (now used
    only as documentation); `backend/api/work.py` exposes queue internals to
    ADMIN only (acceptable).

## Phase 2 — official requirements (verified against Devpost)

13. Fetched `https://paypalaihackathon.devpost.com/` and `/rules`.
14. Deadline **Nov 12, 2026 12:00 PST**; judging has five equally weighted
    criteria (Technological Implementation, Design, Potential Impact,
    Innovation/Idea, Presentation); submission requires a functional demo
    (runnable from source or hosted), a public repo with an open-source license
    visible in "About", a <3 minute YouTube video, and a text description;
    projects must be new or significantly advanced after Oct 1, 2026.
15. Consequence for prior planning: "runnable by a judge" was **false** before
    this cycle (it needed PayPal sandbox credentials and an OpenAI key).

## Phase 3 — external research

16. Web search on PayPal Disputes API surface, chargeback-AI competitors, and
    evidence-grounded financial reasoning. Sources and what each supported are in
    [`09-source-ledger.md`](09-source-ledger.md).
17. Key findings: incumbents optimise auto-representment on card networks and are
    criticised for opaque evidence; PayPal does not ship an AI evidence builder;
    FinRCA-Bench shows retrieval/provenance architecture dominates model choice
    and that an auditable diagnosis is not implied by a correct label.

## Phase 4 — implementation

18. Reconciliation repaired end to end (model, enums, schemas, service, CLI,
    migration `20261108_0010`, `expected_head_revision`), plus service-side
    enforcement that manual reconciliation requires dashboard confirmation.
19. Action/approval API annotated; regression test added at the ASGI level.
20. Simulated PayPal transport (`backend/paypal/simulator.py`,
    `simulation_data.py`, `http.py` delegation) with production refusal in
    `backend/main.py` and `SecurityConfig.validate()`.
21. Deterministic reference reasoner (`backend/ai/providers/rules.py`) and
    provider selection with recorded provenance (`CASEGRAPH_AI_PROVIDER`).
22. `scripts/demo_seed.py`, `CASEGRAPH_SIMULATED_FAULT`, README quick-start.
23. Frontend rebuilt: `App.tsx`, `components/GraphCanvas.tsx`,
    `components/SafetyFindings.tsx`, `components/ActionComposer.tsx`,
    `lib/graph.ts`, new `styles.css`.
24. OIDC JWKS forced-refresh with rate limiting; validation-lock POSIX paths;
    integration-gate literal removed; `tests/conftest.py` DB isolation.
25. Release hygiene: `VERSION` → `1.0.0-rc2`, CHANGELOG, `.env.example`
    additions, `data/submission/submission.json` demo mode → `source`,
    `scripts/regenerate_manifest.py`, manifest regenerated (228 files).

## Phase 5 — validation (all commands and results in doc 08)

26. Full suite: **133 passed, 0 failed**.
27. `compileall` clean (with a writable bytecode prefix); ESLint-equivalent
    `tsc --noEmit` clean; `vite build` clean.
28. Alembic upgrade → downgrade → upgrade on a fresh SQLite DB; repository,
    security and operations doctors all PASS at `20261108_0010`.
29. Live HTTP journey against `uvicorn` with the simulator: sync → intake →
    analyse → safety `REVIEW` → approve → execute `EXECUTED`; graph 14 nodes /
    10 edges.

## Phase 6 — second cycle (novelty re-check and deferred delivery)

30. Probed reviewer availability for the ARIS `novelty-check` Phase C:
    `OPENAI_API_KEY`, `LLM_CHAT_BASE_URL`, `LLM_CHAT_API_KEY`,
    `ANTHROPIC_API_KEY`, `MINIMAX_API_KEY`, `CASEGRAPH_REVIEWER_MODEL` all unset;
    Codex CLI present but **explicitly unauthorized** by the mission. Phase C
    therefore did not run, and the novelty verdict is disclosed as my own
    judgement rather than cross-model validation.
31. Ran the literature sweep (ModSearch) for provenance-gated agent action.
    Found close prior art: **Agent-Sentry** (2603.22868), **Janus** (2609.38266),
    **PROVISO** (2610.27115), **HOPM** (2606.01472), and a negative-result paper
    on agentic fraud investigation (2607.19266).
32. Wrote [`11-novelty-check.md`](11-novelty-check.md), **downgraded** the novelty
    claim from "novel in composition" to PROCEED / PROCEED WITH CAUTION, and
    corrected the positioning in `04-ideas-ranked.md` and the audit README. This
    is a correction of my own earlier finding, not a new claim.
33. Delivered the deferred items: deterministic `explain` artifact + workspace
    panel, constant-query case board, frontend error boundary, configurable
    multipart timeout.
34. Validation: **143 passed, 0 failed**; typecheck clean; production build clean
    (268.51 kB JS / 82.47 kB gzip); `compileall` clean; manifest regenerated
    (232 files).

## Phase 7 — product transformation (cycle 3)

35. Verified the reported baseline before trusting it: `pytest` → **143 passed**.
36. Checked tooling. No Git repository (baseline copy is the rollback net). No
    Playwright/Puppeteer, but **headless Chrome 157 is on PATH**, which closed the
    visual-QA gap that cycle 1 could only report as a limitation.
37. Rendered the existing interface before changing anything and recorded the
    failure honestly: raw fact enums as labels, a JSON array printed as text, an
    ISO timestamp where a deadline belongs, and ~40% empty viewport.
38. Researched references (Palantir Gotham dossier, Sayari source-cited graphs,
    Bloomberg "useful density", Hoefler&Co on tabular figures and data/annotation
    hierarchy) and wrote [`12-design-direction.md`](12-design-direction.md)
    **before** touching the UI.
39. Implemented the dossier: new design system, three-pane shell, eighth backend
    capability (`readiness`), and a corrected reasoning graph (human titles, no
    JSON/ISO nodes).
40. Iterated against screenshots nine times, fixing real defects the eye caught:
    a broken CSS grid (three rows defined for two), a vertical-centring bug that
    misaligned graph columns, a layered-layout experiment that moved root nodes to
    the bottom (reverted, with the reasoning recorded in code), and prose that
    leaked `PROVIDE_SUPPORTING_INFO` into a sentence.
41. Found and fixed a bug in my own `scripts/demo_seed.py` (counted analyses, then
    ignored the count).
42. Invoked the ARIS **`figure-spec`** skill: wrote the FigureSpec JSON, validated
    it, rendered `figures/architecture.svg`, and rasterised it to check the result.
43. Validation: **147 passed, 0 failed**; TypeScript clean; production build clean
    (`279.72 kB` JS / `85.43 kB` gzip, `15.82 kB` CSS).

**Skills actually executed this cycle:** `figure-spec` (full workflow: spec →
validate → render → visual check). Not executed, with reasons: `novelty-check`
Phase C requires a Codex reviewer that this mission forbids; `auto-review-loop-llm`
has no configured API reviewer; `render-html` was replaced by a local
dependency-free renderer already in the repository. **No ARIS workflow was
repaired, reconfigured, or reinstalled.**

## Deliberately not done

- No real PayPal sandbox call: no credentials were provided, and the mission
  forbids inventing provider evidence. The live transport is unexercised this
  cycle and remains a release gate.
- No live model call: no `OPENAI_API_KEY`. The OpenAI provider path is unchanged
  and untested this cycle.
- No PostgreSQL/Redis/OIDC/ClamAV/OTel deployment validation: those need
  infrastructure this environment does not have.
- No browser screenshot QA: no browser automation was available. Frontend
  assurance is typecheck + production build + contract tests + server-side
  journey. This is a **real gap** and is listed in doc 06.
- No demo video, no license file, no repo URL, no publication: all are external
  side effects or owner decisions requiring explicit authorization.
