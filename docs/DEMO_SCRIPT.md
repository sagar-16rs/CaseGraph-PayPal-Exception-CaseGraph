# Three-minute demonstration script

Target: **2:55**. The rules cap the video at three minutes and judges are not
required to watch beyond it, so the first 30 seconds must carry the claim.

Record against the **simulated** sandbox (`CASEGRAPH_PAYPAL_TRANSPORT=simulated`)
so the take is reproducible, and say so out loud. If a live sandbox pass exists by
recording time, show that instead and keep the same beats.

## Setup (before recording)

```bash
cp .env.example .env
export CASEGRAPH_PAYPAL_TRANSPORT=simulated
export CASEGRAPH_AI_PROVIDER=auto        # falls back to the reference reasoner without a key
python scripts/demo_seed.py --reset-simulation
uvicorn backend.main:app --port 8000 &
cd frontend && npm run dev
```

Open `http://localhost:5173/?view=overview` at 1512×982. Three seeded cases are in
the docket.

## Beat sheet

**0:00–0:12 — The problem.**
> "A PayPal dispute gives a merchant three things: a deadline, a pile of
> unstructured evidence, and an API that will move money. Today, deciding what to
> send is guesswork."
Show the docket: three cases, deadlines counting down.

**0:12–0:35 — What CaseGraph is.**
> "CaseGraph turns the dispute into an evidence dossier. PayPal stays the source of
> truth, the model only interprets, and a human authorises the exact response."
Case view (`?view=overview`). Point at the verdict bar, the labelled PayPal record,
and the event spine. Call out "payload source: simulated sandbox".

**0:35–1:05 — The graph.**
Switch to **Evidence graph**. Do not narrate every node.
> "Every assertion is typed and cited. Green is what PayPal says. Amber is what the
> parties claim — each one carries a verbatim excerpt and its evidence revision.
> Purple is the model's inference. This one is contradicted by the merchant's own
> statement, and the conflict is drawn, not hidden."
Hover → click the customer claim. The inspector opens the provenance.

**1:05–1:30 — Readiness, the actionable half.**
Point at the inspector.
> "This is the part operators actually act on: for this dispute reason, CaseGraph
> names the evidence PayPal expects and marks what is present, missing, unknown —
> and never as a probability of winning."
Note the negation handling if visible: evidence that says "no delivery proof" counts
against the requirement.

**1:30–2:00 — Safety blocks a bad action.**
Return to Case view and read the assessment line, then open **Response**.
> "The model may want to fight this case. The deterministic policy will not let it:
> high-risk actions supported by contradicted evidence are blocked, and only a
> low-risk clarification survives — which still needs a person."
Show the typed composer: change the note, expand "exact payload".

**Optional 10-second insertion — evidence upload** (only if the run is ahead of
schedule; it is the weakest beat and the easiest to fumble):
On **Evidence**, attach a PDF. Point at the hash that appears.
> "Every file is hashed, and that hash is bound into the approval — so the bytes
> that were approved are the bytes that get sent."

**2:00–2:35 — Human approval and one write.**
Click **Approve immutable payload**, show the approval hash appear, then
**Execute approved action**.
> "One approval, one write. Execution re-reads PayPal first and refuses if the live
> state differs from what was approved."
Show `EXECUTED` and the event spine entry.

**2:35–2:55 — Ambiguity and closing.**
> "If that write times out, CaseGraph does not retry it. The action stays in
> UNKNOWN_OUTCOME until reconciliation can prove what happened — and only an
> operator who checked the PayPal dashboard can release it."
Optional: show `CASEGRAPH_SIMULATED_FAULT=timeout` in a prepared second window.
Close on the masthead line: **AI interprets · PayPal is authoritative · humans authorize.**

## Rules for the recording

- Say "simulated sandbox" the first time it appears. Do not let a judge infer a
  live integration from a simulated run.
- Do not claim a win rate, a time saving, or a measured user benefit. None has been
  measured.
- No third-party trademarks beyond naming PayPal as the platform, and no music.
- Upload to YouTube as public, under three minutes, and put the link in
  `data/submission/submission.json`.

## Verified against the running product

Every UI state named above exists and was exercised over the DevTools protocol in
this cycle: graph render, node selection, composer enable/disable,
approve → execute, error notice, upload picker, hover, keyboard activation, and the
900 px layout. Durations in the beat sheet are targets; the app's own transitions are
150 ms, so no beat requires waiting on animation.

Two things the script deliberately never does: it never shows a raw internal
identifier as a label, and it never presents evidence coverage as a chance of
winning the dispute.
