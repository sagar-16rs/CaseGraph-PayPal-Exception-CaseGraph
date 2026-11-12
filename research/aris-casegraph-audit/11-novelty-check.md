# Novelty check — corrected verdict

**Method under check:** CaseGraph's core claim — a model may *interpret* a
payment dispute, but a deterministic gate over typed provenance must authorize
any consequential PayPal action, with a human approving the exact payload and
ambiguous write outcomes preserved rather than retried.

## Tooling disclosure (read this before the verdict)

The ARIS `novelty-check` skill's Phase C requires an independent cross-model
reviewer via Codex MCP (`gpt-6-astra`, xhigh reasoning). **That step did not run:**

- the mission explicitly forbids Codex CLI and Codex MCP, and
- no alternative reviewer is configured in this environment
  (`OPENAI_API_KEY`, `LLM_CHAT_*`, `ANTHROPIC_API_KEY`, `MINIMAX_API_KEY` all
  unset — probed this session).

Phase B (multi-source literature search) *did* run, via ModSearch. The verdict
below is therefore **my own calibrated judgement over a real literature sweep,
not cross-model validation.** It must not be represented as an independent review.

## Core claims, each against its closest prior work

| # | Claim | Closest prior work | Delta that survives |
| --- | --- | --- | --- |
| 1 | A gate over a provenance graph decides whether a model-proposed action may execute | **Agent-Sentry** ([arXiv 2603.22868](https://arxiv.org/html/2603.22868)) learns a bound from prior executions and gates tool calls with a provenance-graph classifier + provenance-aware allowlist | **None at the mechanism level.** Agent-Sentry generalizes this for agent tool calls. CaseGraph's version is narrower and hand-authored rather than learned. |
| 2 | The decision record must be durable *before* the effect, and approval must bind the exact action | **Janus** ([arXiv 2609.38266](https://arxiv.org/html/2609.38266)) — "evidence before effect", signed hash-chained log, approval integrity, and a documented post-approval substitution attack where an approval keyed to one proposal was counted for another | **None at the mechanism level.** CaseGraph's `approval_hash` binding plus `_assert_local_chain_current` is a *weaker* instance of what Janus formalizes and attacks. This is important: CaseGraph should adopt Janus's framing, not claim it. |
| 3 | Provenance of an action's *arguments* determines whether it is authorized | **PROVISO** ([arXiv 2610.27115](https://arxiv.org/pdf/2610.27115.pdf)) — provenance-typed memory; "the amount may come from the invoice, but the recipient must come from the user" | CaseGraph does this narrowly (a refund amount must come from PayPal's own ceiling, not from the model or the merchant) and does not generalize it into a source-role model. Partial. |
| 4 | Guardrailed LLM generation of dispute evidence with human review | **HOPM** ([arXiv 2606.01472](https://arxiv.org/html/2606.01472)) — guardrailed evidence-document generation for dispute workflows with human reviewer feedback + automated validators | CaseGraph adds typed epistemic node classes enforced byte-exactly against provider facts and verbatim evidence excerpts, plus risk-class-differentiated policy. HOPM is about document quality, not authorization. **This is the real delta.** |
| 5 | Ambiguous non-idempotent financial writes stay blocked until reconciled | No direct paper found; adjacent to durable-execution literature (Janus cites transactional agent runtimes) | **Plausibly differentiated.** I found no paper treating `UNKNOWN_OUTCOME` as a first-class durable state with an explicit operator-only release path for *PayPal* dispute writes. This is engineering rather than research novelty. |

## Verdict

**PROCEED — as a product and engineering contribution.**
**PROCEED WITH CAUTION — as a research contribution.**

Applying the ARIS verdict limits: no named paper contains this *result*, so
ABANDON is not warranted; the territory is crowded and deltaed, which is PROCEED,
not a rejection. But the delta is thinner than my first audit implied, and I am
correcting that claim here rather than defending it.

What one sentence a reviewer could verify:

> CaseGraph applies the provenance-gated, evidence-before-effect pattern that
> Agent-Sentry, Janus, and PROVISO establish for agent tool calls, to PayPal
> dispute resolution, where the enforcement is a byte-exact evidence contract over
> an explicitly typed epistemic graph and the authorization boundary is a
> risk-classed deterministic policy plus an immutable human-approved payload.

## What this changes in the submission

1. **Do not claim architectural novelty** for "deterministic envelope + human
   approval of an exact payload". That is published prior art and a payments judge
   may well know it. Claiming it invites the one question you cannot survive.
2. **Claim the applied, implemented, domain-specific delta**: the typed
   epistemic contract (`validate_ai_output`), the risk/contradiction/missing-
   evidence policy semantics, and the PayPal-specific `UNKNOWN_OUTCOME` +
   reconciliation discipline.
3. **Cite the prior art in the README or submission description.** A hackathon
   judge who recognizes Janus will trust the project more, not less, if it
   positions itself correctly. This is also simply honest.
4. **Adopt Janus's threat framing where cheap.** Its documented
   post-approval-substitution failure is exactly the class CaseGraph's
   `approval_hash` + live-context revalidation is meant to prevent. Naming the
   attack and showing the defence is a stronger demo beat than claiming the idea.

## Adversarial counter-evidence worth keeping

**"Toward Auditable Fraud Detection"** ([arXiv 2607.19266](https://arxiv.org/abs/2607.19266v1))
reports that a bounded LLM investigation agent *underperformed* direct
thresholding of the classifier it relied on — 65.0% vs 71.7% — while producing "a
coherent written rationale in each case", and concludes that "a plausible
rationale from an investigation agent is not evidence of a better decision."

CaseGraph does not claim a better decision; it claims a *reviewable* and
*gated* one, and it abstains when grounding fails. But this paper is the strongest
argument against AI-in-the-dispute-loop and should be acknowledged rather than
ignored — it is precisely why the safety gate, the abstain path, and the claim
ledger refusing unmeasured benefit claims matter.

## Sources

- Agent-Sentry — <https://arxiv.org/html/2603.22868>
- Janus, evidence-before-effect — <https://arxiv.org/html/2609.38266v1>
- PROVISO — <https://arxiv.org/pdf/2610.27115.pdf>
- HOPM, guardrailed evidence documents — <https://arxiv.org/html/2606.01472>
- Auditable fraud detection (negative result on agentic investigation) —
  <https://arxiv.org/abs/2607.19266v1>
- Human-in-the-loop ≠ human control; segregation of duties —
  <https://forbes.com/councils/forbestechcouncil/2026/10/29/your-ai-agent-can-approve-its-own-payments-but-who-signs-for-it>
