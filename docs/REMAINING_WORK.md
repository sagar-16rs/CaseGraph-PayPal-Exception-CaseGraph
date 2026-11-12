# Remaining work — owner handoff

All code, configuration, licensing, secret-sanitization, and provider-adapter tasks
are complete and verified:
- **212 tests pass, 0 failed, 0 skipped**
- **`LICENSE` (MIT)** added and declared in `data/submission/submission.json` and `README.md`
- **`.env.example` sanitized** (`PAYPAL_WEBHOOK_VERIFY=true`, no embedded credentials, `OPENAI_BASE_URL` clean)
- **Chat-Completions / DeepSeek adapter** implemented in `backend/ai/providers/openai.py` (`CASEGRAPH_AI_API_MODE=auto|responses|chat_completions`)
- **All repository doctors (`doctor.py`, `security_doctor.py`, `integration_doctor.py`, `operations_doctor.py`, `benchmark_doctor.py`, `validation_doctor.py`, `submission_doctor.py`) and `release_scan.py` pass**
- **`MANIFEST.sha256` and public release archive (`verify_public_release.py`) pass**

What follows requires your external PayPal Developer / Devpost / YouTube accounts at submission time.

Do **not** paste secrets into a chat or a file that could be committed. Put them in
your local `.env` (already gitignored).

---

## 1. PayPal Sandbox live dispute & webhook simulation (external account action)

### 1.1 Signature verification is now `true` in `.env.example` (Done)

- `.env.example` now defaults to `PAYPAL_WEBHOOK_VERIFY=true`. When you create your local `.env` for live sandbox testing, keep `PAYPAL_WEBHOOK_VERIFY=true` so unsigned webhook requests are rejected with **400**.

### 1.2 Add the two missing event subscriptions in PayPal Dashboard

- **Where:** PayPal Developer Dashboard → Apps & Credentials → Sandbox → your app → Webhooks → edit the existing webhook.
- **Steps:** add `CUSTOMER.DISPUTE.ESCALATED` and `CUSTOMER.DISPUTE.CANCELLED` alongside `CREATED`, `UPDATED`, `RESOLVED`; save.

### 1.3 Deliver one genuine webhook event & sandbox dispute

- **Where:** PayPal Developer Dashboard → Webhooks → **Simulate**, or raise a dispute between your Personal (buyer) and Business (merchant) sandbox accounts.
- **Verify:** `POST /api/cases/sync/<PP-D-id>` with `CASEGRAPH_PAYPAL_TRANSPORT=live` returns 200 with `simulated: false` and populated `verified_facts`.

---

## 2. Live LLM provider (adapter ready)

### 2.1 Both OpenAI `/v1/responses` and DeepSeek / `/v1/chat/completions` are now supported in code (Done)

- `backend/ai/providers/openai.py` now supports both the OpenAI **Responses API** (`CASEGRAPH_AI_API_MODE=responses`) and OpenAI-compatible **Chat Completions** (`CASEGRAPH_AI_API_MODE=chat_completions`, or automatic detection in `CASEGRAPH_AI_API_MODE=auto` when `OPENAI_BASE_URL=https://api.deepseek.com` or `DEEPSEEK_API_KEY` is set).
- **To run with OpenAI:** set `OPENAI_API_KEY` and `OPENAI_MODEL=gpt-5.6` in your local `.env`.
- **To run with DeepSeek:** set `DEEPSEEK_API_KEY` (or `OPENAI_API_KEY` + `OPENAI_BASE_URL=https://api.deepseek.com`) and `OPENAI_MODEL=deepseek-chat` in your local `.env`.
- **Without a key:** `CASEGRAPH_AI_PROVIDER=auto` continues to use the deterministic reference reasoner (`model_provider="rules"`) outside production.

---

## 3. Licensing and repository publication

### 3.1 MIT Licence (Done)

- `LICENSE` (MIT) has been created at the repository root, `open_source_license` is set to `"MIT"` in `data/submission/submission.json`, and `README.md` links to `LICENSE`.

### 3.2 Publish the repository

- Push the clean repository tree to your public GitHub repository (without your local `.env`), and set `repo_url` in `data/submission/submission.json`.

---

## 4. Demo recording and hackathon submission

### 4.1 Record the demo

- Follow `docs/DEMO_SCRIPT.md` (< 3 minutes), verify duration with `python scripts/check_demo_video.py <file>`, upload to YouTube as public, and set `youtube_video_url`, `contact`, and `team` in `data/submission/submission.json`.
- Run `python scripts/submission_doctor.py --repo . --submission-ready` to confirm all strict submission gates report `PASS`.
