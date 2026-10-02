"""LISA must describe HUMS exceedances as *recorded*: the exceedance model has
no status/resolved field, so open/active/resolved state can never be inferred."""

import re
from pathlib import Path

LISA_DIR = Path(__file__).resolve().parents[2] / "app" / "services" / "lisa"


def test_lisa_never_claims_exceedances_are_active_or_resolved():
    pattern = re.compile(r"(active|open|unresolved|outstanding|resolved)\s+exceedance", re.I)
    offenders = []
    for path in LISA_DIR.rglob("*.py"):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{path.name}:{n}: {line.strip()}")
    assert not offenders, offenders


def test_lisa_telemetry_wording_uses_recorded_exceedance():
    src = (LISA_DIR / "orchestration_service.py").read_text(encoding="utf-8")
    assert "recorded exceedance(s)" in src
