# Research & competitive landscape

## The problem the market actually has

From merchant-side discussion and vendor comparisons, the recurring pain in
payment disputes is **not** "we cannot write a rebuttal". It is:

- **fragmentation** — every processor has its own portal, evidence format and
  deadline, so a four-PSP merchant runs four dispute teams;
- **deadline risk** — PayPal's windows are short (about 10 days for an internal
  claim, 20–45 days for an external chargeback) and a missed window loses;
- **inconsistent evidence** — the same reason code gets a different-quality
  response depending on who assembled it;
- **auditability** — when an automated system submits evidence, nobody can
  reconstruct *why* that particular claim was asserted.

The last point is where the market is weakest and where CaseGraph's architecture
is strongest. Automated representment vendors are priced on recovery percentage,
which makes volume the objective; the evidence they submit is a means, not a
product.

## Incumbent landscape

| Product | Positioning | Where it is exposed |
| --- | --- | --- |
| **Chargeflow** | Self-serve ecommerce auto-representment, 25% of recovered | Win-rate claims benchmarked against an unstated baseline; submission is automatic, human review is an escalation path rather than the normal path |
| **Justt** | Enterprise AI "Dynamic Arguments", performance-priced | Fight-or-concede optimisation, not explanation; pricing unpublished |
| **Disputifier** | Low-cost automated responses, 20% capped | Per-alert pricing unpublished; headline metrics without context |
| **Stripe Smart Disputes** | Stripe-only, "AI rules engine", 30% of won | Waives the counter fee and submits near the deadline if the merchant does nothing — the merchant's judgement is optional by design |
| **Chargebacks911** | Managed service + software | Human specialists, but the reasoning is institutional, not inspectable |
| **Kount (Equifax)** | Dispute analytics inside fraud prevention | Strong data, weak per-case evidence provenance |
| **PayPal itself** | Resolution Center + dispute API | **No AI evidence builder.** The documented integration guide is manual |

**Verified observation:** every one of these optimises for throughput or win rate.
None advertises an inspectable chain from "this claim" to "this exact evidence
revision" to "this approved payload". That is CaseGraph's opening, and it is a
better fit for a hackathon judged on *Design* and *Innovation* than another
auto-fight robot would be.

## Research signal

**FinRCA-Bench (arXiv 2608.18534, 2026)** — a deterministic synthetic benchmark of
2,250 accounts-payable-to-bank reconciliation cases separating retrieval failure
from reasoning failure. Findings that matter here:

- Holding the model, prompt, and generation settings fixed and changing *only*
  retrieval moved macro required-record recall from 0.83% to 77.70% and exact
  accuracy from 2.05% to 72.44%.
- Structural retrieval failures outnumbered reasoning failures 95 to 15.
- "A correct root-cause label is a weak proxy for an auditable one" — strict
  returned-evidence contract accuracy was only 5.72%.
- Their strongest retrieval method is *typed provenance graph retrieval*: a
  default-deny traversal restricted to persisted transaction relationships.

This is external, independent validation of CaseGraph's two central design
choices: **typed provenance as a first-class structure** and **deterministic
evidence contracts rather than trusting the model's answer**. It also points at
the roadmap: when evidence volume grows, retrieval over the provenance graph —
not stuffing the bundle — is the mechanism.

**Corroborating practice from the market:** Chargeflow's own documentation
describes a QA agent that re-checks a drafted case for up to three rounds and
escalates to a human rather than submitting a weak case. Stripe caps responses at
19 pages and allows one submission with no edits. Both support the same
conclusion CaseGraph encodes: consequential submissions need a gate that is not
the generator.

## What this means for the product

1. **Do not build an auto-fighter.** That market is crowded, price-compressed, and
   judged against incumbents' win-rate marketing. Competing there would be a
   weaker idea *and* a weaker demo.
2. **Sell the audit trail.** The differentiator is "show me why, and show me who
   approved it". That is a real merchant need (dispute operations are audited,
   and PayPal risk teams examine behaviour) and it is exactly what an LLM product
   normally cannot offer.
3. **Make the gate visible, not just present.** A safety policy that exists only in
   Python is invisible to a judge. Demonstrating a recommendation being *blocked*
   by a contradicted support node is the product's most convincing moment — and
   before this cycle the UI could not show it.
4. **Be runnable.** The rules allow "clear, complete setup and run instructions"
   in place of a hosted demo. Requiring PayPal sandbox credentials plus a model
   key made that condition false. That was the single highest-leverage gap.

## Sources

Full ledger with URLs and what each supported is in
[`09-source-ledger.md`](09-source-ledger.md). Community/X search was attempted and
returned second-hand results only (the X backend was unreachable), so no X-sourced
claim is used as evidence in this document.
