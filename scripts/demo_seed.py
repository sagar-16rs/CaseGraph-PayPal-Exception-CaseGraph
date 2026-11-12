"""Seed a runnable CaseGraph demonstration without PayPal credentials.

What it does
------------
1. Ensures the schema exists (development only).
2. Reads the three demo disputes from the *simulated* PayPal sandbox and syncs
   them through the real `case_service` normalization path.
3. Stores reference support evidence through the real append-only intake service.
4. Runs the real AI reasoning + deterministic safety pipeline for each case.

Nothing is approved or executed here: approval of a consequential action is a
human decision in CaseGraph, and the demo should not pre-empt it.

Usage
-----
    python scripts/demo_seed.py
    python scripts/demo_seed.py --reset-simulation

Environment
-----------
    CASEGRAPH_PAYPAL_TRANSPORT=simulated   # required; the script refuses live mode
    CASEGRAPH_AI_PROVIDER=rules|auto|openai
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.ai.schemas import AnalyzeCaseRequest
from backend.ai.service import ai_reasoning_service, default_reasoning_provider
from backend.casegraph.schema import SupportIntakeRequest, TranscriptTurnInput
from backend.config import settings
from backend.db.migrations import create_all
from backend.paypal.disputes import disputes_client
from backend.paypal.http import get_simulator, simulated_transport_enabled
from backend.paypal.simulation_data import DEMO_EVIDENCE, DEMO_DISPUTES
from backend.services.cases import case_service
from backend.services.evidence import evidence_service


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed CaseGraph demo cases in the simulated PayPal sandbox")
    parser.add_argument(
        "--reset-simulation",
        action="store_true",
        help="Reset the simulated PayPal state to the shipped fixtures before seeding",
    )
    parser.add_argument(
        "--skip-analysis",
        action="store_true",
        help="Only sync disputes and store evidence; do not run AI reasoning",
    )
    return parser.parse_args()


async def seed(*, reset: bool, skip_analysis: bool) -> int:
    if not simulated_transport_enabled():
        print(
            "ERROR: scripts/demo_seed.py requires CASEGRAPH_PAYPAL_TRANSPORT=simulated.\n"
            "It never seeds data through the live PayPal API.",
            file=sys.stderr,
        )
        return 2

    create_all()
    simulator = get_simulator()
    if reset:
        simulator.reset()

    provider = default_reasoning_provider()
    print(f"reasoning provider: {getattr(provider, 'provider_name', type(provider).__name__)}")

    seeded: list[tuple[str, str]] = []
    for dispute in DEMO_DISPUTES:
        dispute_id = dispute["dispute_id"]
        payload = await disputes_client.get_dispute_details(dispute_id)
        case_id = case_service.sync_dispute_concurrency_safe(payload)

        evidence = DEMO_EVIDENCE.get(dispute_id) or {}
        transcript = [
            TranscriptTurnInput(speaker=turn["speaker"], message=turn["message"])
            for turn in evidence.get("transcript") or []
        ]
        notes = evidence.get("merchant_notes")
        if transcript or notes:
            evidence_service.ingest_support_intake(
                case_id,
                SupportIntakeRequest(
                    intake_request_id=f"INTAKE-DEMO-{dispute_id[-4:]}",
                    created_by="demo-seed",
                    transcript=transcript,
                    merchant_notes=notes,
                ),
            )

        if not skip_analysis:
            # Count first so a repeat run creates a fresh analysis rather than
            # replaying the previous request id: the analysis is idempotent per
            # request id, and a re-seed is an explicit request to analyse again.
            existing = await _analysis_count(case_id)
            analysis = await ai_reasoning_service.analyze(
                case_id,
                AnalyzeCaseRequest(
                    analysis_request_id=f"AIR-DEMO-{dispute_id[-4:]}-{existing + 1}",
                    requested_by="demo-seed",
                ),
            )
            status = analysis.status
            if analysis.error:
                status = f"{status} ({analysis.error[:120]})"
            print(f"  analysis: {status} graph={analysis.graph_id}")
        seeded.append((case_id, dispute_id))

    print("\nSeeded cases:")
    for case_id, dispute_id in seeded:
        print(f"  {case_id}  <-  {dispute_id}")
    print("\nOpen the workspace, select a case, review the graph and safety findings, then approve a payload.")
    return 0


async def _analysis_count(case_id: str) -> int:
    from backend.db.session import session_scope
    from backend.repositories import analyses as analysis_repo

    with session_scope() as session:
        return len(analysis_repo.list_for_case(session, case_id))


def main() -> int:
    args = parse_args()
    print(f"database: {settings.database_url}")
    return asyncio.run(seed(reset=args.reset_simulation, skip_analysis=args.skip_analysis))


if __name__ == "__main__":
    raise SystemExit(main())
