# Architecture

## Design principles

CaseGraph separates authoritative financial state, human-provided evidence, AI interpretation, deterministic safety, and human authorization. The AI is never allowed to become the source of financial truth or directly execute an external action.

## Core domains

### Case state

`backend/services/cases.py` synchronizes PayPal disputes into immutable/versioned local state. Graphs and analyses bind to specific case revisions so stale reasoning can be detected.

### Evidence

Support transcripts, notes, and external evidence are versioned instead of destructively overwritten. Evidence-set revisions record the exact collection of evidence used for an analysis.

### AI reasoning

The reasoning pipeline builds a frozen input bundle, records prompt/schema/provider provenance, requests structured output, validates it again locally, and compiles it into a CaseGraph only when deterministic checks pass.

### CaseGraph

The graph uses explicit epistemic node types including `VERIFIED_FACT`, `CUSTOMER_CLAIM`, `MERCHANT_CLAIM`, `AI_INFERENCE`, `MISSING_EVIDENCE`, `ACTION`, and `EVENT`. Source snapshots and excerpts preserve provenance.

### Safety

The safety layer is separate from the model. It evaluates grounding, contradictions, missing evidence, action risk, PayPal action availability, stale state, and abstention requirements.

### Action approval and execution

Approval persists an immutable typed payload and hashes that bind the action to its analysis, graph, safety decision, and policy versions. Execution receives the approval hash rather than a replacement payload, fetches current PayPal state, revalidates the action, and then performs at most one external write attempt.

### Durable work processing

Verified webhook events are persisted before acknowledgement and associated with durable work rows. Workers use leases, bounded retry/backoff, dead-letter state, and per-dispute synchronization to prevent two webhook jobs from racing the same authoritative dispute state.

### Reconciliation

Ambiguous remote action outcomes remain unresolved until they are reconciled against PayPal. The system never treats a timeout, transport failure, or uncertain 5xx as proof that an action failed.

## Runtime components

```text
React SPA
   │
   ▼
FastAPI API ───────────────► OpenAI
   │
   ├────────► PostgreSQL
   ├────────► Redis
   ├────────► Private evidence storage / ClamAV
   ├────────► OpenTelemetry Collector
   └────────► PayPal APIs

Worker ─────► PostgreSQL ───► PayPal APIs
```

## PayPal transport selection

`CASEGRAPH_PAYPAL_TRANSPORT` selects between `live` (the default; calls
`PAYPAL_BASE_URL`) and `simulated` (an in-process deterministic sandbox in
`backend/paypal/simulator.py`). The simulated transport exists so the product can
be demonstrated without credentials, and it is deliberately constrained:

- every payload it returns is stamped `"simulated": true` and carries a warning
  string, so a stored PayPal response can never be mistaken for provider truth;
- it honours the HATEOAS-link contract, so action-availability validation runs
  unmodified;
- it is refused at startup in production and reported as a configuration error by
  `SecurityConfig.validate()`, because a production process that believes it moved
  money is the worst failure this system can have.

## Reasoning provider selection

`CASEGRAPH_AI_PROVIDER` accepts `openai`, `rules`, or `auto`. The `rules` provider
is a deterministic reference reasoner used for development, the demo walkthrough,
and as a non-LLM benchmark baseline. It is never selected in production, and the
provider actually used is recorded on every analysis row (`model_provider`,
`model_name`) so provenance is never ambiguous.

## Trust boundaries

The browser is not authoritative. Authorization, stale-state validation, role checks, financial validation, file-integrity validation, and PayPal action availability are rechecked on the backend immediately before consequential operations.
