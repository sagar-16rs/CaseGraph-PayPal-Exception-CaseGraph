# Product validation protocol

The validation framework compares normal dispute investigation with CaseGraph using a counterbalanced within-participant design.

Each complete participant performs five baseline tasks and five CaseGraph tasks. Matched scenario variants and workspace order are counterbalanced to reduce order, learning, and scenario effects. Gold labels are stored separately from participant-facing scenario data.

Primary evaluation dimensions include task correctness, unsafe action selection, source verification, contradiction/evidence-gap recognition, completion time, confidence, and workload/UX measures.

A safety regression cannot be averaged away by faster completion or higher subjective preference.

## Pilot mode

The bundled packet interface is intended only for testing instructions, study mechanics, timing, and scenario clarity. Pilot results must not be presented as evidence about the production CaseGraph interface.

## Live-product mode

For confirmatory testing, map each frozen synthetic scenario to a corresponding case in the real CaseGraph product. The mapping includes the expected scenario hash to prevent silent remapping after the protocol is frozen.

## Protocol freeze

Before confirmatory data collection:

```bash
python scripts/generate_validation_assignments.py --participants 10
python scripts/create_live_case_map.py
python scripts/freeze_validation_protocol.py --casegraph-map study_runs/live_casegraph_map.json
```

Once scored responses exist, the freeze command refuses to rewrite the protocol lock. Start a new run directory/version for any protocol change.
