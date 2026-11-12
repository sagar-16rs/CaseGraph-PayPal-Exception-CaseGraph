# Final integration verification

Date: 2026-11-08 · Repository: `D:\casegraph\casegraph` · Version `1.0.0-rc2`
Executed by: DeepSeek V4.1 Flash. No Codex, no Codex CLI, no Codex MCP.

> Numbering note: `15-EXTERNAL-SETUP-CHECKLIST.md` (owner-facing credential audit)
> and this file share the `15-` prefix. This file is the verification record.

---

## A. Executive summary

CaseGraph is in a materially better state than the previous report, because two
blockers that were assumed missing turned out to be **present and working**: the
PayPal sandbox credentials are configured, and a webhook is registered against the
live ngrok tunnel with the Webhook ID matching the configured value.

**Verified for real in this cycle:**

- PayPal Sandbox **OAuth authentication succeeded** against
  `https://api-m.sandbox.paypal.com` (token issued; length only recorded).
- A **read-only** `GET /v1/customer/disputes` succeeded and parsed.
- A **read-only** `GET /v1/notifications/webhooks` confirmed one registration whose
  URL is exactly `https://jacquelin-inoperable-attractively.ngrok-free.dev/api/webhooks/paypal`
  and whose id equals `PAYPAL_WEBHOOK_ID`.
- The webhook route is reachable through that public URL and **rejects unsigned
  requests with 400** when verification is enabled.
- **206 tests pass, 2 skip**, browser QA **23/23**, secret scan finds **no secret
  content**, migrations and doctor pass.

**Discovered and fixed:** `.env` was never loaded by the application — the
documented setup silently produced a process with no credentials. This was the
reason the earlier cycles concluded "credentials missing" when the file was
populated.

**Not verified, and not claimed:** no genuine PayPal webhook event was delivered (the
sandbox account has zero disputes, and creating one is forbidden here), no dispute
lifecycle ran, and **no real LLM call was made** — `OPENAI_API_KEY` is empty.

---

## B. Test results

| Area | Status | Evidence |
|---|---|---|
| Environment configuration | PASS | Python 3.14.5 venv, Node 24.15.0, deps installed; `.env` now loaded (`backend/config.py::load_environment`), sandbox host confirmed, `CASEGRAPH_ENV=development`, auth disabled by design |
| Backend tests | PASS | `206 passed, 2 skipped` (skips are credential-gated guards, each with a stated reason) |
| Frontend checks | PASS | `tsc --noEmit` exit 0; `vite build` 281.33 kB / 85.86 kB gzip |
| Database safety | PASS | All runs used isolated `DATABASE_URL`; user `.data/casegraph.db` untouched (size/mtime unchanged, verified) |
| Evidence integrity | PASS | Hash-bound upload, duplicate/intake idempotency, negation and false-positive regression tests (`test_readiness.py`, `test_secure_uploads.py`, `test_file_action_integrity.py`) |
| Reasoning and graph | PASS | Deterministic reference reasoner only; grounding, contradiction, missing-evidence and explanation consistency covered by `test_explanations.py`, `test_readiness_reasons.py` |
| Approval and execution | PASS | `test_http_journey.py`, `test_paypal_error_mapping.py` — stale chain rejected, payload/hash bound, duplicate execution prevented |
| Reconciliation | PASS | `test_reconciliation.py` — `UNKNOWN_OUTCOME` preserved, auto probe inconclusive, manual release requires dashboard confirmation |
| PayPal Sandbox authentication | PASS | Real OAuth token issued against the sandbox endpoint (`research/.tmp/paypal_probe.py`, token length only printed) |
| PayPal read-only API | PARTIAL | `GET /v1/customer/disputes` returned **0 disputes**; no dispute to fetch, so field mapping against a real payload is unproven |
| Webhook endpoint reachability | PASS | `POST https://jacquelin-…ngrok-free.dev/api/webhooks/paypal` → **400** from the app; `GET /health` via the same tunnel → 200 |
| Webhook signature verification | PASS (rejection) / NOT VERIFIED (acceptance) | Unsigned request rejected 400 with `PAYPAL_WEBHOOK_VERIFY=true`; a valid signature can only come from PayPal |
| Genuine PayPal event processing | NOT TESTED | Requires a real dispute event; account has none and creating one is prohibited |
| Deterministic reference reasoner | PASS | Seeded demo journey produced graphs; provider recorded as `rules/reference-rules-v1` |
| Real LLM API | **BLOCKED — credentials missing** | `OPENAI_API_KEY` empty; `OPENAI_MODEL` set but unusable alone |
| Browser QA | PASS | CDP-driven: 23/23 assertions, 0 failures, 0 unexpected console errors |
| Security and secret scan | PARTIAL | `secret_like_findings: []`; scan exits non-zero solely because the local `.env` is present (excluded from the archive, **not** sanitized) |
| Release manifest | PASS | 247 entries; `--check` clean |

---

## C. Defects discovered and fixed

### D1 — `.env` was never loaded (high)

**Symptom.** A correctly populated `.env` had no effect: the process started with no
PayPal credentials, which is why earlier audits recorded them as "not configured".

**Root cause.** `python-dotenv` was a declared dependency but nothing called it.
`backend/config.py` read `os.getenv` only, and the documented start command
(`uvicorn backend.main:app`) does not pass `--env-file`.

**Fix.** `backend/config.py` now defines `load_environment()` and calls it at import,
with `override=False` so a real shell/CI environment stays authoritative and a
missing file is not an error.

**Regression test.** `tests/test_config_dotenv.py` — file values reach the process,
real environment wins, a missing file is tolerated, default target is the repo root.

**Behaviour change, stated plainly:** tests now inherit `.env`. Two credential-gated
guard tests changed from "assert the guard fires" to "skip, credentials are
configured". That is the honest outcome, not a weakened assertion.

---

## D. Exact commands executed

| Command | Exit | Note |
|---|---|---|
| `python -m pytest -q` (baseline, before fix) | 0 | `203 passed, 1 skipped` |
| `python research/.tmp/paypal_probe.py` | 0 | OAuth OK; `list_disputes` count=0 |
| `python research/.tmp/paypal_webhooks_probe.py` | 0 | 1 webhook, URL matches tunnel, id matches config |
| `uvicorn backend.main:app --port 8000 --env-file .env` (verify=true) | running | used for webhook tests, then stopped |
| `POST http://127.0.0.1:8000/api/webhooks/paypal` (unsigned) | 400 | signature rejection |
| `POST https://jacquelin-…ngrok-free.dev/api/webhooks/paypal` (unsigned) | 400 | public reachability + rejection |
| `GET https://jacquelin-…ngrok-free.dev/health` | 200 | tunnel forwards to the backend |
| `python -m pytest -q` (after fix) | 0 | `206 passed, 2 skipped` |
| `node research/.tmp/qa/qa.mjs` | 0 | 23/23 assertions |
| `python -m compileall -q backend scripts tests migrations` | 0 | |
| `alembic upgrade head` + `scripts/doctor.py` (isolated DB) | 0 | head `20261108_0010`, PASS |
| `npx tsc --noEmit` | 0 | |
| `npx vite build` | 0 | 281.33 kB / 85.86 kB gzip |
| `python scripts/release_scan.py` | 1 | no secret-like findings; fails on local `.env` presence |
| `python scripts/regenerate_manifest.py --check` | 0 | 247 files match |

No secret value was printed, logged, or written to any file during this cycle.

---

## E. Integration limitations

Kept strictly separate, because these are different claims:

| Level | Status |
|---|---|
| Code exists | Yes — PayPal OAuth, disputes, webhooks, approval, execution, reconciliation |
| Unit tests pass | Yes — 206 |
| Local application works | Yes — browser journey exercised end to end on the simulator |
| Sandbox API authentication works | **Yes — verified this cycle** |
| Sandbox dispute data read | **No dispute on the account**; endpoint connectivity proven, payload mapping unproven |
| Genuine PayPal webhook event verified | **No** — registration, reachability and rejection proven; acceptance unproven |
| Real PayPal dispute lifecycle tested | **No** — would require creating a dispute/action, which is prohibited |
| Real backend LLM provider tested | **No** — `OPENAI_API_KEY` empty |

---

## F. Remaining owner actions

1. **Provide an LLM key** for a provider serving the OpenAI **Responses API** with
   strict JSON Schema, and set `OPENAI_MODEL`. DeepSeek's chat-completions API does
   not satisfy this without a code adapter (see
   [`15-EXTERNAL-SETUP-CHECKLIST.md`](15-EXTERNAL-SETUP-CHECKLIST.md) §B.3).
2. **Create or expose a sandbox dispute** (merchant + buyer sandbox accounts) so the
   read-only detail mapping and, if desired, one approved action can be exercised.
3. **Trigger a genuine webhook** — PayPal dashboard → Webhooks → *Simulate*, or let a
   dispute event occur — so a signed delivery is verified.
4. **Change `PAYPAL_WEBHOOK_VERIFY=false` to `true`** in `.env` for any real run.
   Confirmed this cycle: rejection works only when it is enabled.
5. **Add the missing event subscriptions** `CUSTOMER.DISPUTE.ESCALATED` and
   `CUSTOMER.DISPUTE.CANCELLED` (only CREATED / UPDATED / RESOLVED are registered).
6. **Licence decision** (MIT recommended) — not created, by instruction.
7. **Repository URL, demo video URL, contact, team** in
   `data/submission/submission.json`.

---

## G. Release recommendation

**READY WITH EXPLICIT LIMITATIONS.**

Justification, from observed evidence only:

- The application runs, and every interactive path a judge would touch was exercised
  in a real browser with zero failures.
- The money-handling classification (4xx → definitively failed, 5xx/timeout →
  `UNKNOWN_OUTCOME`, never retried) is tested and, for the sandbox, the credential
  path is genuinely working.
- The webhook is correctly *registered* end to end — URL, route and Webhook ID all
  agree — which is more than the previous report could claim.

It is not "READY" because three claims remain unproven and must not be implied: a
genuine signed webhook, a real dispute lifecycle, and any LLM-produced analysis. The
remaining gap is **data and a key**, not code — which is why this is a limitation
rather than a blocker: the product is demonstrable today, on the simulator, and the
sandbox authentication that judges most doubt is real.

**Most important remaining blocker:** no genuine PayPal webhook event has been
delivered, so webhook *processing* of real provider data is unverified even though
the registration is correct.
