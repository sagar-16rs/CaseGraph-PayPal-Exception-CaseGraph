# PayPal integration assessment

## Surface actually implemented

`backend/paypal/disputes.py` wraps these `v1/customer/disputes` operations, all
with caller-supplied idempotency intent and per-operation names:

| Operation | Method/path | Local action type |
| --- | --- | --- |
| list disputes | `GET /v1/customer/disputes` | — |
| dispute details | `GET /v1/customer/disputes/{id}` | — |
| send message | `POST …/{id}/send-message` | `SEND_MESSAGE` |
| provide evidence (multipart) | `POST …/{id}/provide-evidence` | `PROVIDE_EVIDENCE` |
| appeal (multipart) | `POST …/{id}/appeal` | `APPEAL` |
| make offer | `POST …/{id}/make-offer` | `MAKE_OFFER` |
| accept claim | `POST …/{id}/accept-claim` | `ACCEPT_CLAIM` |
| escalate | `POST …/{id}/escalate` | `ESCALATE` |
| provide supporting info | `POST …/{id}/provide-supporting-info` | `PROVIDE_SUPPORTING_INFO` |
| acknowledge return item | `POST …/{id}/acknowledge-return-item` | `ACKNOWLEDGE_RETURN_ITEM` |
| verify webhook signature | `POST /v1/notifications/verify-webhook-signature` | — |

**Verified against the official Disputes v1 reference:** all eleven endpoints
exist with those paths and methods, and `provide-evidence` is multipart with an
`input` part plus file parts — which is how `PayPalHTTP.multipart_input` builds
the request. This is a faithful implementation of the documented surface, not an
invented one.

## Correctness details that matter

- **Action availability comes from HATEOAS links, not from a local guess.**
  `case_service._supported_actions` derives `allowed_response_options` only from
  the `links[].rel` values PayPal returned, and
  `actions/validation.py::validate_action_payload_against_dispute` re-checks that
  the specific `rel` is present on *live* PayPal state immediately before a write.
  This is the right contract: the merchant's opinion about what is allowed is
  never authoritative.
- **Money ceilings are enforced against PayPal's own numbers.**
  `MakeOfferPayload` / `AcceptClaimPayload` amounts are compared to
  `refund_details.allowed_refund_amount` (falling back to `dispute_amount`), and
  the currency must match. A refund larger than PayPal permits is rejected with
  422 before approval and again at execution.
- **Evidence documents are hash-bound.** `EvidenceFileRef` carries
  `{file_uid, sha256}`; `resolve_action_files` re-reads stored bytes, re-hashes
  them, rejects a mismatch, and `build_paypal_evidence_payload` re-hashes again at
  send time. A file swapped between approval and execution fails closed.
- **Non-idempotent writes are treated as such.** `idempotent=False` is passed for
  every dispute POST, and `ActionEngine` performs at most one external write
  attempt per approval hash.
- **Transport failures are classified, not assumed.** `PayPalTransportError` and
  `PayPalAPIError(>=500)` → `UNKNOWN_OUTCOME`; explicit 4xx → `FAILED`.

## Gaps and risks (not fixed this cycle)

1. **No `PayPal-Request-Id` header.** PayPal honours `PayPal-Request-Id` for
   several APIs as a deduplication key. CaseGraph deliberately does not rely on
   it because the Disputes write endpoints do not document it as idempotent — the
   conservative choice — but the header is also not *sent*, so if PayPal did
   deduplicate, CaseGraph cannot benefit. Worth a documented experiment in the
   sandbox rather than a code change on faith.
2. **`paypal_timeout_seconds` is now honoured for JSON calls but multipart still
   hard-codes 60 s.** Evidence uploads legitimately need a longer timeout, but the
   value should be a setting.
3. **No HTTP connection pooling.** A fresh `httpx.AsyncClient` per call.
4. **Rate-limit (429) handling is coarse.** 429 is treated as `FAILED` (correct —
   nothing was processed), but there is no `Retry-After` awareness anywhere.
5. **The live transport is unexercised in this cycle.** No credentials were
   available and none were fabricated. Every claim about PayPal above is about
   *code correctness against the documented contract*, not about a successful
   sandbox run. This must be closed before submission.
6. **Webhook verification depends on a network call inside the request path.** If
   PayPal's verification endpoint is slow, webhook acknowledgement is slow. There
   is no local certificate caching. Acceptable fail-closed behaviour, worth a
   timeout budget note.

## The simulated transport added this cycle

To make the product demonstrable without credentials, `backend/paypal/simulator.py`
implements the same operation names against a JSON state file:

- returns PayPal-shaped payloads including `links`, `allowed_response_options`,
  `refund_details`, `disputed_transactions`, `seller_response_due_date`;
- mutates `status`/`dispute_life_cycle_stage` on writes so the post-write
  revalidation and sync paths are genuinely exercised;
- bumps `simulation_revision` on every write so `paypal_snapshot_hash` changes and
  case revisions advance exactly as they would with a real provider;
- stamps every payload `"simulated": true` plus an explicit warning string;
- supports fault injection (`CASEGRAPH_SIMULATED_FAULT=timeout|server_error`) on
  write operations only, so the `UNKNOWN_OUTCOME` path can be demonstrated while
  reads keep working.

**Safety properties, verified:** the application refuses to start in production
with the simulated transport (`backend/main.py` lifespan) and
`SecurityConfig.validate()` reports a production configuration error. The
simulated path cannot be reached with `CASEGRAPH_ENV=production`.

**Honest limitation:** the simulator is a *demonstration* device. It is not a
PayPal conformance suite, and passing against it does not imply the live
integration works.
