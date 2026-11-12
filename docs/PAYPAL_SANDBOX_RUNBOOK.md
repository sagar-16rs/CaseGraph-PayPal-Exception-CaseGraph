# PayPal sandbox runbook

**Status: not executed.** No PayPal sandbox credentials exist in this environment
(`PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_WEBHOOK_ID` are all unset).
Nothing in this repository claims a live sandbox pass. Everything below is the
procedure to obtain that evidence, plus exactly what must be observed.

The simulated transport (`CASEGRAPH_PAYPAL_TRANSPORT=simulated`) exercises the same
service, validation, safety and approval code against a local stand-in. It proves
the *application* works. It does **not** prove the *integration* works, and the two
must not be conflated in a submission.

## 1. Prerequisites

1. PayPal developer account and a **sandbox** app at <https://developer.paypal.com/dashboard/applications/sandbox>.
2. Sandbox merchant and buyer accounts with a completed payment between them.
3. A dispute raised against that payment, visible in the sandbox Resolution Center.
4. A public HTTPS endpoint for webhooks (e.g. an ngrok tunnel), registered for:
   - `CUSTOMER.DISPUTE.CREATED`
   - `CUSTOMER.DISPUTE.UPDATED`
   - `CUSTOMER.DISPUTE.RESOLVED`

## 2. Configuration

```bash
export CASEGRAPH_ENV=development
export CASEGRAPH_PAYPAL_TRANSPORT=live
export PAYPAL_BASE_URL=https://api-m.sandbox.paypal.com
export PAYPAL_CLIENT_ID=<sandbox client id>
export PAYPAL_CLIENT_SECRET=<sandbox secret>
export PAYPAL_WEBHOOK_ID=<webhook id>
export PAYPAL_WEBHOOK_VERIFY=true
export OPENAI_API_KEY=<key>          # or CASEGRAPH_AI_PROVIDER=rules
```

Preflight — must exit non-zero if anything is missing:

```bash
python scripts/doctor.py
python scripts/integration_doctor.py
python scripts/security_doctor.py
```

## 3. Lifecycle to execute, in order

| # | Step | Command / action | Evidence it worked |
| --- | --- | --- | --- |
| 1 | Retrieve the dispute | `POST /api/cases/sync/{PP-D-...}` | 200 with `simulated: false`, facts including `PAYPAL_AVAILABLE_ACTIONS` |
| 2 | Confirm allowed responses | inspect `allowed_response_options` | Only actions present in PayPal's HATEOAS `links` appear |
| 3 | Attach evidence | `POST /api/cases/{id}/intake`, upload a PDF | evidence-set revision increments |
| 4 | Analyse | `POST /api/cases/{id}/ai/analyze` | `COMPLETED`, graph revision created |
| 5 | Read the safety verdict | `GET …/ai/analyses/{uid}/explain` | `verdict.effective_action` is one PayPal actually exposes |
| 6 | Approve the exact payload | `POST /api/cases/{id}/actions/approve` | `approval_hash` returned; payload round-trips |
| 7 | Execute once | `POST …/actions/{uid}/execute` | `EXECUTED`; PayPal shows the action in the dispute |
| 8 | Verify server-side | PayPal dashboard / `GET` dispute | the message or evidence is present |
| 9 | Webhook | trigger an update in the sandbox | event stored, work row completed, case revision increments |
| 10 | Ambiguity | repeat 7 with the network cut mid-request | `UNKNOWN_OUTCOME`, never retried |
| 11 | Reconcile | `POST …/reconcile` | `INCONCLUSIVE` while unproven; CLI release only with dashboard confirmation |

## 4. What to record

For each step: HTTP status, `case_revision`, `approval_hash`, `execution_status`, and
the PayPal-side observation. Paste them into
`research/aris-casegraph-audit/08-verification-record.md` under a new "Live sandbox"
section and change the status line at the top of this document. Until that happens,
the integration remains unverified.

## 5. Hard rules (do not relax to make a demo work)

- Sandbox only. Never point `PAYPAL_BASE_URL` at production.
- `PAYPAL_WEBHOOK_VERIFY=true`; an unverified webhook is rejected with 400.
- Exactly one external write attempt per approval hash.
- A timeout, transport error or 5xx is `UNKNOWN_OUTCOME`, never `FAILED`.
- Only an operator who has checked the PayPal dashboard may release that block.
- Never retry an ambiguous write, and never edit `alembic_version` or an approval row.
