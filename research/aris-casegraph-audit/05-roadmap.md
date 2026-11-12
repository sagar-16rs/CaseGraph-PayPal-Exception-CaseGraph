# Roadmap

## This cycle (complete)

| Order | Item | Status |
| --- | --- | --- |
| 1 | Approve/execute HTTP binding + ASGI regression test | Done |
| 2 | Reconciliation model/service/schema/enums/CLI/migration | Done |
| 3 | Manual reconciliation fails closed without dashboard confirmation | Done |
| 4 | Test-suite database isolation | Done |
| 5 | Simulated PayPal transport with production refusal | Done |
| 6 | Deterministic reference reasoner + provider provenance | Done |
| 7 | `scripts/demo_seed.py`, fault injection, README quick start | Done |
| 8 | Frontend rebuild (canvas, safety UX, typed composer) | Done |
| 9 | OIDC JWKS rotation refresh | Done |
| 10 | Integration-gate literal, protocol-lock portability, manifest tooling | Done |

## Cycle 2 (complete)

| Order | Item | Status |
| --- | --- | --- |
| 11 | Server-side deterministic `explain` artifact + workspace panel | Done |
| 12 | Constant-query `list_cases` projection | Done |
| 13 | Frontend error boundary | Done |
| 14 | Configurable PayPal multipart timeout | Done |
| 15 | Novelty re-check against agent-security literature; positioning corrected | Done |

## Before submission (owner actions, in priority order)

1. **Licence file.** The rules require an open-source licence visible in the
   repository "About" section. `submission_doctor.py` reports
   `open_source_license: false`. This is a blocking gate and an owner decision —
   MIT or Apache-2.0 for a project of this shape, but I did not choose for you.
2. **Real PayPal sandbox pass.** Sync a sandbox dispute, submit evidence, and
   confirm the post-write state transition. Nothing in this repository proves the
   live transport works.
3. **Real model pass.** `CASEGRAPH_AI_PROVIDER=openai` with a key; confirm the
   structured-output schema round-trip on `gpt-5.6` or whichever model is current.
4. **Browser pass.** Open the workspace at 1440px and 1024px, click through all
   five tabs, and check the graph canvas scroll and node selection. Build and
   typecheck are clean but no visual QA was possible here.
5. **Demo video (< 3 min)** on the simulated sandbox: seed → graph → safety
   `REVIEW` on the contradicted case → approve → execute → fault-injected
   `UNKNOWN_OUTCOME` → reconcile refusal → manual release.
6. **Repo and video URLs** in `data/submission/submission.json`; then
   `python scripts/submission_doctor.py --repo .` must report PASS.

## Next engineering cycle (ranked)

1. **Evidence retrieval over the provenance graph.** Activate when a case
   routinely exceeds the bundle budget: typed traversal from the recommended
   action's support nodes, default-deny, admitting only persisted relationships —
   the FinRCA-Bench result suggests this is the highest-yield investment at scale.
2. **Shared PayPal HTTP client** with connection pooling (a fresh
   `httpx.AsyncClient` per call today).
3. **`PayPal-Request-Id` experiment** in the sandbox: if the Disputes write
   endpoints honour it, ambiguity handling gets dramatically cheaper. Must be
   *proven*, not assumed.
4. **Observability for the safety decision.** Emit the policy verdict and finding
   codes as span attributes so blocked actions are queryable in production.
5. **Reconciliation release in-product.** Today the operator-only release is a
   CLI (`scripts/reconcile_action.py`) because a public route was deliberately
   refused. A properly gated ADMIN flow with a second confirmation would close the
   loop without weakening the control.

## Explicitly not on the roadmap

- Auto-submission of representment, win-rate prediction, multi-PSP adapters, and
  any RAG/chat surface over evidence. See
  [`04-ideas-ranked.md`](04-ideas-ranked.md) for the reasoning.
