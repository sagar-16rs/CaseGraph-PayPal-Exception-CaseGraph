from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def test_expected_casegraph_interfaces_exist():
    if not Path("backend").is_dir():
        pytest.skip("repository interfaces unavailable in this verification environment")
    for module in [
        "backend.ai.schemas",
        "backend.ai.service",
        "backend.casegraph.schema",
        "backend.safety.service",
        "backend.services.cases",
        "backend.services.evidence",
    ]:
        importlib.import_module(module)
