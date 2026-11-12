# Release readiness — final

Supersedes the gate table in [`13-final-qa-and-release.md`](13-final-qa-and-release.md),
which remains as the record of that phase. This page separates what was **executed**,
what is **externally blocked**, and what remains **unverified**.

## Completed and evidenced

| Area | What was executed | Evidence |
| --- | --- | --- |
| Test suite | `pytest` from a clean run | **203 passed, 1 skipped** (the skip is credential-gated) |
| Frontend | `tsc --noEmit`, `vite build` | exit 0; 281 kB JS / 86 kB gzip |
| Interactive QA (pass 1) | CDP: graph, node inspector, composer validation, approve → execute, error notice, Tab traversal with focus rings, 900 px layout, 8 contrast roles | **22/22 assertions**, 0 page errors |
| Interactive QA (pass 2) | CDP: file-upload picker, hover, transition presence, keyboard activation, 11 contrast roles | **16/16 assertions**, 0 console errors, 0 failed requests |
| PayPal HTTP mapping | 401 / 403 / 404 / 422 / 429 vs 500 / 502 / 503 / 504, plus transport timeout | 12 tests: client rejections → `FAILED`, never resent; server/transport → `UNKNOWN_OUTCOME`, never retried; an ambiguous action blocks a second approval; the transport preserves provider status and body |
| Evidence readiness | all eight dispute reasons, complete packs, unrelated packs, contradiction downgrade, ambiguous signal, missing-evidence precedence | 28 tests, all passing |
| Readiness honesty | serialised payload must not contain probability/win-rate language | enforced by test |
| Release gates | `compileall`, Alembic upgrade→downgrade→upgrade, repository/integration doctors, `MANIFEST.sha256 --check` | all pass |
| Documentation | design direction, architecture diagram, QA record, PayPal runbook, public-repo checklist, demo script | in `docs/` and `research/aris-casegraph-audit/` |

### Defects fixed in this phase

1. **Upload returned HTTP 500 in the demo profile** — `request.state.actor` is `None`
   when authentication is disabled, so `actor.subject` raised. Every judge running
   the no-credential demo would have hit this on the evidence upload. Fixed, with a
   regression test.
2. **Missing favicon** — a 404 on every page load. Replaced with an inline SVG mark.
3. **Invalid dispute id → HTTP 500** — now 404 with a message that says state was not
   changed (previous phase, re-verified).
4. **Three text roles below AA contrast** — measured 4.11:1, re-measured 5.31:1
   (previous phase, re-verified with an expanded role set).
5. **Masthead overflow at 900 px** (previous phase, re-verified).
6. **Negated and false-positive evidence matching** — "no delivery proof" and
   "IP address" both used to satisfy requirements (previous phase, expanded tests).

## Externally blocked

| Item | Why | What exists instead |
| --- | --- | --- |
| **PayPal sandbox lifecycle** | No `PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET` / `PAYPAL_WEBHOOK_ID` in this environment. I did not fabricate credentials or claim a pass. | [`docs/PAYPAL_SANDBOX_RUNBOOK.md`](../docs/PAYPAL_SANDBOX_RUNBOOK.md) with the 11-step lifecycle and the evidence each step must produce; guards proven by `tests/test_paypal_live_gate.py` |
| **DeepSeek / OpenAI model run** | No `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `OPENAI_BASE_URL` or `ANTHROPIC_API_KEY` is set. The `rules` provider is the deterministic reference reasoner, **not** a model. | Provider selection is explicit and recorded per analysis (`model_provider`, `model_name`); `CASEGRAPH_AI_PROVIDER=auto` prefers a real model when a key exists and never in production |
| **Licence file** | Choosing a licence is an owner legal decision; the instruction forbids creating one without authorization. | MIT recommended with rationale in [`docs/PUBLIC_REPO_CHECKLIST.md`](../docs/PUBLIC_REPO_CHECKLIST.md) |
| **Repository URL, demo video, contact** | Owner actions with external side effects. | Demo script at [`docs/DEMO_SCRIPT.md`](../docs/DEMO_SCRIPT.md); `submission.json` fields left as `CHANGE_ME` |

## Unverified

- **Live PayPal behaviour** in any form: OAuth, dispute retrieval, evidence upload,
  webhooks, real-world error bodies. The error-mapping tests use injected provider
  errors, which proves CaseGraph's classification, not PayPal's responses.
- **Any model's output quality.** No LLM has produced a graph in this repository's
  recorded history; only the deterministic reference reasoner has.
- **PostgreSQL, Redis, OIDC, ClamAV, OpenTelemetry, Docker Compose.**
- **Browser coverage beyond the assertions listed**: hover on every surface, the
  150 ms view transition visually, drag/drop, and mobile widths below 900 px.
- **Contrast for `--claim` and `--caution` on `--paper`** specifically; measured
  roles pass, but the token set was not exhaustive.
- **Accessibility beyond contrast and keyboard order**: no screen-reader run, no
  automated axe audit.
- **User benefit.** No study, no win-rate measurement, no time-saving claim. The
  repository's claim ledger correctly reports `user_study_status: PENDING`.

## Submission gate (actual output)

```
python scripts/submission_doctor.py --repo .
  demo_mode            true      (functional_demo_mode: source)
  claim_ledger         true
  rules_snapshot       true
  validation_framework true
  readme               true
  secret_scan          false     <- local .env present; sanitized archive path required
  open_source_license  false     <- BLOCKING: owner decision
  license_declared     false     <- BLOCKING: owner decision
  repo_url             false     <- BLOCKING: owner action
  video_url            false     <- BLOCKING: owner action
status: FAIL
```

## Recommendation

The application is in a state I would demonstrate publicly: it runs with no
credentials, every interactive path a judge would touch has been exercised over a
real browser, the money-handling classification is tested against the statuses that
matter, and the evidence layer no longer lies about negated or contradicted
evidence.

It is **not** submission-complete. Three of the four blocking items are the owner's
to resolve, and the fourth — the live PayPal pass — is the one I most want to see
done before anyone says "integrated with PayPal" without qualification.
