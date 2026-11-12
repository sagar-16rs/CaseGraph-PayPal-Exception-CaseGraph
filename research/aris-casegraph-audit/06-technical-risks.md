# Technical risks

Ordered by expected damage. "New" means introduced or materially changed this
cycle.

## Blocking a submission

**R1 — No live PayPal verification (pre-existing).** Every PayPal claim in this
repository is about code correctness against the documented contract. The live
transport has not run. If the submitter publishes before a sandbox pass, the
product's central claim is unproven. *Mitigation:* run the sandbox gate; the
simulator deliberately does not count as evidence.

**R2 — No licence file (pre-existing).** Automatic rule failure. Owner decision.

**R3 — No browser visual QA (new surface).** The frontend was rebuilt and passes
`tsc --noEmit` and `vite build`, but no browser automation was available, so
layout, overflow, and interaction quality are unverified. Specific things I would
check first: the graph canvas at more than seven columns (horizontal scroll and
column headers), the typed composer with `MAKE_OFFER` + `REFUND_WITH_RETURN`
(the return address fields are hard-coded to a placeholder merchant address and
will look odd in a demo), and contrast of the `SIMULATED SANDBOX` badge on the
dark header. *Mitigation:* a 10-minute manual pass before recording the video.

## Product / design

**R4 — The reference reasoner could be mistaken for the AI (new).** It produces
plausible graphs without a model. It is labelled in three places
(`model_provider="rules"`, `model_name="reference-rules-v1"`, an explicit
`uncertainties` entry, and the README), and it is never selected in production.
The residual risk is a demo that showcases the reference reasoner and lets a
judge assume that is the AI. *Mitigation:* when recording, show the analysis
provenance panel with an `openai` provider, or state it in the narration.

**R5 — Simulated sandbox dilutes the "payments" credibility (new).** A payments
judge may discount a demo that does not touch PayPal. *Mitigation:* keep the
simulated run as the *setup-free* path and the real sandbox run as the evidence
path; the README already orders them that way.

**R6 — Reconciliation is now correct but its UX is thin (new).** The workspace
shows the reconciliation trail and offers "Read-only reconcile", but releasing a
blocked write still requires the CLI, by explicit governance design
(`test_security_contract` forbids a public manual-reconcile route). For a demo
this is defensible — it *shows* that recovery is deliberate — but a judge may read
it as incomplete. *Mitigation:* narrate it as a control, and show the CLI.

## Correctness

**R7 — Migration `20261108_0010` is conditional (new).** It inspects the live
schema and only adds/drops what differs, because migration `0007` builds tables
from current metadata. Verified upgrade → downgrade → upgrade on SQLite. It has
**not** run against PostgreSQL, where `DROP COLUMN` semantics and transactional
DDL differ. *Mitigation:* run `alembic upgrade head` against a Postgres instance
before deploying; the doctor already gates on head revision.

**R8 — Downgrade cannot restore reconciliation history (new).** The obsolete
columns never held rows (the module crashed before writing), so nothing is lost in
practice, but the downgrade is not data-preserving by construction. Documented in
the migration.

**R9 — Provider auto-selection could mask misconfiguration (new).** With
`CASEGRAPH_AI_PROVIDER=auto` and no key outside production, analysis silently uses
the reference reasoner. Production still hard-fails. The visible cost is an
operator wondering why answers are rigid. *Mitigation:* the provider name is
recorded per analysis and printed by `scripts/demo_seed.py`.

## Operational

**R10 — Test isolation writes into `.data/` (new).** `pytest-<pid>.db` files
accumulate in the gitignored `.data/` directory (one per run). They are never
deleted. Harmless, unbounded. *Mitigation:* a session-scoped finalizer could unlink
them; not worth the risk of deleting a database a developer is inspecting.

**R11 — Frontend has no runtime error boundary (pre-existing).** A malformed
payload from a future endpoint blanks the app. Cheap to add, not added because it
is invisible in a demo and I preferred spending the cycle on the product surface.

**R12 — Rate limiting is in-memory by default (pre-existing, documented).**
Correct for local use, refused in production by `SecurityConfig.validate()`.

## Explicitly accepted

- The simulated transport is refused in production at two independent points
  (`main.py` startup, `SecurityConfig.validate()`), so the worst-case failure —
  a production process believing it moved money — is blocked.
- `UNKNOWN_OUTCOME` remains sticky by design. There is no timer, no background
  auto-release, and no operator shortcut without a dashboard assertion. This is
  intentional and was made *stronger* this cycle (service-level enforcement).
