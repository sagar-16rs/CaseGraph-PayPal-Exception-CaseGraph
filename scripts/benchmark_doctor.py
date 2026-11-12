from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.benchmark.doctor import run


def main() -> int:
    parser = argparse.ArgumentParser(description="CaseGraph benchmark diagnostics")
    parser.add_argument("--data-dir", default=str(ROOT / "data" / "benchmark"))
    parser.add_argument("--require-casegraph", action="store_true")
    parser.add_argument("--require-openai", action="store_true")
    args = parser.parse_args()
    result = run(
        Path(args.data_dir),
        require_casegraph=args.require_casegraph,
        require_openai=args.require_openai,
        repo_root=ROOT,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
