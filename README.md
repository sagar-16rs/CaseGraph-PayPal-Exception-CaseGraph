CaseGraph runs out-of-the-box from source in under 2 minutes with zero external credentials required (using our built-in deterministic simulated PayPal sandbox and reference reasoner), or against the live PayPal Sandbox + OpenAI/DeepSeek APIs:

1. Backend setup:
   python -m venv .venv && . .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
   pip install -r requirements-dev.txt -r requirements-production.txt
   cp .env.example .env
   export CASEGRAPH_PAYPAL_TRANSPORT=simulated    # PowerShell: $env:CASEGRAPH_PAYPAL_TRANSPORT="simulated"
   python scripts/demo_seed.py --reset-simulation
   uvicorn backend.main:app --reload --port 8000

2. Frontend workspace (second terminal):
   cd frontend && npm install && npm run dev
   Open http://localhost:5173

3. What to explore:
   - PP-D-DEMO-1001: Contradicted customer vs. merchant claim -> safety policy downgrades high-risk actions to REVIEW and allows only SEND_MESSAGE.
   - PP-D-DEMO-1002: Merchandise damage claim -> missing condition proof surfaced as a first-class MISSING_EVIDENCE node and negation-aware readiness gap.
   - PP-D-DEMO-1003: Unauthorized transaction inquiry -> PASS for PROVIDE_SUPPORTING_INFO requiring human approval of the exact typed payload.
   - Fault injection: Set CASEGRAPH_SIMULATED_FAULT=timeout and execute an approved action to see CaseGraph fail closed into UNKNOWN_OUTCOME without blindly retrying.
