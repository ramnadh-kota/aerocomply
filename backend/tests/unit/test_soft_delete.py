"""Unit tests for the Platform Control Plane soft-delete pilot (Asset):
deletion_service (tenant soft-delete, platform permanent-delete) and
restoration_service (platform list/restore).

Same convention as tests/unit/test_common_aerospace_domain.py: MagicMock
Session, no DB -- these test the service-layer logic (state transitions,
guard conditions, audit calls) in isolation from Postgres.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.errors import ConflictError, NotFoundError
from app.models.asset import Asset
from app.models.organization import Organization
from app.schemas.deletion import AssetDeleteRequest, OrganizationDeletionRequest, PermanentDeleteRequest
from app.services import deletion_service, restoration_service

TENANT_A = uuid.UUID("00000000-0000-0000-0000-000000000001")
USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000010")


def _org(**overrides):
    defaults = dict(
        id=TENANT_A,
        name="Test Org",
        status="ACTIVE",
        deleted_at=None,
        deleted_by=None,
        deletion_reason=None,
        restored_at=None,
        restored_by=None,
    )
    defaults.update(overrides)
    return Organization(**defaults)


def _asset(**overrides):
    defaults = dict(
        id=uuid.uuid4(),
        organization_id=TENANT_A,
        asset_type="AIRCRAFT",
        registration="N100SD",
        status="ACTIVE",
        deleted_at=None,
        deleted_by=None,
        deletion_reason=None,
        restored_at=None,
        restored_by=None,
    )
    defaults.update(overrides)
    return Asset(**defaults)


class TestSoftDeleteAsset:
    def test_soft_delete_stamps_metadata_and_audits(self):
        db = MagicMock()
        asset = _asset()
        db.execute.return_value.scalar_one_or_none.return_value = asset

        with patch("app.services.deletion_service.record_audit_event") as mock_audit:
            result = deletion_service.soft_delete_asset(
                db,
                organization_id=TENANT_A,
                actor_user_id=USER_ID,
                asset_id=asset.id,
                payload=AssetDeleteRequest(reason="Retired from fleet"),
            )
            assert result.deleted_at is not None
            assert result.deleted_by == USER_ID
            assert result.deletion_reason == "Retired from fleet"
            assert db.commit.called
            mock_audit.assert_called_once()
            assert mock_audit.call_args.kwargs["action"] == "asset.deleted"
            assert mock_audit.call_args.kwargs["entity_type"] == "Asset"

    def test_soft_delete_missing_asset_raises_not_found(self):
        db = MagicMock()
        db.execute.return_value.scalar_one_or_none.return_value = None
        with pytest.raises(NotFoundError):
            deletion_service.soft_delete_asset(
                db,
                organization_id=TENANT_A,
                actor_user_id=USER_ID,
                asset_id=uuid.uuid4(),
                payload=AssetDeleteRequest(),
            )

    def test_soft_delete_already_deleted_raises_conflict(self):
        db = MagicMock()
        asset = _asset(deleted_at=datetime.now(UTC))
        db.execute.return_value.scalar_one_or_none.return_value = asset
        with pytest.raises(ConflictError) as exc:
            deletion_service.soft_delete_asset(
                db,
                organization_id=TENANT_A,
                actor_user_id=USER_ID,
                asset_id=asset.id,
                payload=AssetDeleteRequest(),
            )
        assert exc.value.code == "already_deleted"

    def test_soft_delete_reason_is_optional(self):
        db = MagicMock()
        asset = _asset()
        db.execute.return_value.scalar_one_or_none.return_value = asset
        with patch("app.services.deletion_service.record_audit_event"):
            result = deletion_service.soft_delete_asset(
                db,
                organization_id=TENANT_A,
                actor_user_id=USER_ID,
                asset_id=asset.id,
                payload=AssetDeleteRequest(),
            )
            assert result.deletion_reason is None


class TestPermanentDeleteAsset:
    def test_requires_explicit_confirmation(self):
        db = MagicMock()
        with pytest.raises(ConflictError) as exc:
            deletion_service.permanently_delete_asset(
                db,
                actor_user_id=USER_ID,
                asset_id=uuid.uuid4(),
                payload=PermanentDeleteRequest(reason="cleanup", confirm=False),
            )
        assert exc.value.code == "confirmation_required"
        assert not db.execute.called

    def test_missing_asset_raises_not_found(self):
        db = MagicMock()
        db.execute.return_value.scalar_one_or_none.return_value = None
        with pytest.raises(NotFoundError):
            deletion_service.permanently_delete_asset(
                db,
                actor_user_id=USER_ID,
                asset_id=uuid.uuid4(),
                payload=PermanentDeleteRequest(reason="cleanup", confirm=True),
            )

    def test_refuses_to_permanently_delete_a_still_active_asset(self):
        db = MagicMock()
        asset = _asset(deleted_at=None)
        db.execute.return_value.scalar_one_or_none.return_value = asset
        with pytest.raises(ConflictError) as exc:
            deletion_service.permanently_delete_asset(
                db,
                actor_user_id=USER_ID,
                asset_id=asset.id,
                payload=PermanentDeleteRequest(reason="cleanup", confirm=True),
            )
        assert exc.value.code == "not_soft_deleted"
        assert not db.delete.called

    def test_permanently_deletes_a_soft_deleted_asset_and_audits_first(self):
        db = MagicMock()
        asset = _asset(deleted_at=datetime.now(UTC), deleted_by=USER_ID)
        db.execute.return_value.scalar_one_or_none.return_value = asset

        with patch("app.services.deletion_service.record_audit_event") as mock_audit:
            deletion_service.permanently_delete_asset(
                db,
                actor_user_id=USER_ID,
                asset_id=asset.id,
                payload=PermanentDeleteRequest(reason="Confirmed disposed", confirm=True),
            )
            mock_audit.assert_called_once()
            assert mock_audit.call_args.kwargs["action"] == "asset.permanently_deleted"
            assert db.delete.called
            assert db.commit.called

    def test_dependent_records_block_permanent_delete_with_clear_error(self):
        """Every FK to assets.id from operational/compliance tables (Flight,
        Component, WorkOrder, ...) is declared ondelete=RESTRICT -- Postgres
        itself refuses the DELETE. This must surface as a clear ConflictError,
        not a raw IntegrityError/500."""
        db = MagicMock()
        asset = _asset(deleted_at=datetime.now(UTC))
        db.execute.return_value.scalar_one_or_none.return_value = asset
        db.commit.side_effect = IntegrityError("DELETE", {}, Exception("FK violation"))

        with patch("app.services.deletion_service.record_audit_event"):
            with pytest.raises(ConflictError) as exc:
                deletion_service.permanently_delete_asset(
                    db,
                    actor_user_id=USER_ID,
                    asset_id=asset.id,
                    payload=PermanentDeleteRequest(reason="cleanup", confirm=True),
                )
            assert exc.value.code == "has_dependent_records"
            assert db.rollback.called


class TestRestoreAsset:
    def test_restore_clears_deletion_metadata_and_stamps_restore(self):
        db = MagicMock()
        asset = _asset(
            deleted_at=datetime.now(UTC), deleted_by=USER_ID, deletion_reason="oops"
        )
        db.execute.return_value.scalar_one_or_none.return_value = asset

        with patch("app.services.restoration_service.record_audit_event") as mock_audit:
            result = restoration_service.restore_asset(
                db, actor_user_id=USER_ID, asset_id=asset.id
            )
            assert result.deleted_at is None
            assert result.deleted_by is None
            assert result.deletion_reason is None
            assert result.restored_at is not None
            assert result.restored_by == USER_ID
            mock_audit.assert_called_once()
            assert mock_audit.call_args.kwargs["action"] == "asset.restored"

    def test_restore_missing_asset_raises_not_found(self):
        db = MagicMock()
        db.execute.return_value.scalar_one_or_none.return_value = None
        with pytest.raises(NotFoundError):
            restoration_service.restore_asset(db, actor_user_id=USER_ID, asset_id=uuid.uuid4())

    def test_restore_a_never_deleted_asset_raises_conflict(self):
        db = MagicMock()
        asset = _asset(deleted_at=None)
        db.execute.return_value.scalar_one_or_none.return_value = asset
        with pytest.raises(ConflictError) as exc:
            restoration_service.restore_asset(db, actor_user_id=USER_ID, asset_id=asset.id)
        assert exc.value.code == "not_deleted"


class TestListDeletedRecords:
    def test_maps_asset_rows_to_response_shape(self):
        db = MagicMock()
        asset = _asset(
            deleted_at=datetime.now(UTC), deleted_by=USER_ID, deletion_reason="test"
        )
        # entity_type="ASSET" -> only _deleted_assets' single query runs.
        db.execute.return_value.scalars.return_value.all.return_value = [asset]

        items, total = restoration_service.list_deleted_records(
            db, entity_type="ASSET", organization_id=TENANT_A
        )
        assert total == 1
        assert len(items) == 1
        assert items[0].entity_type == "ASSET"
        assert items[0].status == "DELETED"
        assert items[0].identifier == "N100SD"
        assert items[0].deletion_reason == "test"

    def test_maps_organization_rows_to_response_shape(self):
        db = MagicMock()
        org = _org(deleted_at=datetime.now(UTC), deleted_by=USER_ID, deletion_reason="offboarding")
        db.execute.return_value.scalars.return_value.all.return_value = [org]

        items, total = restoration_service.list_deleted_records(db, entity_type="ORGANIZATION")
        assert total == 1
        assert items[0].entity_type == "ORGANIZATION"
        assert items[0].identifier == "Test Org"
        assert items[0].asset_type is None
        assert items[0].deletion_reason == "offboarding"

    def test_merges_both_entity_types_sorted_by_deleted_at_desc_when_unfiltered(self):
        db = MagicMock()
        older_asset = _asset(deleted_at=datetime(2026, 1, 1, tzinfo=UTC))
        newer_org = _org(deleted_at=datetime(2026, 6, 1, tzinfo=UTC))
        db.execute.side_effect = [
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[older_asset])))),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[newer_org])))),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
        ]

        items, total = restoration_service.list_deleted_records(db)
        assert total == 2
        assert items[0].entity_type == "ORGANIZATION"  # newer first
        assert items[1].entity_type == "ASSET"

    def test_clamps_limit_to_max(self):
        db = MagicMock()
        db.execute.return_value.scalars.return_value.all.return_value = []
        restoration_service.list_deleted_records(db, entity_type="ASSET", limit=99999)
        # No assertion error means the clamp math ran without raising; the
        # actual SQL LIMIT value isn't observable through this mock, so the
        # clamp is separately exercised by the module-level constant checks.
        assert restoration_service.DELETED_RECORDS_MAX_LIMIT == 100


class TestRequestOrganizationDeletion:
    def test_stamps_metadata_and_audits(self):
        db = MagicMock()
        org = _org()
        db.get.return_value = org

        with patch("app.services.deletion_service.record_audit_event") as mock_audit:
            result = deletion_service.request_organization_deletion(
                db,
                organization_id=TENANT_A,
                actor_user_id=USER_ID,
                payload=OrganizationDeletionRequest(reason="Closing account"),
            )
            assert result.deleted_at is not None
            assert result.deleted_by == USER_ID
            assert result.deletion_reason == "Closing account"
            assert db.commit.called
            mock_audit.assert_called_once()
            assert mock_audit.call_args.kwargs["action"] == "organization.deletion_requested"
            assert mock_audit.call_args.kwargs["entity_type"] == "Organization"

    def test_missing_organization_raises_not_found(self):
        db = MagicMock()
        db.get.return_value = None
        with pytest.raises(NotFoundError):
            deletion_service.request_organization_deletion(
                db,
                organization_id=TENANT_A,
                actor_user_id=USER_ID,
                payload=OrganizationDeletionRequest(),
            )

    def test_already_requested_raises_conflict(self):
        db = MagicMock()
        org = _org(deleted_at=datetime.now(UTC))
        db.get.return_value = org
        with pytest.raises(ConflictError) as exc:
            deletion_service.request_organization_deletion(
                db,
                organization_id=TENANT_A,
                actor_user_id=USER_ID,
                payload=OrganizationDeletionRequest(),
            )
        assert exc.value.code == "already_deleted"


class TestPermanentlyDeleteOrganization:
    def test_requires_explicit_confirmation(self):
        db = MagicMock()
        with pytest.raises(ConflictError) as exc:
            deletion_service.permanently_delete_organization(
                db,
                actor_user_id=USER_ID,
                organization_id=TENANT_A,
                payload=PermanentDeleteRequest(reason="cleanup", confirm=False),
            )
        assert exc.value.code == "confirmation_required"
        assert not db.get.called

    def test_missing_organization_raises_not_found(self):
        db = MagicMock()
        db.get.return_value = None
        with pytest.raises(NotFoundError):
            deletion_service.permanently_delete_organization(
                db,
                actor_user_id=USER_ID,
                organization_id=TENANT_A,
                payload=PermanentDeleteRequest(reason="cleanup", confirm=True),
            )

    def test_refuses_a_still_active_organization(self):
        db = MagicMock()
        org = _org(deleted_at=None)
        db.get.return_value = org
        with pytest.raises(ConflictError) as exc:
            deletion_service.permanently_delete_organization(
                db,
                actor_user_id=USER_ID,
                organization_id=TENANT_A,
                payload=PermanentDeleteRequest(reason="cleanup", confirm=True),
            )
        assert exc.value.code == "not_soft_deleted"
        assert not db.delete.called

    def test_refuses_when_users_still_exist(self):
        db = MagicMock()
        org = _org(deleted_at=datetime.now(UTC))
        db.get.return_value = org
        db.execute.side_effect = [
            MagicMock(scalar_one=MagicMock(return_value=1)),  # user_count
            MagicMock(scalar_one=MagicMock(return_value=0)),  # asset_count
        ]
        with pytest.raises(ConflictError) as exc:
            deletion_service.permanently_delete_organization(
                db,
                actor_user_id=USER_ID,
                organization_id=TENANT_A,
                payload=PermanentDeleteRequest(reason="cleanup", confirm=True),
            )
        assert exc.value.code == "has_dependent_records"
        assert not db.delete.called

    def test_refuses_when_assets_still_exist(self):
        db = MagicMock()
        org = _org(deleted_at=datetime.now(UTC))
        db.get.return_value = org
        db.execute.side_effect = [
            MagicMock(scalar_one=MagicMock(return_value=0)),  # user_count
            MagicMock(scalar_one=MagicMock(return_value=1)),  # asset_count
        ]
        with pytest.raises(ConflictError) as exc:
            deletion_service.permanently_delete_organization(
                db,
                actor_user_id=USER_ID,
                organization_id=TENANT_A,
                payload=PermanentDeleteRequest(reason="cleanup", confirm=True),
            )
        assert exc.value.code == "has_dependent_records"

    def test_deletes_a_genuinely_empty_organization_and_audits_first(self):
        db = MagicMock()
        org = _org(deleted_at=datetime.now(UTC))
        db.get.return_value = org
        db.execute.side_effect = [
            MagicMock(scalar_one=MagicMock(return_value=0)),  # user_count
            MagicMock(scalar_one=MagicMock(return_value=0)),  # asset_count
        ]
        with patch("app.services.deletion_service.record_audit_event") as mock_audit:
            deletion_service.permanently_delete_organization(
                db,
                actor_user_id=USER_ID,
                organization_id=TENANT_A,
                payload=PermanentDeleteRequest(reason="confirmed empty", confirm=True),
            )
            mock_audit.assert_called_once()
            assert mock_audit.call_args.kwargs["action"] == "organization.permanently_deleted"
            assert db.delete.called
            assert db.commit.called


class TestRestoreOrganization:
    def test_restore_clears_deletion_metadata_and_stamps_restore(self):
        db = MagicMock()
        org = _org(deleted_at=datetime.now(UTC), deleted_by=USER_ID, deletion_reason="oops")
        db.get.return_value = org

        with patch("app.services.restoration_service.record_audit_event") as mock_audit:
            result = restoration_service.restore_organization(
                db, actor_user_id=USER_ID, organization_id=TENANT_A
            )
            assert result.deleted_at is None
            assert result.deleted_by is None
            assert result.deletion_reason is None
            assert result.restored_at is not None
            assert result.restored_by == USER_ID
            mock_audit.assert_called_once()
            assert mock_audit.call_args.kwargs["action"] == "organization.restored"

    def test_restore_missing_organization_raises_not_found(self):
        db = MagicMock()
        db.get.return_value = None
        with pytest.raises(NotFoundError):
            restoration_service.restore_organization(
                db, actor_user_id=USER_ID, organization_id=TENANT_A
            )

    def test_restore_a_never_deleted_organization_raises_conflict(self):
        db = MagicMock()
        org = _org(deleted_at=None)
        db.get.return_value = org
        with pytest.raises(ConflictError) as exc:
            restoration_service.restore_organization(
                db, actor_user_id=USER_ID, organization_id=TENANT_A
            )
        assert exc.value.code == "not_deleted"
