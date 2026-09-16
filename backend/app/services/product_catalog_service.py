"""Phase 18.2: mutation/read layer for the platform product catalog
(ProductSuite -> ProductModule -> ProductPage / ProductFeature).

Follows the exact create/flush/audit/commit transaction pattern established
by app/services/plan_service.py (itself following platform_service.py/
aircraft_service.py): mutate + db.flush() inside a try/except that
translates a unique-constraint IntegrityError into a clean ConflictError,
record the (still-uncommitted) audit event, then db.commit(). A flush
failure raises before the audit event is ever added and the whole thing
rolls back together, so a duplicate-code conflict can never leave a partial
catalog row or an orphaned audit event behind.

Audit attribution: catalog entities have no natural tenant subject (same as
Plan/PlanFeature), so each mutation is attributed to the acting platform
admin's own organization_id, exactly matching plan_service.py's precedent.

This module makes zero changes to app/services/entitlement_service.py or
app/core/deps.py::require_feature -- it only manages catalog metadata that
ProductFeature.code conventionally documents as the recommended value for a
PlanFeature.feature_key / require_feature() argument (see
app/models/product_catalog.py's module docstring for why there is no
foreign key between them).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ConflictError, NotFoundError
from app.models.product_catalog import ProductFeature, ProductModule, ProductPage, ProductSuite
from app.services.audit_service import record_audit_event

# --- Suite -------------------------------------------------------------


def list_suites(db: Session) -> list[ProductSuite]:
    return list(
        db.execute(select(ProductSuite).order_by(ProductSuite.display_order, ProductSuite.code))
        .scalars()
        .all()
    )


def get_catalog_tree(db: Session) -> list[ProductSuite]:
    """The full nested Suite -> Module -> (Page, Feature) tree, eagerly
    loaded in a bounded number of queries -- used by the single
    GET /platform/product-catalog endpoint that renders the whole
    hierarchy at once (e.g. for an admin UI tree view)."""
    return list(
        db.execute(
            select(ProductSuite)
            .options(
                selectinload(ProductSuite.modules).selectinload(ProductModule.pages),
                selectinload(ProductSuite.modules).selectinload(ProductModule.features),
            )
            .order_by(ProductSuite.display_order, ProductSuite.code)
        )
        .scalars()
        .all()
    )


def get_suite(db: Session, *, suite_id: uuid.UUID) -> ProductSuite:
    suite = db.get(ProductSuite, suite_id)
    if suite is None:
        raise NotFoundError("Product suite not found")
    return suite


def create_suite(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    actor_organization_id: uuid.UUID,
    code: str,
    name: str,
    description: str | None = None,
    display_order: int = 0,
    is_active: bool = True,
) -> ProductSuite:
    suite = ProductSuite(
        code=code,
        name=name,
        description=description,
        display_order=display_order,
        is_active=is_active,
    )
    db.add(suite)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            f"Product suite code {code!r} already exists", code="duplicate_suite_code"
        ) from exc
    record_audit_event(
        db,
        organization_id=actor_organization_id,
        user_id=actor_user_id,
        action="platform.product_suite.created",
        entity_type="ProductSuite",
        entity_id=suite.id,
        metadata={"code": code, "name": name},
    )
    db.commit()
    db.refresh(suite)
    return suite


def update_suite(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    actor_organization_id: uuid.UUID,
    suite_id: uuid.UUID,
    name: str | None = None,
    description: str | None = None,
    display_order: int | None = None,
    is_active: bool | None = None,
) -> ProductSuite:
    suite = get_suite(db, suite_id=suite_id)

    updates: dict = {}
    if name is not None:
        suite.name = name
        updates["name"] = name
    if description is not None:
        suite.description = description
        updates["description"] = description
    if display_order is not None:
        suite.display_order = display_order
        updates["display_order"] = display_order
    if is_active is not None:
        suite.is_active = is_active
        updates["is_active"] = is_active

    db.add(suite)
    if updates:
        db.flush()
        record_audit_event(
            db,
            organization_id=actor_organization_id,
            user_id=actor_user_id,
            action="platform.product_suite.updated",
            entity_type="ProductSuite",
            entity_id=suite.id,
            metadata=updates,
        )
    db.commit()
    db.refresh(suite)
    return suite


# --- Module --------------------------------------------------------------


def list_modules(db: Session, *, suite_id: uuid.UUID | None = None) -> list[ProductModule]:
    stmt = select(ProductModule).order_by(ProductModule.display_order, ProductModule.code)
    if suite_id is not None:
        stmt = stmt.where(ProductModule.suite_id == suite_id)
    return list(db.execute(stmt).scalars().all())


def get_module(db: Session, *, module_id: uuid.UUID) -> ProductModule:
    module = db.get(ProductModule, module_id)
    if module is None:
        raise NotFoundError("Product module not found")
    return module


def create_module(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    actor_organization_id: uuid.UUID,
    suite_id: uuid.UUID,
    code: str,
    name: str,
    description: str | None = None,
    display_order: int = 0,
    is_active: bool = True,
) -> ProductModule:
    # Resolving the parent suite first (rather than trusting the FK alone to
    # reject an invalid suite_id) is what lets this raise the same safe,
    # typed NotFoundError every other "invalid parent relationship" check in
    # this codebase raises, instead of a raw IntegrityError/ForeignKeyViolation.
    get_suite(db, suite_id=suite_id)

    module = ProductModule(
        suite_id=suite_id,
        code=code,
        name=name,
        description=description,
        display_order=display_order,
        is_active=is_active,
    )
    db.add(module)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            f"Product module code {code!r} already exists", code="duplicate_module_code"
        ) from exc
    record_audit_event(
        db,
        organization_id=actor_organization_id,
        user_id=actor_user_id,
        action="platform.product_module.created",
        entity_type="ProductModule",
        entity_id=module.id,
        metadata={"code": code, "name": name, "suite_id": str(suite_id)},
    )
    db.commit()
    db.refresh(module)
    return module


def update_module(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    actor_organization_id: uuid.UUID,
    module_id: uuid.UUID,
    name: str | None = None,
    description: str | None = None,
    display_order: int | None = None,
    is_active: bool | None = None,
) -> ProductModule:
    module = get_module(db, module_id=module_id)

    updates: dict = {}
    if name is not None:
        module.name = name
        updates["name"] = name
    if description is not None:
        module.description = description
        updates["description"] = description
    if display_order is not None:
        module.display_order = display_order
        updates["display_order"] = display_order
    if is_active is not None:
        module.is_active = is_active
        updates["is_active"] = is_active

    db.add(module)
    if updates:
        db.flush()
        record_audit_event(
            db,
            organization_id=actor_organization_id,
            user_id=actor_user_id,
            action="platform.product_module.updated",
            entity_type="ProductModule",
            entity_id=module.id,
            metadata=updates,
        )
    db.commit()
    db.refresh(module)
    return module


# --- Page ------------------------------------------------------------------


def list_pages(db: Session, *, module_id: uuid.UUID | None = None) -> list[ProductPage]:
    stmt = select(ProductPage).order_by(ProductPage.display_order, ProductPage.code)
    if module_id is not None:
        stmt = stmt.where(ProductPage.module_id == module_id)
    return list(db.execute(stmt).scalars().all())


def get_page(db: Session, *, page_id: uuid.UUID) -> ProductPage:
    page = db.get(ProductPage, page_id)
    if page is None:
        raise NotFoundError("Product page not found")
    return page


def create_page(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    actor_organization_id: uuid.UUID,
    module_id: uuid.UUID,
    code: str,
    name: str,
    description: str | None = None,
    route: str | None = None,
    display_order: int = 0,
    is_active: bool = True,
) -> ProductPage:
    get_module(db, module_id=module_id)

    page = ProductPage(
        module_id=module_id,
        code=code,
        name=name,
        description=description,
        route=route,
        display_order=display_order,
        is_active=is_active,
    )
    db.add(page)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            f"Product page code {code!r} already exists", code="duplicate_page_code"
        ) from exc
    record_audit_event(
        db,
        organization_id=actor_organization_id,
        user_id=actor_user_id,
        action="platform.product_page.created",
        entity_type="ProductPage",
        entity_id=page.id,
        metadata={"code": code, "name": name, "module_id": str(module_id)},
    )
    db.commit()
    db.refresh(page)
    return page


def update_page(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    actor_organization_id: uuid.UUID,
    page_id: uuid.UUID,
    name: str | None = None,
    description: str | None = None,
    route: str | None = None,
    display_order: int | None = None,
    is_active: bool | None = None,
) -> ProductPage:
    page = get_page(db, page_id=page_id)

    updates: dict = {}
    if name is not None:
        page.name = name
        updates["name"] = name
    if description is not None:
        page.description = description
        updates["description"] = description
    if route is not None:
        page.route = route
        updates["route"] = route
    if display_order is not None:
        page.display_order = display_order
        updates["display_order"] = display_order
    if is_active is not None:
        page.is_active = is_active
        updates["is_active"] = is_active

    db.add(page)
    if updates:
        db.flush()
        record_audit_event(
            db,
            organization_id=actor_organization_id,
            user_id=actor_user_id,
            action="platform.product_page.updated",
            entity_type="ProductPage",
            entity_id=page.id,
            metadata=updates,
        )
    db.commit()
    db.refresh(page)
    return page


# --- Feature ---------------------------------------------------------------


def list_features(db: Session, *, module_id: uuid.UUID | None = None) -> list[ProductFeature]:
    stmt = select(ProductFeature).order_by(ProductFeature.code)
    if module_id is not None:
        stmt = stmt.where(ProductFeature.module_id == module_id)
    return list(db.execute(stmt).scalars().all())


def get_feature(db: Session, *, feature_id: uuid.UUID) -> ProductFeature:
    feature = db.get(ProductFeature, feature_id)
    if feature is None:
        raise NotFoundError("Product feature not found")
    return feature


def create_feature(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    actor_organization_id: uuid.UUID,
    module_id: uuid.UUID,
    code: str,
    name: str,
    description: str | None = None,
    is_active: bool = True,
) -> ProductFeature:
    get_module(db, module_id=module_id)

    feature = ProductFeature(
        module_id=module_id,
        code=code,
        name=name,
        description=description,
        is_active=is_active,
    )
    db.add(feature)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            f"Product feature code {code!r} already exists", code="duplicate_feature_code"
        ) from exc
    record_audit_event(
        db,
        organization_id=actor_organization_id,
        user_id=actor_user_id,
        action="platform.product_feature.created",
        entity_type="ProductFeature",
        entity_id=feature.id,
        metadata={"code": code, "name": name, "module_id": str(module_id)},
    )
    db.commit()
    db.refresh(feature)
    return feature


def update_feature(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    actor_organization_id: uuid.UUID,
    feature_id: uuid.UUID,
    name: str | None = None,
    description: str | None = None,
    is_active: bool | None = None,
) -> ProductFeature:
    feature = get_feature(db, feature_id=feature_id)

    updates: dict = {}
    if name is not None:
        feature.name = name
        updates["name"] = name
    if description is not None:
        feature.description = description
        updates["description"] = description
    if is_active is not None:
        feature.is_active = is_active
        updates["is_active"] = is_active

    db.add(feature)
    if updates:
        db.flush()
        record_audit_event(
            db,
            organization_id=actor_organization_id,
            user_id=actor_user_id,
            action="platform.product_feature.updated",
            entity_type="ProductFeature",
            entity_id=feature.id,
            metadata=updates,
        )
    db.commit()
    db.refresh(feature)
    return feature
