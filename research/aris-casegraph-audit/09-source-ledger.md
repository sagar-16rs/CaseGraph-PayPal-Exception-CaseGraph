# Research source ledger

Every external source consulted in this cycle, what it supported, and how
strongly. "Verified" = I fetched and read the content. "Second-hand" = returned
through a search summary that I could not confirm by fetching the primary page.

## Tier 1 — official / primary

| # | Source | Verified | Used for |
| --- | --- | --- | --- |
| 1 | [PayPal AI Hackathon — overview](https://paypalaihackathon.devpost.com/) | Yes (full page text) | Deadline (2026-11-12 12:00 PST), "must meaningfully use both PayPal and AI", functional-demo requirement ("judges must be able to actually run or interact with a working build"), public repo + open-source licence in About, <3 min public YouTube video, five judging criteria and prizes, judging panel. |
| 2 | [PayPal AI Hackathon — official rules](https://paypalaihackathon.devpost.com/rules) | Yes (full page text) | Submission period Oct 1 – Nov 12 2026; project must be new or "significantly updated" after the period start; testing access obligations; repositories must contain all source and instructions; five equally weighted Stage-Two criteria; IP originality. |
| 3 | [PayPal Disputes v1 API reference](https://developer.paypal.com/api/customer-disputes/v1) | Yes (index) | Confirmed the eleven dispute operations implemented in `backend/paypal/disputes.py` exist with those paths/methods, including `provide-evidence`, `appeal`, `escalate`, `send-message`, `make-offer`, `accept-claim`, `acknowledge-return-item`, `provide-supporting-info`. |
| 4 | [Provide evidence — Disputes v1](https://developer.paypal.com/api/customer-disputes/v1/disputes-provide-evidence) | Yes | Evidence is `multipart/form-data`; merchants may provide evidence when the dispute is `WAITING_FOR_SELLER_RESPONSE`; evidence types include proof of delivery (tracking) and proof of refund (refund ID); requested evidence sources are `REQUESTED_FROM_SELLER` / `REQUESTED_FROM_BUYER`. Used to judge the evidence-payload model in `backend/actions/schemas.py`. |
| 5 | [Dispute API test values](https://developer.paypal.com/api/disputes/test-values) | Yes | Sandbox error-injection conventions (`ERRDIS0xx` paths) — informs the fault-injection design of the simulator, which deliberately borrows the idea of driving negative paths. |

## Tier 2 — research literature

| # | Source | Verified | Used for |
| --- | --- | --- | --- |
| 6 | FinRCA-Bench — *Separating Retrieval Failure from Reasoning Failure in Financial Reconciliation RCA* ([arXiv 2608.18534](https://arxiv.org/pdf/2608.18534), also [arcxiv mirror](https://arcxiv.org/abs/2608.18534)) | Yes (abstract + substantial body text) | Independent support for provenance-first design: with model/prompt fixed and only retrieval changed, macro required-record recall moved 0.83% → 77.70% and exact accuracy 2.05% → 72.44%; structural retrieval failures outnumbered reasoning failures 95 to 15; strict returned-evidence contract accuracy 5.72%; "a correct root-cause label is a weak proxy for an auditable one"; typed provenance graph retrieval as the strongest method. This is the single most relevant paper found and it validates both the typed-graph design and the roadmap item about retrieval. |

## Tier 3 — competitive landscape

| # | Source | Verified | Used for |
| --- | --- | --- | --- |
| 7 | [Best AI Agents for Chargeback Management (2026)](https://runtm.com/compare/best-ai-agents-chargebacks) | Yes (long comparison text) | Positioning, pricing models, and weaknesses of Chargeflow, Justt, Disputifier, Stripe Smart Disputes, Chargebacks911, Verifi/Ethoca, Kount. Source of the "win-rate claims relative to an unstated baseline" observation about Chargeflow and of Justt's 500+ data-point argument generation. |
| 8 | [Top 5 Chargeback Automation Platforms](https://wrist-pay.com/finance/fintech/top-5-chargeback-automation-platforms-for-effective-dispute-management) | Yes | Corroborates the feature set (pre-dispute alerts, reason-code-specific evidence packages, automated submission) and that merchants are the buyers. |
| 9 | [5 Best Chargeback Automation Platforms](https://finance-monthly.com/5-best-chargeback-automation-platforms-for-dispute-management) | Yes | Pricing-structure comparison and the "evidence must match the reason code" framing. |
| 10 | [AI for payment disputes: what to automate, what to fight, and what it costs](https://eesel.ai/blog/ai-for-payment-disputes) | Yes | The most detailed source: Stripe Smart Disputes' "submits just before the dispute times out if you do nothing", its 30% fee, PayPal's lack of an AI evidence builder, Chargeflow's QA-agent escalation design, and the VAMP/ratio economics. Used for the differentiation argument. |
| 11 | [Chargeflow — PayPal dispute automation](https://chargeflow.io/blog/paypal-dispute-chargeback-automation-saves-money-and-time) | Yes | Incumbent framing of PayPal dispute automation; vendor claims treated as marketing, not evidence. |
| 12 | [Disputifier — PayPal chargeback automation](https://disputifier.com/post/paypal-chargeback-automation-stop-disputes-from-turning-into-rolling-reserves) | Yes | PayPal-specific operational pain (rolling reserves, deadlines, inconsistent evidence). |
| 13 | [PayPal — the evolution of dispute management](https://paypal.com/us/brc/article/dispute-management-chargeback-prevention) | Second-hand (search summary) | PayPal's own stated direction: pre-dispute interception, CE 3.0 data, expected-value decisioning, VAMP monitoring. Treated as directional, not quoted as fact. |
| 14 | [PayPal — chargeback protection automation](https://paypal.com/us/brc/article/chargeback-protection-dispute-automation) | Second-hand | Confirms PayPal positions automation as a partner capability rather than a built-in Resolution Center feature. Used cautiously. |
| 15 | [Solidgate — PayPal chargeback representment guide](https://solidgate.com/blog/paypal-chargeback-representment-a-guide-to-winning-paypal-disputes) | Yes | PayPal response windows (≈10 days internal claim, 20–45 days external chargeback), evidence-format constraints (one PDF, ≤19 pages, <4 MB), and dispute reason taxonomy. Cross-checked against the API reference for the reason codes. |
| 16 | [Merchant Risk Council — Chargebacks Are Beautiful](https://merchantriskcouncil.org/learning/resource-center/member-news/blog/2026/payrails-chargebacks-are-beautiful) | Yes | Practitioner view that the real pain is operational friction across PSPs and that AI is useful for drafting, clustering and fight-or-concede — with the explicit caveat that policy judgement stays human. Directly supports the human-approval design. |

## Search tooling note

X/Twitter search was attempted for merchant sentiment. The X backend was
unreachable and the tool returned a second-hand web-search answer instead. **No X
post is cited as evidence anywhere in this audit**, and no claim rests on it.

## What is *not* sourced

Everything in [`01-codebase-audit.md`](01-codebase-audit.md) and
[`07-implementation-changelog.md`](07-implementation-changelog.md) is derived from
this repository, not from a source above. Where I assert an external fact
(deadline, judging criteria, API shape), the source is listed here. Where I assert
a product judgement (novelty, market position), it is labelled as judgement in
[`04-ideas-ranked.md`](04-ideas-ranked.md).
