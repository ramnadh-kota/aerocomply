import uuid

import pytest

from app.core.errors import NotFoundError
from app.schemas.compliance import RegulatoryRequirementCreateRequest
from app.schemas.regulatory_document import RegulatoryDocumentCreateRequest
from app.services import compliance_service, regulatory_service


def _create_document(db_session, org_id, **overrides):
    data = dict(
        authority="FAA",
        doc_type="AD",
        doc_number="2026-01-01",
        title="Wing spar inspection AD",
    )
    data.update(overrides)
    return regulatory_service.create_document(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=RegulatoryDocumentCreateRequest(**data),
    )


def test_create_document_defaults_not_configured_sync(db_session):
    org_id = uuid.uuid4()
    document = _create_document(db_session, org_id)
    assert document.sync_status == "NOT_CONFIGURED"
    assert document.source_status == "PUBLISHED"


def test_provider_status_all_not_configured():
    statuses = regulatory_service.get_provider_status()
    assert len(statuses) == 5
    assert all(s.status == "NOT_CONFIGURED" for s in statuses)
    authorities = {s.authority for s in statuses}
    assert authorities == {"DGCA", "FAA", "EASA", "CASA", "UK_CAA"}


def test_list_documents_filters_by_authority(db_session):
    org_id = uuid.uuid4()
    _create_document(db_session, org_id, authority="FAA", doc_number="FAA-1")
    _create_document(db_session, org_id, authority="EASA", doc_number="EASA-1")

    faa_only = regulatory_service.list_documents(
        db_session, organization_id=org_id, authority="FAA"
    )
    assert len(faa_only) == 1
    assert faa_only[0].authority == "FAA"


def test_get_document_cross_tenant_raises(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    document = _create_document(db_session, org_a)

    with pytest.raises(NotFoundError):
        regulatory_service.get_document(db_session, organization_id=org_b, document_id=document.id)


def test_requirement_can_cite_document(db_session):
    org_id = uuid.uuid4()
    document = _create_document(db_session, org_id)

    requirement = compliance_service.create_requirement(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=RegulatoryRequirementCreateRequest(
            authority="FAA",
            regulatory_document_id=document.id,
            requirement_number="AD-2026-01-01",
            title="Wing spar inspection",
            description="Repetitive inspection per AD.",
        ),
    )
    assert requirement.regulatory_document_id == document.id
