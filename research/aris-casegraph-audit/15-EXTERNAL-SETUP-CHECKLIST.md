# External setup checklist — what the owner must provide and configure

Audit of the actual repository, not of its documentation. Every requirement below
cites the code that reads it or the official page that issues it. No values were
read from `.env`; only variable **names** were inspected.

**One finding changes the AI ask — read §B.3 before buying anything.**

---

## A. Must provide

Five credentials. Everything else in this document is optional.

| # | Item | Environment variable | Type | Used by | Mandatory? |
| --- | --- | --- | --- | --- | --- |
| A1 | PayPal sandbox **REST Client ID** | `PAYPAL_CLIENT_ID` | Credential | `backend/paypal/auth.py` (HTTP Basic to `/v1/oauth2/token`) | **Yes** — for live sandbox |
| A2 | PayPal sandbox **REST Client Secret** | `PAYPAL_CLIENT_SECRET` | Credential | same | **Yes** — for live sandbox |
| A3 | PayPal **Webhook ID** | `PAYPAL_WEBHOOK_ID` | Configuration value issued by PayPal | `backend/paypal/webhooks.py:39` → sent as `webhook_id` to `/v1/notifications/verify-webhook-signature`; also a production startup gate (`backend/main.py:36`) | **Yes** — if webhook verification is on |
| A4 | An **LLM API key** for a provider that supports the OpenAI **Responses API** with strict JSON Schema | `OPENAI_API_KEY` | Credential | `backend/ai/providers/openai.py:19-43` | **Yes** — for real model output |
| A5 | The **model identifier** that key can call | `OPENAI_MODEL` | Configuration value | `backend/ai/providers/openai.py:30` | **Yes** — with A4 |

### Accounts you must have (no environment variable)

| # | Account | Needed for | Mandatory? |
| --- | --- | --- | --- |
| A6 | PayPal **Developer** account (free) | Access to the sandbox dashboard | Yes |
| A7 | PayPal **Business (merchant)** sandbox account | The seller in the dispute; the account whose dispute CaseGraph syncs | Yes |
| A8 | PayPal **Personal (buyer)** sandbox account | Raising the dispute against the merchant | Yes |

Both sandbox accounts are auto-created by PayPal when you create a sandbox app; you
do not register new ones.

---

## B. Must configure

### B.1 PayPal transport and endpoint

| Variable | Value to set | Why |
| --- | --- | --- |
| `CASEGRAPH_PAYPAL_TRANSPORT` | `live` | `simulated` is the default in tests; `live` routes through `backend/paypal/http.py` to PayPal |
| `PAYPAL_BASE_URL` | `https://api-m.sandbox.paypal.com` | Hard-checked by `Settings.is_paypal_sandbox` and by `validate_paypal_sandbox()` |
| `PAYPAL_WEBHOOK_VERIFY` | `true` | `backend/paypal/webhooks.py:19` — when false, the receiver accepts **unsigned** events. Production refuses to start unless this is true (`backend/main.py:36-37`) |
| `PAYPAL_TIMEOUT_SECONDS` | `30` (default) | Used for JSON calls in `backend/paypal/http.py` |
| `PAYPAL_MULTIPART_TIMEOUT_SECONDS` | `60` (default) | Used for evidence uploads |

### B.2 Webhook: URL, endpoint and ID are three different things

**The receiver route already exists.** Do not write a new one:

```
POST https://<your-public-host>/api/webhooks/paypal
```

- Declared in `backend/paypal/webhooks.py:12` (`prefix="/api/webhooks"`) and `:56` (`@router.post("/paypal")`).
- Registered in `backend/main.py:95` (`app.include_router(webhook_router)`).
- Registered as **public** (unauthenticated) in `backend/security/policy.py:31`:
  `_r("POST", r"/api/webhooks/paypal", public=True, requests_per_minute=240)`.

**The URL you register in PayPal must point at that route**, including the path:

```
https://<tunnel-host>/api/webhooks/paypal
```

Relationship between the three objects, precisely:

| Object | What it is | Where it lives |
| --- | --- | --- |
| Public HTTPS URL | Where PayPal sends events | Your tunnel (e.g. ngrok/Cloudflare) → your host, path `/api/webhooks/paypal` |
| CaseGraph endpoint | The FastAPI route that receives them | `backend/paypal/webhooks.py`, code — already written |
| **Webhook ID** | An identifier PayPal **issues after** you register the URL; it is the key that binds a signature to *that* registration | PayPal dashboard → your app → Webhooks. Go in `PAYPAL_WEBHOOK_ID` |

Verification flow, from the code: CaseGraph reads the five `PAYPAL-*` transmission
headers, then calls PayPal's `POST /v1/notifications/verify-webhook-signature` with
`{auth_algo, cert_url, transmission_id, transmission_sig, transmission_time,
webhook_id, webhook_event}` and requires `verification_status == "SUCCESS"`
(`backend/paypal/webhooks.py:22-53`). Consequence: **if the registered URL and
`PAYPAL_WEBHOOK_ID` do not belong to the same webhook registration, every event is
rejected with 400.** A Webhook ID is not a URL and a URL is not an ID.

**Event subscriptions to select** (the worker accepts any event whose
`resource.dispute_id` or `resource.id` starts with `PP-` and dead-letters the rest —
`backend/work/service.py:209-219`):

- `CUSTOMER.DISPUTE.CREATED`
- `CUSTOMER.DISPUTE.UPDATED`
- `CUSTOMER.DISPUTE.RESOLVED`
- `CUSTOMER.DISPUTE.ESCALATED`
- `CUSTOMER.DISPUTE.CANCELLED`

Selecting more is harmless; selecting fewer means some state changes arrive only on
manual sync.

### B.3 AI provider — **this is the decision that matters**

CaseGraph does **not** call a generic "chat" endpoint. `backend/ai/providers/openai.py`
uses the OpenAI **Responses API** with Structured Outputs:

```python
client = AsyncOpenAI(api_key=…, base_url=settings.openai_base_url or None, timeout=…)
response = await client.responses.create(
    model=settings.openai_model,
    store=False,
    instructions=DEVELOPER_INSTRUCTIONS,
    input=json.dumps(bundle, …),
    text={"format": {"type": "json_schema", "name": "casegraph_analysis",
                     "strict": True, "schema": analysis_output_schema()}},
    max_output_tokens=…,
)
```

That is `POST /v1/responses` with `strict: true` JSON Schema. **DeepSeek's public API
is OpenAI-*Chat-Completions* compatible** (`POST /v1/chat/completions`,
`response_format`), and does not serve `/v1/responses`. Pointing
`OPENAI_BASE_URL=https://api.deepseek.com` at this code would fail on the first
analysis, not return a degraded answer.

So, to answer the question directly:

> **Do not assume Harness credentials reach CaseGraph.** They do not. Harness
> authenticates *this agent session*; CaseGraph is a separate process that reads its
> own `OPENAI_API_KEY` / `OPENAI_BASE_URL` from its own environment. Nothing in the
> repository reads a Harness token, and `backend/config.py` has no such variable.

Therefore you have three options, and **only the first requires no code change**:

| Option | What you provide | Code change |
| --- | --- | --- |
| **B.3.a — OpenAI-compatible provider with Responses API** (recommended for speed) | `OPENAI_API_KEY`, `OPENAI_MODEL`, optional `OPENAI_BASE_URL` for a gateway/aggregator that exposes `/v1/responses` with strict schemas | None |
| **B.3.b — Use DeepSeek** | A DeepSeek API key **and** authorization for me to add a chat-completions adapter (`response_format: json_object`, local schema validation already exists in `validate_ai_output`) | **Yes** — new provider module; out of scope until you say so |
| **B.3.c — No key** | Nothing | None; `CASEGRAPH_AI_PROVIDER=auto` falls back to the deterministic reference reasoner, which is what every recorded run used |

Related settings, all read in `backend/config.py`:

| Variable | Default | Notes |
| --- | --- | --- |
| `CASEGRAPH_AI_PROVIDER` | `auto` | `auto` \| `openai` \| `rules`. `auto` uses the model when a key exists and **never** falls back to rules in production (`backend/ai/service.py:40-55`) |
| `OPENAI_BASE_URL` | empty | Only needed for a non-OpenAI gateway |
| `AI_TIMEOUT_SECONDS` | `60` | |
| `AI_MAX_OUTPUT_TOKENS` | `6000` | |
| `AI_MAX_BUNDLE_CHARS` | `200000` | Hard cap on the frozen bundle |

### B.4 Runtime (local demo — nothing to buy)

| Variable | Recommended for the sandbox pass | Why |
| --- | --- | --- |
| `CASEGRAPH_ENV` | `development` | `production` turns on fail-closed requirements (Postgres, enforced OIDC, Redis, ClamAV) you do not need |
| `DATABASE_URL` | default SQLite, or a Postgres URL | SQLite is fine and is what all tests use |
| `CASEGRAPH_AUTH_MODE` | `disabled` | Leaves the workspace open for the demo; also the reason uploads needed fixing |
| `CASEGRAPH_UPLOAD_ALLOW_UNSCANNED_DEV` | `true` | Lets the evidence-file path work without ClamAV |
| `CASEGRAPH_UPLOAD_DIR` | any writable path | Where evidence bytes are stored |

### B.5 Dependencies (not credentials, but the upload path breaks without them)

`python-multipart==0.0.32` is required by `File(...)` on the upload route and lives in
**`requirements-production.txt`**, not `requirements.txt`. Install both files
(`README` already says so). Forgetting it makes `/api/cases/{id}/files` fail while
everything else looks healthy.

---

## C. Optional

Not needed for the hackathon demonstration. Each is gated so you can ignore it.

| Area | Variables | When it becomes necessary |
| --- | --- | --- |
| OIDC / RBAC | `CASEGRAPH_AUTH_MODE=enforce`, `CASEGRAPH_TENANT_ID`, `CASEGRAPH_AUTH_ISSUER`, `CASEGRAPH_AUTH_AUDIENCE`, `CASEGRAPH_AUTH_JWKS_URL` **or** `CASEGRAPH_AUTH_PUBLIC_KEY_PEM`, `CASEGRAPH_AUTH_ROLES_CLAIM`, `CASEGRAPH_AUTH_TENANT_CLAIM`, `CASEGRAPH_ENFORCE_ROLE_SEPARATION` | Only if you demo authentication. Production requires it. |
| Redis rate limiting | `CASEGRAPH_RATE_LIMIT_BACKEND=redis`, `CASEGRAPH_REDIS_URL` | Multi-process deployment. Memory limiter is fine locally. |
| Malware scanning | `CASEGRAPH_UPLOAD_SCANNER=clamav`, `CASEGRAPH_CLAMAV_MAX_DB_AGE_HOURS` | Any real upload trust boundary; not for a demo. |
| OpenTelemetry | `CASEGRAPH_OTEL_ENABLED`, `CASEGRAPH_OTEL_ENDPOINT` | Production observability. |
| Browser origin allow-list | `CASEGRAPH_ALLOWED_ORIGINS` | Non-localhost frontend hosting. |
| Request limits | `CASEGRAPH_MAX_JSON_REQUEST_BYTES`, `CASEGRAPH_MAX_UPLOAD_REQUEST_BYTES`, `CASEGRAPH_UPLOAD_MAX_FILE_BYTES` | Tuning only. |
| Worker tuning | `CASEGRAPH_WORKER_*`, `CASEGRAPH_DISPUTE_LOCK_TIMEOUT_SECONDS` | Load tuning. |
| Ops gate | `CASEGRAPH_INTEGRATION_API_URL`, `CASEGRAPH_INTEGRATION_BEARER_TOKEN`, `CASEGRAPH_INTEGRATION_TEST_TOKEN` | Only for `scripts/integration_gate.py`. |
| Deployment bootstrapping | `POSTGRES_*`, `REDIS_PASSWORD`, `FORWARDED_ALLOW_IPS`, `OTEL_COLLECTOR_IMAGE` | `deploy/compose.production.yml` only. |

**Do not configure any of section C to complete the sandbox verification.** They add
failure modes without adding evidence.

---

## D. Step-by-step setup

### D.1 PayPal sandbox (A1, A2, A6–A8, B1)

1. Sign in at <https://developer.paypal.com/dashboard/> — this creates the Developer
   account (A6).
2. **Apps & Credentials → Sandbox → Create App.** Name it e.g. `casegraph-sandbox`.
3. Copy **Client ID** (A1) and **Secret** (A2) from the app page. The Secret is shown
   once; regenerate if lost.
4. The same page lists the sandbox accounts, or use
   <https://developer.paypal.com/dashboard/accounts>:
   - the **Business** account (A7) is the merchant,
   - the **Personal** account (A8) is the buyer.
   Their logins are printed there; you do not need their passwords for CaseGraph.
5. **Scopes:** CaseGraph does not request an explicit scope list — `backend/paypal/auth.py`
   posts `grant_type=client_credentials` with HTTP Basic auth and no `scope`
   parameter. PayPal grants scopes from the app's enabled features. A standard
   sandbox app can call the Disputes API; there is nothing to tick. If a call later
   returns 403, the app lacks the Disputes feature and must be recreated.
6. Create the dispute: log into the **Business** sandbox account's
   [sandbox Resolution Center](https://www.sandbox.paypal.com/) — or, more reliably,
   have a payment made from the Personal account and open a dispute from it. Note the
   dispute id from the URL (`PP-D-…`); that is what `POST /api/cases/sync/{id}` takes.

### D.2 Public webhook URL (B2)

1. Start a tunnel to port 8000, e.g. `ngrok http 8000` → `https://<random>.ngrok-free.app`.
2. In the PayPal app page → **Webhooks → Add Webhook**.
3. **Webhook URL:** `https://<random>.ngrok-free.app/api/webhooks/paypal`
   — the path is mandatory; the root URL will 404.
4. **Event types:** the five `CUSTOMER.DISPUTE.*` events from §B.2.
5. Save. PayPal shows a **Webhook ID** (A3). That is the value for `PAYPAL_WEBHOOK_ID`.
6. Keep the tunnel alive and the URL stable for the duration of testing; if ngrok
   gives you a new hostname, register again and take the **new** Webhook ID.

### D.3 AI provider (A4, A5, B.3)

- **If you choose B.3.a:** create a key at your provider (for OpenAI:
  <https://platform.openai.com/api-keys>). Set `OPENAI_API_KEY`, `OPENAI_MODEL`
  (e.g. a current model that supports Responses + structured outputs), and leave
  `OPENAI_BASE_URL` empty. If you use an aggregator, set `OPENAI_BASE_URL` to its
  `/v1` base and confirm it documents Responses API support.
- **If you choose B.3.b:** create a DeepSeek key at <https://platform.deepseek.com/api_keys>,
  then **tell me to add the adapter** — it does not work end to end without it.
- **Where to put them:** your local `.env` (gitignored, never committed) or your shell
  environment. **Do not paste secrets into this conversation**, and do not edit
  `.env.example` / `.env.production.example` with real values.

---

## E. Integration verification

What I will run once the items exist, and what counts as success.

| Item | Verification | Success criterion | Failure signature |
| --- | --- | --- | --- |
| A1/A2 | `python scripts/doctor.py`, then `POST /api/cases/sync/PP-D-…` with `CASEGRAPH_PAYPAL_TRANSPORT=live` | 200; response has `simulated: false` and real `verified_facts` including `PAYPAL_AVAILABLE_ACTIONS` | 502 "PayPal could not be reached" → network/URL; 502 "PayPal rejected the dispute lookup (401)" → bad credentials; 404 → wrong dispute id |
| A3 + tunnel | Trigger a dispute update in the sandbox while the worker runs | `paypal_events` row stored, work row completes, `case_revision` increments | 400 "invalid PayPal webhook signature" → Webhook ID/URL pair mismatch, or `PAYPAL_WEBHOOK_VERIFY=true` pointed at a stale registration |
| A4/A5 | `CASEGRAPH_AI_PROVIDER=openai` then `POST …/ai/analyze` | Analysis `COMPLETED`, `model_provider="openai"`, graph compiled, `validation_status=PASSED` | `FAILED_PROVIDER` with a message naming the API error — a 404 on `/responses` means the base URL does not serve the Responses API (the DeepSeek case) |
| Full lifecycle | The 11 steps in [`docs/PAYPAL_SANDBOX_RUNBOOK.md`](../docs/PAYPAL_SANDBOX_RUNBOOK.md) | One human-approved action executes once and is visible in the PayPal dashboard; an injected timeout yields `UNKNOWN_OUTCOME` and is not retried | Any automatic retry, or `EXECUTED` without the action appearing in PayPal, is a defect I must fix before release |

I will record the actual HTTP statuses, `case_revision`, `approval_hash` and
`execution_status` per step into
`research/aris-casegraph-audit/08-verification-record.md`. Until that section exists,
the integration is unverified — including anything I might be tempted to imply.

---

## F. Final submission blockers

| Blocker | Resolvable by you | Resolvable by me autonomously |
| --- | --- | --- |
| Live PayPal sandbox pass | **Yes** — A1, A2, A3, A6–A8, tunnel (§B.1, §B.2) | Only with those values present |
| Real model pass | **Yes** — A4, A5 (or authorize B.3.b for DeepSeek) | No — needs a key |
| Webhook verification | **Yes** — tunnel + registration | No |
| Open-source licence | **Yes** — a decision; MIT recommended in [`docs/PUBLIC_REPO_CHECKLIST.md`](../docs/PUBLIC_REPO_CHECKLIST.md) | No — legal decision, and I will not create one unauthorized |
| Repository URL, demo video, contact, team | **Yes** — accounts and recording | No — external side effects |
| License/README/submission metadata edits once you decide | No | **Yes** |
| Secret scan clean run | **Yes** — remove or relocate the local `.env` before archiving, or use the sanitized release pipeline | **Yes**, given an `.env`-free tree |
| Independent cross-model review of the claims | **Yes** — an API reviewer key | No — none configured, and Codex is out of scope |
| Browser QA, tests, build, manifest | No | **Yes** — already executed; I will re-run on request |

### The shortest path to "integration verified"

1. PayPal app → Client ID, Secret (D.1).
2. Tunnel → register `…/api/webhooks/paypal` + five dispute events → Webhook ID (D.2).
3. One model key + model id that serves the Responses API (D.3, option B.3.a).
4. Put the four values in your local environment; tell me they are set — **not the
   values**.
5. I run the lifecycle, record the evidence, and update the release report.

Total: four values. Everything in section C can stay unset.

---

## Source references

| Claim | Reference |
| --- | --- |
| Credential/transport settings | `backend/config.py` (`Settings` fields, `is_paypal_sandbox`, `validate_paypal_sandbox`) |
| OAuth with no explicit scopes | `backend/paypal/auth.py` — `data={'grant_type':'client_credentials'}`, HTTP Basic |
| Webhook path and verification | `backend/paypal/webhooks.py:12,19-53,56`; `backend/security/policy.py:31`; `backend/main.py:95` |
| Worker's event acceptance rule | `backend/work/service.py:209-219` |
| Responses API + strict schema | `backend/ai/providers/openai.py:22-43` |
| Provider selection and production fail-closed | `backend/ai/service.py:34-55` |
| Production startup gates | `backend/main.py:33-44` |
| Security/upload/OIDC settings | `backend/security/config.py` (`SecurityConfig.from_env`) |
| Optional production profile | `.env.production.example` |
| Dependency split (`python-multipart`) | `requirements.txt`, `requirements-production.txt` |
| Release gates | `docs/RELEASE_CHECKLIST.md` |
| PayPal Disputes API surface | <https://developer.paypal.com/api/customer-disputes/v1/> (verified: 3 `disputes` + 12 `disputes-actions` endpoints, matching `backend/paypal/disputes.py`) |
| Webhook signature verification contract | PayPal's `POST /v1/notifications/verify-webhook-signature`, as used in `backend/paypal/webhooks.py` |
