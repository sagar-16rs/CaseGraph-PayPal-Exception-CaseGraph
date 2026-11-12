# Design direction — "the dossier"

Status: **decided**, supersedes the card-dashboard layout from cycle 1.

## Evidence this is based on

I rendered the current workspace in headless Chrome before deciding anything (see
`research/.tmp/shots/current-overview.png` during the session). What it actually
looks like is a generic admin dashboard:

- a raw key/value dump titled "Authoritative PayPal state" exposing internal fact
  names (`PAYPAL DISPUTE LIFECYCLE STAGE`) and a JSON array printed as literal text
  (`["PROVIDE_SUPPORTING_INFO","SEND_MESSAGE"]`);
- an ISO timestamp shown raw (`2026-11-22T00:00:00Z`) where a human needs a
  deadline;
- rounded cards with soft shadows on cool grey — the default SaaS surface;
- every label at 12–13 px, so nothing leads;
- roughly 40% of the viewport empty below the content.

That is a *presentation* failure of a product whose entire thesis is provenance.

## References studied

| Source | What it contributes |
| --- | --- |
| [Palantir Gotham](https://bdemerson.com/article/palantir-gotham) | The **dossier** as the unit of work: objects, timelines and graphs are *pieces inserted into one canvas*, not tabs in an app. Analysis and presentation are different visual modes. |
| [Sayari Graph](https://sayari.com/platform/graph) | **Every relationship is source-cited to the originating filing.** "Source-linked evidence packages" are the product, not a feature. |
| [Bloomberg design language](https://raw.githubusercontent.com/ndroussi/design-md-for-ai/main/design-md/bloomberg/DESIGN.md) | "Useful density": high contrast, editorial hierarchy, mono for data, one signature accent. Explicit warning: *do not soften into generic fintech minimalism.* |
| [Hoefler&Co, "Fonts for Complex Data"](https://typography.com/blog/fonts-for-complex-data) | Tabular figures for money; a deliberate size/colour split between **data** and **annotation**; and a "verifiable reference for the source of your data" as a typographic requirement. |

## The identity

**CaseGraph is a dossier under examination.** Warm paper, ink, hairline rules,
and a single signal colour. It should read like a forensic case file that happens
to be interactive — not like a metrics dashboard.

Deliberately rejected: dark-mode terminal cosplay (a disputes workspace is read in
daylight, printed, and attached to a file), neon accents, glassmorphism, gradient
heroes, decorative stat tiles, and chat-first layouts.

## Design tokens

### Colour

| Token | Value | Role |
| --- | --- | --- |
| `--paper` | `#f6f2e9` | Application ground — warm, not clinical |
| `--surface` | `#fffdf8` | Dossier sheet |
| `--ink` | `#1a1a14` | Primary text |
| `--ink-2` | `#4a4a3f` | Secondary |
| `--ink-3` | `#7a7a6b` | Annotation |
| `--rule` | `#ddd6c6` | Hairline rules — replaces shadows |
| `--rule-strong` | `#c3baa6` | Section breaks |
| `--authority` | `#1f3550` | PayPal facts only. Cold navy against warm paper: authority reads as a different *material* |
| `--claim` | `#7a4a12` | Human statements |
| `--inference` | `#4a3a6b` | Model inference |
| `--risk` | `#8c2f22` | Blocked / contradiction |
| `--caution` | `#8a6414` | Review / gaps |
| `--clear` | `#2c5c45` | Pass / executed |

### Type

| Role | Stack | Use |
| --- | --- | --- |
| Document | `Palatino Linotype, Georgia, Constantia, serif` | Case identity, section titles, node statements, narrative |
| Interface | `Segoe UI, system-ui, sans-serif` | Controls, labels, tables |
| Record | `Cascadia Mono, Consolas, monospace` | IDs, hashes, revision markers |

Money and dates use **tabular figures**. Micro-labels (taxonomy only) are 10 px,
uppercase, letter-spaced `0.12em`. Body text is 13.5 px at 1.5; the old build ran
everything at 12–13 px with no scale, which is why nothing led.

Radii drop to 2–3 px. Rules replace shadows. No card-in-card.

## Layout

```
┌──────────────────────────────────────────────────────────────────────────┐
│ CaseGraph · PayPal dispute dossier          [SIMULATED]   deadline: 3d   │
├────────────┬───────────────────────────────────────────┬─────────────────┤
│ DOCKET     │ CASE HEADER                               │ INSPECTOR       │
│            │  PP-D-DEMO-1001  ·  €310  ·  UNDER_REVIEW │                 │
│ ● 1003 3d  │  ── verdict bar: REVIEW · SEND_MESSAGE ──  │ selected node / │
│   1002 6d  │                                           │ provenance, or  │
│   1001 9d  │  CANVAS (graph | evidence | reasoning)    │ readiness, or   │
│            │                                           │ action composer │
│            │  ── event spine (timeline) ──              │                 │
└────────────┴───────────────────────────────────────────┴─────────────────┘
```

Three panes, all persistent. The graph is the **default canvas**, not a tab users
must find. Selecting a node loads the inspector with its provenance path; the
verdict bar is always visible so the decision state is never hidden behind
navigation.

## Data presentation rules

1. **Never print an internal identifier as a label.** `PAYPAL_DISPUTE_REASON` is
   data; "Reason" is the label.
2. **Never print a JSON array as text.** Available actions are chips; amounts are
   formatted with currency; dates are relative ("due in 9 days") with the absolute
   value on hover.
3. **Every claim shows its citation inline.** A claim without a visible source
   reference is a bug in the interface.
4. **Gaps are content, not alerts.** Missing evidence is rendered as a named
   requirement in the inspector, because that is the actionable part of an
   investigation.
5. **One signal colour per state**, used on a rule or a 2 px edge — never as a
   filled card with white text.

## Motion

150 ms ease-out on panel content, 200 ms on inspector swap. No bounce, no pulse,
no skeleton shimmer loops. State changes are announced by rule colour, not glow.

## Accessibility

Full keyboard tab order; `aria-current` on the active docket entry; contrast ratios
≥ 4.5:1 for body text (ink on paper is ~13:1); focus rings 2 px `--authority`;
graph nodes are `<button>` elements with `aria-pressed`; the colour system never
carries meaning alone — every state also has a text label.

## Result

Implemented and verified in headless Chrome (Chrome 157, `--headless
--screenshot`), not merely described. Captures live in `figures/`:

| Capture | What it shows |
| --- | --- |
| [`figures/ui-overview.png`](figures/ui-overview.png) | Case view: labelled PayPal record, verdict bar, event spine |
| [`figures/ui-graph.png`](figures/ui-graph.png) | Provenance canvas: facts → claims → inference → action, with the inspector showing readiness |
| [`figures/ui-ai.png`](figures/ui-ai.png) | Reasoning view: analysis provenance, confidence against policy, grounded citations |
| [`figures/ui-actions.png`](figures/ui-actions.png) | Response view: typed composer, latest approval, action history |
| [`figures/ui-1280.png`](figures/ui-1280.png) | The same case at 1280 px to confirm the three-pane layout survives |
| [`figures/architecture.svg`](figures/architecture.svg) | Architecture, generated from [`figures/specs/architecture.json`](figures/specs/architecture.json) with the ARIS `figure-spec` renderer |

### What the redesign fixed, concretely

| Before | After |
| --- | --- |
| `AUTHORITATIVE PAYPAL STATE` with `PAYPAL_DISPUTE_LIFECYCLE_STAGE` as a visible label | "PayPal record" table with "Lifecycle stage" |
| `["PROVIDE_SUPPORTING_INFO","SEND_MESSAGE"]` printed as text | Two labelled chips: "Provide information", "Send message" |
| `2026-11-22T00:00:00Z` | "22 Nov 2026 · 14d left" |
| `UNDER_REVIEW` rendered as a warning colour | Treated as normal PayPal state |
| Seven stacked lists behind a "graph" tab | Layered provenance canvas as a first-class view, with node selection driving the inspector |
| Readiness absent | Named requirements per dispute reason, with coverage meter |
| No deadline awareness anywhere | Deadline in the docket, the case header and the verdict bar |

### Honest limits

- The visual QA loop used static screenshots of the real application against real
  seeded data. Interactive states (hover, focus rings, the typed composer's
  validation, the 150 ms view transition) are implemented but were not exercised
  by an automated interaction test — there is no Playwright/Puppeteer in the
  repository, and adding one was out of scope for this cycle.
- Colour contrast was reasoned from the token values, not measured with an audit
  tool. The primary pair (ink `#1a1a14` on paper `#f6f2e9`) is far above the AA
  threshold; the accent colours on paper should be re-measured before any
  accessibility claim is published.

