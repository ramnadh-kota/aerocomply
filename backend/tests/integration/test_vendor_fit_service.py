import uuid

import pytest

from app.core.errors import NotFoundError
from app.schemas.part import PartCreateRequest
from app.schemas.vendor import VendorCreateRequest
from app.schemas.vendor_part_availability import VendorPartAvailabilityCreateRequest
from app.services import (
    part_service,
    vendor_fit_service,
    vendor_part_availability_service,
    vendor_service,
)


def _create_part(db_session, org_id, **overrides):
    data = dict(part_number="PN-4000", description="Nav antenna")
    data.update(overrides)
    return part_service.create_part(
        db_session, organization_id=org_id, actor_user_id=None, payload=PartCreateRequest(**data)
    )


def _create_vendor(db_session, org_id, **overrides):
    data = dict(name="Acme Aerospace")
    data.update(overrides)
    return vendor_service.create_vendor(
        db_session, organization_id=org_id, actor_user_id=None, payload=VendorCreateRequest(**data)
    )


def test_fully_scored_vendor_ranks_above_partially_scored(db_session):
    org_id = uuid.uuid4()
    part = _create_part(db_session, org_id)
    full_vendor = _create_vendor(db_session, org_id, name="Full Data Vendor", reliability_score=90)
    partial_vendor = _create_vendor(db_session, org_id, name="Partial Data Vendor")

    vendor_part_availability_service.create_availability(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=VendorPartAvailabilityCreateRequest(
            vendor_id=full_vendor.id,
            part_id=part.id,
            availability_status="IN_STOCK",
            lead_time_days=1,
            unit_price_cents=10000,
            currency="USD",
            certification_status="VERIFIED",
        ),
    )
    vendor_part_availability_service.create_availability(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=VendorPartAvailabilityCreateRequest(
            vendor_id=partial_vendor.id, part_id=part.id, availability_status="OUT_OF_STOCK"
        ),
    )

    results = vendor_fit_service.score_vendor_options_for_part(
        db_session, organization_id=org_id, part_id=part.id
    )

    assert len(results) == 2
    assert results[0].vendor_id == full_vendor.id
    assert results[0].confidence == "HIGH"
    assert results[0].missing_factors == []
    assert "vendor reliability history unavailable" in results[1].missing_factors


def test_no_data_never_defaults_to_zero_score(db_session):
    org_id = uuid.uuid4()
    part = _create_part(db_session, org_id)
    vendor = _create_vendor(db_session, org_id)
    vendor_part_availability_service.create_availability(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=VendorPartAvailabilityCreateRequest(vendor_id=vendor.id, part_id=part.id),
    )

    results = vendor_fit_service.score_vendor_options_for_part(
        db_session, organization_id=org_id, part_id=part.id
    )

    assert results[0].score is None
    assert results[0].confidence == "UNKNOWN"
    assert len(results[0].missing_factors) == 5


def test_vendor_fit_scoped_to_part(db_session):
    org_id = uuid.uuid4()
    part_a = _create_part(db_session, org_id, part_number="PN-4001")
    part_b = _create_part(db_session, org_id, part_number="PN-4002")
    vendor = _create_vendor(db_session, org_id)
    vendor_part_availability_service.create_availability(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=VendorPartAvailabilityCreateRequest(vendor_id=vendor.id, part_id=part_a.id),
    )

    results_a = vendor_fit_service.score_vendor_options_for_part(
        db_session, organization_id=org_id, part_id=part_a.id
    )
    results_b = vendor_fit_service.score_vendor_options_for_part(
        db_session, organization_id=org_id, part_id=part_b.id
    )
    assert len(results_a) == 1
    assert results_b == []


def test_create_availability_cross_tenant_part_rejected(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    part = _create_part(db_session, org_a)
    vendor = _create_vendor(db_session, org_b)

    with pytest.raises(NotFoundError):
        vendor_part_availability_service.create_availability(
            db_session,
            organization_id=org_b,
            actor_user_id=None,
            payload=VendorPartAvailabilityCreateRequest(vendor_id=vendor.id, part_id=part.id),
        )


def test_vendor_reliability_score_persists(db_session):
    org_id = uuid.uuid4()
    vendor = _create_vendor(db_session, org_id, reliability_score=75)
    assert vendor.reliability_score == 75
