# Candidate improvements: ranking, challenge, selection

Every idea was scored 1–5 on: **Impact** (does it materially improve the
product?), **Judging** (does it move the five official criteria?), **Effort**
(inverse — 5 = cheap), **Risk** (inverse — 5 = safe). Scores are my judgement,
not measurements; the reasoning is stated so it can be challenged.

| # | Idea | Impact | Judging | Effort | Risk | Total | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Fix broken reconciliation | 5 | 4 | 4 | 5 | 18 | **Selected** |
| 2 | Fix broken approve/execute HTTP binding | 5 | 5 | 5 | 5 | 20 | **Selected** |
| 3 | Zero-credential simulated sandbox + demo seed | 5 | 5 | 3 | 4 | 17 | **Selected** |
| 4 | Rebuild frontend (graph canvas, safety UX, typed composer) | 5 | 5 | 2 | 4 | 16 | **Selected** |
| 5 | Deterministic reference reasoner (no-key path) | 4 | 4 | 4 | 4 | 16 | **Selected** |
| 6 | Test-suite DB isolation | 4 | 2 | 5 | 5 | 16 | **Selected** |
| 7 | OIDC JWKS rotation refresh | 3 | 1 | 4 | 4 | 12 | **Selected** |
| 8 | Server-side deterministic `explain` endpoint | 4 | 3 | 3 | 4 | 14 | Deferred |
| 9 | Evidence-grounded retrieval over the provenance graph | 5 | 3 | 1 | 2 | 11 | Rejected for this cycle |
| 10 | Claim extraction pipeline (LLM → candidate claim nodes) | 3 | 2 | 2 | 2 | 9 | Rejected |
| 11 | Win-rate / outcome prediction model | 2 | 2 | 1 | 1 | 6 | **Rejected** |
| 12 | Auto-submit representment ("agent mode") | 2 | 3 | 2 | 1 | 8 | **Rejected** |
| 13 | Multi-PSP support (Stripe/Adyen adapters) | 4 | 3 | 1 | 3 | 11 | Rejected for this cycle |
| 14 | Postgres-backed test matrix / dockerised e2e | 3 | 2 | 2 | 3 | 10 | Rejected |
| 15 | Add a vector database and RAG chat over evidence | 2 | 2 | 2 | 2 | 8 | **Rejected** |

## Why the selected five

**#2 and #1 first.** No amount of design work rescues a product whose main action
returns 422 and whose recovery path raises `TypeError`. These are also the
highest-scoring *judging* items because "Technological Implementation: does the
project reflect genuine effort and a working, non-trivial implementation?" cannot
be answered yes while the Approval button is broken. Verified before and after.

**#3 next.** The official rules require a functional demo that judges can run or
interact with. With credential requirements, that condition was false. A labelled
simulator makes the entire differentiator observable in two minutes and is also
the only way *I* could verify the end-to-end journey in this environment. It is
unusually high leverage: it changes the submission from "read the code" to "run
it and watch the safety policy block a bad action".

**#4 because the product's thesis is visual.** A provenance-first product that
renders provenance as seven bullet lists is arguing against itself. Design is one
of five equally weighted criteria, and it was the weakest surface in the repo.

**#5** is what lets #3 work with no model key, and it doubles as a non-LLM
baseline for the existing benchmark. It is explicitly labelled in the analysis
record (`model_provider="rules"`), so nobody can mistake it for a model result.

**#6** is cheap and prevents a data-loss foot-gun that would embarrass any judge
who ran the suite on their own checkout.

**#7** is a real bug that surfaced as a failing test; fixing it cost minutes.

## Rejected ideas and why

**#9 Retrieval over the provenance graph.** This is the most intellectually
interesting direction and the research points at it. Rejected because: with the
current evidence model (one bundle per case, typically a handful of revisions)
there is nothing to retrieve; building a retrieval layer with no corpus would be
infrastructure theatre. The mechanism becomes correct when evidence volume does —
see the roadmap.

**#10 LLM claim extraction.** Tempting, but the graph validator already requires
verbatim excerpts and exact speaker matches, which is the hard part. Adding a
second model call to pre-extract claims would duplicate a guarantee the compiler
already enforces, add latency and cost, and give a judge one more thing that can
fail on stage. Rejected as complexity without new capability.

**#11 Win-rate prediction.** Everyone in the market claims one, nobody can
validate it on a hackathon dataset, and inventing a number is exactly the kind of
fabrication this project's own claim ledger forbids. Rejected on integrity
grounds, not effort.

**#12 Auto-submit / agent mode.** Directly contradicts the product's stated
principle (humans authorize consequential actions) and the financial-safety
constraints of the mission. It would also make the demo indistinguishable from
incumbents. Rejected.

**#13 Multi-PSP.** Genuinely valuable commercially, but it multiplies integration
surface with zero ability to verify any of it in this environment. Rejected for
this cycle; the PayPal path is not yet proven against a live sandbox.

**#15 Vector DB / RAG chat.** "Add RAG" is the default AI-shaped answer and it
would make this product worse: a chat box over evidence invites exactly the
unsourced assertions the architecture exists to prevent. Rejected as
anti-differentiation.

## Novelty check (honest)

> **Superseded in part.** A dedicated literature sweep after this ranking found
> close prior art for the *mechanism* (Agent-Sentry, Janus, PROVISO). The verdict
> was downgraded and the positioning corrected in
> [`11-novelty-check.md`](11-novelty-check.md). The text below is the original
> assessment, kept for the record; the doc 11 verdict governs.

- **PayPal-native dispute workspace with provenance-typed reasoning and
  human-approved typed payloads:** I found no product doing this. Nearest
  neighbours are auto-representment services (evidence generation, no provenance,
  no per-action approval) and generic "AI analyst" dashboards (no financial
  action, no PayPal state machine). Originally assessed as novel in composition,
  now corrected: the composition of provenance gating, evidence-before-effect,
  and exact-action approval is published prior art in the agent-security
  literature. What remains CaseGraph's own is the byte-exact evidence contract,
  the risk/contradiction policy semantics, and the PayPal dispute lifecycle work.
- **The simulated sandbox for a payments product** is not novel as a technique
  (every PSP ships one) but is uncommon for a *dispute-ops* product and is what
  makes the demo possible. Not claimed as an innovation.
- **Deterministic safety over a graph** is well-precedented in form (policy
  engines, guardrails); the specific policy — grounding closure, missing-evidence
  blocking by risk class, contradiction-aware downgrade — is CaseGraph's own
  design and is implemented, not sketched.

No literature search can prove absence of prior art. This is a bounded,
documented search, not a patentability opinion.
