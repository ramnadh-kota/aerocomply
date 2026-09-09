import uuid

import pytest

from app.core.errors import NotFoundError
from app.schemas.vendor import VendorCreateRequest, VendorUpdateRequest
from app.services import vendor_service


def _payload(**overrides) -> VendorCreateRequest:
    data = dict(
        name="Skyline Component Supply",
        contact_email="ops@skyline.example",
        location="Wichita, KS",
        certifications="AS9120,FAA-AC00-56B",
        approved=False,
    )
    data.update(overrides)
    return VendorCreateRequest(**data)


def test_create_and_get_vendor(db_session):
    org_id = uuid.uuid4()
    vendor = vendor_service.create_vendor(
        db_session, organization_id=org_id, actor_user_id=None, payload=_payload()
    )
    assert vendor.id is not None
    assert vendor.organization_id == org_id
    assert vendor.approved is False

    fetched = vendor_service.get_vendor(db_session, organization_id=org_id, vendor_id=vendor.id)
    assert fetched.id == vendor.id


def test_get_vendor_not_found_raises(db_session):
    with pytest.raises(NotFoundError):
        vendor_service.get_vendor(
            db_session, organization_id=uuid.uuid4(), vendor_id=uuid.uuid4()
        )


def test_list_vendors_scoped_to_organization(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    vendor_service.create_vendor(
        db_session, organization_id=org_a, actor_user_id=None, payload=_payload()
    )
    vendor_service.create_vendor(
        db_session, organization_id=org_b, actor_user_id=None, payload=_payload(name="Other Co")
    )

    vendors_a = vendor_service.list_vendors(db_session, organization_id=org_a)
    vendors_b = vendor_service.list_vendors(db_session, organization_id=org_b)

    assert len(vendors_a) == 1
    assert len(vendors_b) == 1
    assert vendors_a[0].organization_id == org_a


def test_org_b_cannot_get_org_a_vendor(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    vendor = vendor_service.create_vendor(
        db_session, organization_id=org_a, actor_user_id=None, payload=_payload()
    )

    with pytest.raises(NotFoundError):
        vendor_service.get_vendor(db_session, organization_id=org_b, vendor_id=vendor.id)


def test_update_vendor_approval(db_session):
    org_id = uuid.uuid4()
    vendor = vendor_service.create_vendor(
        db_session, organization_id=org_id, actor_user_id=None, payload=_payload()
    )
    updated = vendor_service.update_vendor(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        vendor_id=vendor.id,
        payload=VendorUpdateRequest(approved=True),
    )
    assert updated.approved is True


def test_update_vendor_not_found_raises(db_session):
    with pytest.raises(NotFoundError):
        vendor_service.update_vendor(
            db_session,
            organization_id=uuid.uuid4(),
            actor_user_id=None,
            vendor_id=uuid.uuid4(),
            payload=VendorUpdateRequest(approved=True),
        )
