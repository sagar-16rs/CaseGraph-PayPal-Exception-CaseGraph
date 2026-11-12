# Codebase cleanup and stabilisation

Date 2026-11-08 · Version `1.0.0-rc2` · Executor: DeepSeek V4.1 Flash (no Codex)

Scope: cleanup, defect correction and handoff. No new features, no redesign.

---

## 1. Baseline (measured independently, not copied)

| Check | Baseline result |
| --- | --- |
| Backend suite | **206 passed, 2 skipped** |
| Skips | `test_live_sandbox_validation_requires_credentials` (creds configured), `test_production_requires_verified_webhooks` (dev profile) |
| Typecheck / build | `tsc --noEmit` exit 0; `vite build` 281.33 kB |
| Python compile | exit 0 |
| Migrations | head `20261108_0010`, doctor PASS on an isolated DB |
| User database | `.data/casegraph.db` 225 280 bytes, mtime 27-10-2026 — verified before and after |
| Git | no repository; the local baseline copy under `research/.baseline/` is the rollback net |

---

## 2. Problems found

### P1 — Webhook signature verification is **disabled** in the normal startup path (reported, not changed)

The previous audit was internally inconsistent, and the discrepancy was real. Resolved
by measuring rather than reading:

```
python -c "from backend.config import Settings; s=Settings(); print(s.paypal_webhook_verify, bool(s.paypal_webhook_id))"
→ False True
```

Since `.env` is now loaded at import, the effective configuration is
`PAYPAL_WEBHOOK_VERIFY=false` **with** a Webhook ID present. Therefore:

- The rejection test in the previous audit passed because verification was forced on
  for that run (`PAYPAL_WEBHOOK_VERIFY=true` as a process override), not because the
  owner's configuration enables it.
- In the current startup path, an unsigned request is **accepted**. Production is
  protected by the startup gate (`backend/main.py` refuses to boot with
  `paypal_webhook_verify` false), so this is a development-profile exposure only.

**Not changed.** Editing `.env` is prohibited by the task, and flipping the default in
code would weaken a deliberate per-environment switch. Recorded as owner action 1 in
[`docs/REMAINING_WORK.md`](../../docs/REMAINING_WORK.md).

### P2 — A credential-gated guard was never actually tested

`test_live_sandbox_validation_requires_credentials` skipped whenever credentials were
present — i.e. it never ran in the only environment that has them. The guard itself is
real and worth proving.

**Fix:** build the probe with `dataclasses.replace(Settings(), paypal_client_id="",
paypal_client_secret="")` so the guard is exercised regardless of local configuration.

### P3 — A test asserted a premise that does not exist at its layer

`test_production_requires_verified_webhooks` skipped in development and, even in
production, could not assert anything: `SecurityConfig` does not read
`PAYPAL_WEBHOOK_VERIFY` — that gate lives in `backend/main.py`. The test ended with
`... or not errors`, which passes vacuously.

**Fix:** removed. The behaviour it pretended to cover is genuinely covered by
`test_production_forbids_the_simulated_transport` (same file, deterministic) and the
production startup gates in `tests/test_release_security.py`.

### P4 — Dead files

| File | Evidence | Action |
| --- | --- | --- |
| `frontend/src/components/SafetyFindings.tsx` | 0 references after the inspector absorbed its responsibility | deleted |
| `backend/ai/providers/base.py` | `ReasoningProvider` Protocol, 0 imports anywhere | deleted |

`backend/ai/providers/static.py` was inspected and **kept**: it is used by
`tests/action_fixtures.py`, `tests/test_integration_contract.py` and
`tests/test_release_security.py`.

---

## 3. What changed

| File | Change |
| --- | --- |
| `frontend/src/components/SafetyFindings.tsx` | deleted (dead) |
| `backend/ai/providers/base.py` | deleted (dead) |
| `tests/test_paypal_live_gate.py` | guard test now deterministic; vacuous webhook test removed |

No production behaviour changed. No dependency changed. No architecture changed.

### Deliberately **not** done

- **No broad dead-code sweep.** With the remaining budget I verified the specific
  candidates rather than running an automated unused-symbol pass whose false positives
  would have cost more than it saved. Residual risk: low-value unused helpers may
  remain; none are reachable from a route or entry point.
- **Duplicate finding explanations.** `FINDING_EXPLANATIONS` exists in
  `backend/services/explanations.py` and as a UI-voice map in
  `frontend/src/components/Inspector.tsx`. The server version is the audit artifact;
  the client version is tighter prose. Merging them is a real improvement but not a
  defect, so it was left rather than risking a UI regression late in the cycle.
- **No dependency removals.** Every declared package is imported: `python-dotenv`
  (now used by `config.load_environment`), `python-multipart` (upload route),
  `psycopg` (production URL), `PyJWT`, `redis`, OTel stack. Nothing was removable.

---

## 4. Verification

### Backend

| Check | Result |
| --- | --- |
| Full suite | **207 passed, 1 warning, 0 failed, 0 skipped** |
| Compile | `python -m compileall backend scripts tests migrations` → exit 0 |
| Migrations | fresh DB → `upgrade head` → doctor PASS at `20261108_0010` |
| Prior skips | both eliminated by fixing test logic, not by weakening assertions |

Test-count movement 206+2 skipped → 207+0: one previously-skipped guard now runs, one
vacuous test removed, and the deleted modules had no tests of their own.

### Frontend, in a real browser

Chrome 157 over the DevTools protocol, six viewports:

| Viewport | Horizontal overflow | Masthead | Nodes | Clipped controls | Inspector | Docket |
| --- | --- | --- | --- | --- | --- | --- |
| 1440×900 | 0 px | 46 px | 8 | 0 | visible | visible |
| 1280×800 | 0 px | 46 px | 8 | 0 | visible | visible |
| 1024×768 | 0 px | 46 px | 8 | 0 | visible | visible |
| 900×760 | 0 px | 46 px | 8 | 0 | visible | visible |
| 768×720 | 0 px | 46 px | 8 | 0 | visible | visible |
| 390×844 | 0 px | 46 px | 8 | 0 | visible | visible |

Interactions: switching cases changed the rendered case id; clicking a graph node
opened the provenance inspector. **0 console errors, 0 failed network requests.**

Earlier in the cycle (same build, `research/.tmp/qa/qa.mjs`): 23/23 assertions —
composer validation, approve → execute on the simulator, error notice, Tab traversal
with visible focus rings, contrast ≥ 4.5:1 on 11 text roles.

Screenshots: `research/aris-casegraph-audit/evidence/responsive-*.png`.

### Security and hygiene

| Check | Result |
| --- | --- |
| `scripts/release_scan.py` | `secret_like_findings: []`; exits non-zero **only** because the local `.env` is present |
| `.env` handling | never read into a report, never modified, never copied |
| User database | unchanged byte-for-byte (225 280 bytes, 27-10-2026) |
| Manifest | `MANIFEST.sha256` regenerated, 245 entries, `--check` clean |
| Upload validation / traversal | unchanged; covered by `tests/test_secure_uploads.py` |
| Approval / idempotency / reconciliation | unchanged; covered by the suite |

**The `.env` exclusion is not sanitisation.** The scan skips it; the file still
contains live sandbox credentials and must never be committed or archived.

---

## 5. Known limitations

1. **Webhook signature verification is off in the current `.env`** (P1) — a genuine
   gap for any run that receives real PayPal traffic.
2. **No genuine PayPal webhook event has been delivered**, so real event processing
   remains unverified. Registration, URL match, ID match, reachability and rejection
   were verified previously.
3. **No sandbox dispute exists** on the account; dispute-detail mapping against a real
   payload is unproven.
4. **No live LLM call has ever run.** `OPENAI_API_KEY` is empty; only the
   deterministic reference reasoner has produced a graph. The UI labels it as such.
5. **No automated dead-code analysis** (see §3).
6. **No screen-reader or automated accessibility audit**; contrast and keyboard order
   were measured, nothing more.

---

## 6. Release recommendation

**READY WITH EXPLICIT LIMITATIONS.**

The repository is stable, the suite is fully green with no skipped tests, the UI holds
across every required viewport with no overflow or clipped controls, no secret content
is present in tracked files, and the owner's data is untouched. What remains is
external: a live model key, a genuine webhook event, a sandbox dispute, and the four
owner decisions — all listed in [`docs/REMAINING_WORK.md`](../../docs/REMAINING_WORK.md).

It is not "READY" because three capability claims still cannot be made: real webhook
verification is disabled in the effective configuration, no genuine PayPal event has
been processed, and no live model has produced an analysis.
