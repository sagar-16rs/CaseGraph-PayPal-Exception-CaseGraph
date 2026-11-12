# Public repository checklist

Prepared, **not executed** — publishing is an external action and requires the
owner's authorization. This is the exact sequence to follow.

## 1. Licence — recommendation only

The hackathon rules require "an open source license file … detectable and visible at
the top of the repository page (in the About section)". **No license file has been
created**: choosing a license is the owner's legal decision.

**Recommendation: MIT.**

| Option | Fits CaseGraph because | Cost |
| --- | --- | --- |
| **MIT** (recommended) | Shortest, universally understood, frictionless for judges who want to run the code, and permissive enough for a demo project | No patent grant |
| Apache-2.0 | Adds an explicit patent grant and trademark clause — worth it if any part may be commercialised | Longer, more to read |
| AGPL-3.0 | Would prevent a hosted competitor from closing the source | Frequently avoided by companies, may deter judges |

Do not use "All rights reserved", an unlicensed repository, or a license incompatible
with the bundled dependencies (PyJWT, FastAPI, SQLAlchemy, React, Vite — all
permissive; MIT is compatible).

To apply MIT: create `LICENSE` with the standard MIT text, set the copyright line,
put `MIT` in the GitHub "About → License" field, and add a `## License` line to the
README naming it.

## 2. Secrets before pushing

```bash
python scripts/release_scan.py          # must report PASS
python scripts/submission_doctor.py --repo .
```

- `.env` is gitignored and **must not** be committed. The local scan currently fails
  precisely because a developer `.env` exists in the working tree; that is the guard
  working, not a defect.
- Confirm `.gitignore` still covers `.env`, `.env.*` (except `.example`), `.data/`,
  `frontend/node_modules/`, `frontend/dist/`, `*.tsbuildinfo`, `research/.tmp/`,
  `research/.baseline/`.
- No PayPal credentials, model keys, webhook ids, evidence files, or study
  participant data may be present in the published tree or in git history.
- If a secret was ever committed, rotate it — deleting the file is not enough.

## 3. Repository setup

1. Create the public repo, push `main`.
2. Add the license file (step 1) and confirm GitHub detects it in About.
3. Set the repository description to the product tagline.
4. Enable Issues (judges sometimes file questions) and keep Actions on — the
   workflow in `.github/workflows/ci.yml` runs the deterministic suite.
5. Do **not** enable any deployment that would hold real credentials.

## 4. Setup instructions a judge can follow

The README quick start is the contract with the judges. It must work from a clean
clone with **no credentials**:

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt -r requirements-production.txt
cp .env.example .env
export CASEGRAPH_PAYPAL_TRANSPORT=simulated
python scripts/demo_seed.py --reset-simulation
uvicorn backend.main:app --port 8000
cd frontend && npm install && npm run dev
```

Verify from a *fresh* clone before publishing, including `npm install` (not a warm
`node_modules`). If a judge cannot reach a running workspace in five minutes, the
submission fails the "functional demo" requirement regardless of code quality.

## 5. Before announcing

- [ ] `pytest` green from a clean checkout
- [ ] `npm run build` green from a clean `npm install`
- [ ] `python scripts/release_scan.py` PASS
- [ ] LICENSE present and detected
- [ ] README quick start tested verbatim
- [ ] Demo video public, under three minutes, link in the submission form
- [ ] `data/submission/submission.json` has real `repo_url`, `youtube_video_url`,
      `open_source_license`, `contact`, `team`
- [ ] `python scripts/submission_doctor.py --repo .` returns PASS
- [ ] No claim in the README, video, or submission text asserts a live PayPal
      sandbox pass or measured user benefit that has not happened
