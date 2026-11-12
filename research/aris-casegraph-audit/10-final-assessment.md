# Final product assessment

## Scorecard against the official criteria

Scores are mine, on the same five equally weighted criteria the judges use.
"Before" means the state I found; "after" is this cycle's result. I have been
deliberately harsh, because a scorecard that flatters the work is useless.

| Criterion | Before | After | Reasoning |
| --- | --- | --- | --- |
| **Technological Implementation** | 3 | 4 | The architecture is genuinely non-trivial and now *works*: approval and execution are reachable over HTTP, reconciliation executes, the simulated provider exercises the same validation and safety paths. It stays at 4 rather than 5 because the live PayPal and live model paths are still unproven. |
| **Design** | 2 | 4 | From one 72-line component with JSON dumps in `<pre>` to a componentised workspace with a real provenance canvas, human-readable safety findings with node drill-down, and a typed action composer. Not 5: no browser QA was possible, and some surfaces (reconciliation release) remain CLI-only by governance choice. |
| **Potential Impact** | 4 | 4 | Unchanged and strong: PayPal-native dispute operations with an auditable trail is a real, specific problem for a real audience, and the research supports where the value sits. Still no measured user benefit — the repository correctly refuses to claim one. |
| **Innovation** | 3 | 4 | The composition was novel and invisible; it is now visible and demonstrable. The blocked-by-safety moment is a distinctive demo. Not 5 because the underlying ideas (provenance graphs, human-in-the-loop approval) are individually well known. |
| **Presentation** | 1 | 3 | From "cannot be run without credentials" to "two commands and no credentials". Missing: the video, the repo URL, and any browser-verified visuals. Presentation is now *possible*; it is not yet *done*. |

## The honest bottom line

The product improved materially, and the improvement is concentrated where the
judging criteria and the rules actually bite: a working end-to-end path, a
demonstrable safety gate, and a UI that expresses the thesis instead of hiding it.
Three defects that would each have been fatal in a live demo are closed, with
regression tests at the level a user actually touches (HTTP, database,
reconciliation) rather than at the level that made them invisible (source text).

It is **not** submission-complete. Four items are outside what I could do here and
each is blocking on its own: a licence file, a real PayPal sandbox pass, a demo
video, and repository/video URLs. I did not invent any of them.

## Adversarial self-review (disclosed: not independent)

No independent cross-model reviewer was configured for this session (the Codex
review path is explicitly out of scope for this mission, and no API-backed
reviewer was available). What follows is my own attempt to argue against my work.
It should be read as self-criticism, **not** as external validation.

1. **"You fixed bugs that a real user would have hit, so how good was the original
   really?"** The bugs are real and severe — but the surrounding architecture is
   sound and mostly unchanged. This is not a rescue of a broken design; it is a
   design whose two most user-visible code paths were never wired. The tests even
   asserted on source text, which is why nobody noticed. The strongest criticism
   is of the *verification culture*, not the architecture, and that is now
   different: the three new suites run through ASGI and the database.
2. **"The simulator is a demo crutch and could mislead."** Fair. Mitigations are
   real (production refusal at two points, `simulated: true` on every payload, a
   UI badge, a provider name recorded per analysis, README ordering) but the risk
   is a judge assuming the demo *is* the PayPal integration. The only honest fix
   is to also show a real sandbox pass — which I could not do.
3. **"The reference reasoner is a rules engine wearing an AI costume."** Also fair.
   It exists so the pipeline is observable with no key, and it is labelled
   everywhere. If the demo never shows the OpenAI provider, the product looks like
   a rules engine — which would undercut the "AI hackathon" premise. This is the
   single largest presentation risk.
4. **"Design improvements are unverified without a screenshot."** True. Build and
   typecheck prove it compiles and that the contract holds; they prove nothing
   about whether the graph canvas is legible at seven columns or whether the
   composer is pleasant at 1024 px. I chose to say so rather than imply otherwise.
5. **"You added a demo transport to a financial product — isn't that how accidents
   happen?"** The failure mode would be a production process that believes it moved
   money. That path is blocked twice, independently, and the refusal is covered by
   configuration validation. I also did not touch the live transport, the
   idempotency model, the safety policy, or the approval hash chain — the parts
   where a mistake would be unforgivable.
6. **"Did you improve the product or just the packaging?"** Both, but the ratio
   matters: two of the five selected items (#1, #2) are pure correctness, two
   (#3, #5) are capability under the rules, one (#4) is design. The packaging work
   (docs, manifest, changelog) is the smallest part and was done for integrity.
7. **What I would have got wrong if I had not read the code.** I would have built
   a "graph visualization" for a graph that already existed but was rendered as
   lists — missing that the reason the graph tab looked empty of insight was the
   UI, while the reason the *product* was unusable was a FastAPI annotation.
   Reading the implementation first was the difference between a cosmetic cycle
   and a real one.

## What remains, in order of consequence

1. **Licence file** (blocking, owner decision).
2. **Real PayPal sandbox pass** (blocking for the core claim; unproven).
3. **Demo video + repo URL** (blocking submission fields).
4. **Browser QA pass** (~10 minutes, protects the video take).
5. **Real model pass** with `CASEGRAPH_AI_PROVIDER=openai` (protects the "AI" half
   of the pitch).
6. Server-side `explain` artifact, evidence retrieval over the provenance graph,
   `list_cases` projection (post-submission engineering).

## Files a reviewer should read first

- `backend/casegraph/validate.py` — the deterministic compiler that makes the
  product's central claim true.
- `backend/safety/service.py` — the policy that turns provenance into a decision.
- `backend/services/actions.py` — the approval/execution boundary.
- `frontend/src/components/GraphCanvas.tsx` and `SafetyFindings.tsx` — where the
  thesis becomes visible.
- `tests/test_http_journey.py` — the regression test that the product, not the
  library, works.
