"""/auth/me returns the caller's OWN organization's display name (the UI shows it instead of an
"Org 1e49da8d" id prefix); it never reveals another tenant's name."""
from __future__ import annotations

from tests.integration.test_acquisition_pipeline import _org


def test_me_returns_own_organization_name_only(client, db_session):
    org_a, ha = _org(client, db_session, "alpha")
    org_b, hb = _org(client, db_session, "bravo")
    a = client.get("/api/v1/auth/me", headers=ha).json()
    b = client.get("/api/v1/auth/me", headers=hb).json()
    assert a["organization_name"].startswith("alpha-") and b["organization_name"].startswith("bravo-")
    assert a["organization_id"] == str(org_a) and b["organization_id"] == str(org_b)
    assert "bravo" not in str(a) and "alpha" not in str(b)
