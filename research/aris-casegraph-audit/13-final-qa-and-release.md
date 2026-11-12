# Final QA and release readiness

Phase: product-quality and submission-readiness. No new features were added.

## 1. Visual QA — executed, with interaction

Tooling: **headless Chrome 157 driven over the DevTools Protocol** (WebSocket via
Node 24), not static screenshots. The harness (`research/.tmp/qa/qa.mjs`, gitignored)
navigates, clicks, types into React-controlled inputs, dispatches Tab keys,
overrides the viewport, captures screenshots, listens for console errors and
measures computed contrast ratios.

**Result: 22 / 22 assertions pass, 0 page errors.** The single console entry is the
browser logging the intentional 404 from the invalid-dispute-id test.

Covered: graph render · node click → provenance inspector → back to posture ·
composer disabled while the payload is incomplete · approve → execute end to end ·
invalid dispute id → error notice · Tab traversal with visible focus rings ·
900 px layout with no horizontal overflow · contrast on eight text roles.

### Defects found and fixed

| # | Defect | Evidence | Fix |
| --- | --- | --- | --- |
| V1 | Three text roles failed AA contrast: `--ink-3` on `--surface` measured **4.11:1** | measured via `getComputedStyle` + WCAG formula | `--ink-3` `#7d7d6d` → `#6b6b5e`; re-measured **5.31:1** (4.6:1 on paper) |
| V2 | Masthead overflowed its 46 px row at 900 px — wordmark, stamp, case count and tagline all wrapped | 900 px screenshot | `nowrap` on masthead items, `overflow: hidden`, tagline hidden below 1180 px |
| V3 | Invalid dispute id returned **HTTP 500** | console: "500 Internal Server Error"; QA assertion detail | `sync` now maps PayPal 4xx → 404 and transport/5xx → 502, with a message that says state was not changed |

### Open visual items

- Interactive states beyond the ones exercised (hover on every surface, the 150 ms
  view transition, file-upload picker) were not automated.
- Contrast was measured on eight representative roles, not every token pair.
  `--claim` and `--caution` on `--paper` should be measured before any published
  accessibility claim.

## 2. Evidence intelligence — validated

Ten new tests (`tests/test_readiness.py`) plus four in `tests/test_explanations.py`.

**Reason-code provenance, stated honestly.** The eight reason codes follow PayPal's
dispute-reason taxonomy. The **per-reason requirement list is CaseGraph's own
judgement** — PayPal publishes no normative per-reason evidence checklist. The
module docstring now says so, where it previously implied a PayPal rule.

### Defects found and fixed

| # | Defect | Evidence | Fix |
| --- | --- | --- | --- |
| E1 | **Negated evidence counted as present.** "No delivery proof was provided" satisfied the delivery requirement | new test | negation-aware matching: a signal preceded by a negator in the same clause counts *against* the requirement |
| E2 | **"IP address" satisfied "delivery to the buyer."** A false positive that would tell an operator a delivery requirement was met by device data | test `test_coverage_counts_only_present_critical_requirements` failed | delivery signals tightened to `deliver|shipment|shipped|courier|tracking number|address on file|proof of delivery` |
| E3 | Coverage could read as truth when the graph recorded a contradiction | design review | fourth status `contradicted`: text supports the requirement but the graph knows a conflict; counted as unsatisfied, surfaced in the summary |
| E4 | Explanation prose embedded `PROVIDE_SUPPORTING_INFO` mid-sentence | screenshot | next-step copy made action-agnostic |

### Honesty boundary, now enforced by a test

`test_readiness_is_never_presented_as_a_win_probability` serialises the entire
readiness payload and fails if it contains *probability*, *win rate*, *likelihood*,
*chance of winning* or *predict*. The output is labelled `basis: deterministic
keyword coverage …`. Coverage is coverage, not a forecast.

### Consistency across surfaces

`test_explanation_reports_dispute_readiness_for_the_reason_code` and the
determinism test verify that the exported explanation carries the same readiness the
inspector renders, from the same persisted rows. The readiness service reads the
graph's `MISSING_EVIDENCE` nodes and the safety layer reads the graph independently;
both are derived from one graph revision, so a contradiction cannot be invisible to
one and blocking in the other.

## 3. PayPal integration — **not executed**

No sandbox credentials exist in this environment (`PAYPAL_CLIENT_ID`,
`PAYPAL_CLIENT_SECRET`, `PAYPAL_WEBHOOK_ID` all unset). The live lifecycle — dispute
retrieval, allowed responses, evidence submission, webhooks, reconciliation — has
**not** been run and is not claimed.

What was verified instead:

- Endpoint surface matches the official Disputes v1 reference for all eleven
  operations used.
- `tests/test_paypal_live_gate.py` proves the guards: the live path refuses to run
  without credentials, and the simulated transport is a **production configuration
  error**.
- `scripts/integration_doctor.py` passes on the development profile.
- The simulated transport exercises the same service, validation, safety and
  approval code (proven by `tests/test_demo_simulation.py`, including an injected
  `UNKNOWN_OUTCOME` and its release).

Procedure and evidence requirements for the real run:
[`docs/PAYPAL_SANDBOX_RUNBOOK.md`](../docs/PAYPAL_SANDBOX_RUNBOOK.md).

## 4. Release readiness

| Gate | Status | Detail |
| --- | --- | --- |
| Test suite | **PASS** | 162 passed, 1 skipped (credential-gated) |
| Python compile | PASS | `compileall` clean |
| Frontend typecheck | PASS | `tsc --noEmit` exit 0 |
| Production build | PASS | 281 kB JS / 86 kB gzip, 16 kB CSS |
| Alembic migration chain | PASS | upgrade → downgrade → upgrade; head `20261108_0010` |
| Repository doctor | PASS on migrated DB | fails on an un-migrated dev DB, which is the intended signal |
| Integration doctor | PASS | development profile |
| Manifest | PASS | 243 files, `--check` clean |
| Secret scan | **BLOCKED locally** | the developer's `.env` exists; the public-release pipeline builds a sanitized archive. No secret-like content found in tracked files |
| **Open-source licence** | **MISSING** | blocking rule requirement; owner decision |
| Repository URL | **MISSING** | owner action |
| Demo video | **MISSING** | script written: [`docs/DEMO_SCRIPT.md`](../docs/DEMO_SCRIPT.md) |
| Demo mode | PASS | `functional_demo_mode: source` — runnable with no credentials |

## Prioritized defect list

**Fixed this phase (all with tests or measured evidence):** V1 contrast, V2 masthead
overflow, V3 500-on-bad-id, E1 negation, E2 IP-address false positive, E3
contradicted coverage, E4 prose enum.

**Open, in consequence order:**

1. **No live PayPal sandbox pass** — the product's central integration claim is
   unproven. Runbook ready; needs credentials.
2. **No licence file** — automatic rule failure; owner decision.
3. **No demo video or repository URL** — submission fields; script ready.
4. **No live model pass** — the OpenAI provider path is unchanged and unexercised
   this cycle; only the deterministic reference reasoner has run.
5. **Interactive QA coverage is partial** — hover/transition/upload-picker states
   and the full token set were not automated.
6. **`list_cases` still returns full case details** — correct and now batched, but a
   dedicated summary projection would be smaller on the wire.
7. **Single-process SQLite demo** — the durable worker and per-dispute locking are
   exercised in tests but not under PostgreSQL in this environment.

Nothing on this list was hidden; nothing above is claimed as complete that is not.
