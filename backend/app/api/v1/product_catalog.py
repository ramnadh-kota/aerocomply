"""Phase 18.2: platform product catalog administration
(Suite -> Module -> Page / Feature).

Every mutation here requires Permission.PLATFORM_MANAGE -- the same
canonical platform permission every other platform-catalog mutation in this
codebase already uses (Plan/PlanFeature, see app/api/v1/platform.py), never
a new permission. Tenant/organization users receive a 403 from
require_permission before this router's code ever runs, exactly like every
other PLATFORM_MANAGE-gated route.

This module contains no entitlement logic and no authorization logic of its
own beyond that single permission check -- see app/services/
product_catalog_service.py for the actual create/read/update behavior and
app/models/product_catalog.py for why this catalog is deliberately NOT
wired into app.services.entitlement_service's resolution path.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.product_catalog import (
    ProductFeatureCreateRequest,
    ProductFeatureResponse,
    ProductFeatureUpdateRequest,
    ProductModuleCreateRequest,
    ProductModuleResponse,
    ProductModuleUpdateRequest,
    ProductModuleWithChildrenResponse,
    ProductPageCreateRequest,
    ProductPageResponse,
    ProductPageUpdateRequest,
    ProductSuiteCreateRequest,
    ProductSuiteResponse,
    ProductSuiteUpdateRequest,
    ProductSuiteWithChildrenResponse,
)
from app.services import product_catalog_service

router = APIRouter(prefix="/platform", tags=["product-catalog"])


@router.get("/product-catalog", response_model=list[ProductSuiteWithChildrenResponse])
def get_product_catalog(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> list[ProductSuiteWithChildrenResponse]:
    suites = product_catalog_service.get_catalog_tree(db)
    return [ProductSuiteWithChildrenResponse.model_validate(s) for s in suites]


# --- Suites ------------------------------------------------------------


@router.get("/product-suites", response_model=list[ProductSuiteResponse])
def list_product_suites(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> list[ProductSuiteResponse]:
    suites = product_catalog_service.list_suites(db)
    return [ProductSuiteResponse.model_validate(s) for s in suites]


@router.post("/product-suites", response_model=ProductSuiteResponse, status_code=201)
def create_product_suite(
    payload: ProductSuiteCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> ProductSuiteResponse:
    suite = product_catalog_service.create_suite(
        db,
        actor_user_id=current_user.id,
        actor_organization_id=current_user.organization_id,
        code=payload.code,
        name=payload.name,
        description=payload.description,
        display_order=payload.display_order,
        is_active=payload.is_active,
    )
    return ProductSuiteResponse.model_validate(suite)


@router.get("/product-suites/{suite_id}", response_model=ProductSuiteResponse)
def get_product_suite(
    suite_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> ProductSuiteResponse:
    suite = product_catalog_service.get_suite(db, suite_id=suite_id)
    return ProductSuiteResponse.model_validate(suite)


@router.patch("/product-suites/{suite_id}", response_model=ProductSuiteResponse)
def update_product_suite(
    suite_id: uuid.UUID,
    payload: ProductSuiteUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> ProductSuiteResponse:
    suite = product_catalog_service.update_suite(
        db,
        actor_user_id=current_user.id,
        actor_organization_id=current_user.organization_id,
        suite_id=suite_id,
        name=payload.name,
        description=payload.description,
        display_order=payload.display_order,
        is_active=payload.is_active,
    )
    return ProductSuiteResponse.model_validate(suite)


# --- Modules -----------------------------------------------------------


@router.get("/product-modules", response_model=list[ProductModuleResponse])
def list_product_modules(
    suite_id: uuid.UUID | None = None,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> list[ProductModuleResponse]:
    modules = product_catalog_service.list_modules(db, suite_id=suite_id)
    return [ProductModuleResponse.model_validate(m) for m in modules]


@router.post("/product-modules", response_model=ProductModuleResponse, status_code=201)
def create_product_module(
    payload: ProductModuleCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> ProductModuleResponse:
    module = product_catalog_service.create_module(
        db,
        actor_user_id=current_user.id,
        actor_organization_id=current_user.organization_id,
        suite_id=payload.suite_id,
        code=payload.code,
        name=payload.name,
        description=payload.description,
        display_order=payload.display_order,
        is_active=payload.is_active,
    )
    return ProductModuleResponse.model_validate(module)


@router.get("/product-modules/{module_id}", response_model=ProductModuleWithChildrenResponse)
def get_product_module(
    module_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> ProductModuleWithChildrenResponse:
    module = product_catalog_service.get_module(db, module_id=module_id)
    return ProductModuleWithChildrenResponse.model_validate(module)


@router.patch("/product-modules/{module_id}", response_model=ProductModuleResponse)
def update_product_module(
    module_id: uuid.UUID,
    payload: ProductModuleUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> ProductModuleResponse:
    module = product_catalog_service.update_module(
        db,
        actor_user_id=current_user.id,
        actor_organization_id=current_user.organization_id,
        module_id=module_id,
        name=payload.name,
        description=payload.description,
        display_order=payload.display_order,
        is_active=payload.is_active,
    )
    return ProductModuleResponse.model_validate(module)


# --- Pages ---------------------------------------------------------------


@router.get("/product-pages", response_model=list[ProductPageResponse])
def list_product_pages(
    module_id: uuid.UUID | None = None,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> list[ProductPageResponse]:
    pages = product_catalog_service.list_pages(db, module_id=module_id)
    return [ProductPageResponse.model_validate(p) for p in pages]


@router.post("/product-pages", response_model=ProductPageResponse, status_code=201)
def create_product_page(
    payload: ProductPageCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> ProductPageResponse:
    page = product_catalog_service.create_page(
        db,
        actor_user_id=current_user.id,
        actor_organization_id=current_user.organization_id,
        module_id=payload.module_id,
        code=payload.code,
        name=payload.name,
        description=payload.description,
        route=payload.route,
        display_order=payload.display_order,
        is_active=payload.is_active,
    )
    return ProductPageResponse.model_validate(page)


@router.get("/product-pages/{page_id}", response_model=ProductPageResponse)
def get_product_page(
    page_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> ProductPageResponse:
    page = product_catalog_service.get_page(db, page_id=page_id)
    return ProductPageResponse.model_validate(page)


@router.patch("/product-pages/{page_id}", response_model=ProductPageResponse)
def update_product_page(
    page_id: uuid.UUID,
    payload: ProductPageUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> ProductPageResponse:
    page = product_catalog_service.update_page(
        db,
        actor_user_id=current_user.id,
        actor_organization_id=current_user.organization_id,
        page_id=page_id,
        name=payload.name,
        description=payload.description,
        route=payload.route,
        display_order=payload.display_order,
        is_active=payload.is_active,
    )
    return ProductPageResponse.model_validate(page)


# --- Features ----------------------------------------------------------


@router.get("/product-features", response_model=list[ProductFeatureResponse])
def list_product_features(
    module_id: uuid.UUID | None = None,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> list[ProductFeatureResponse]:
    features = product_catalog_service.list_features(db, module_id=module_id)
    return [ProductFeatureResponse.model_validate(f) for f in features]


@router.post("/product-features", response_model=ProductFeatureResponse, status_code=201)
def create_product_feature(
    payload: ProductFeatureCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> ProductFeatureResponse:
    feature = product_catalog_service.create_feature(
        db,
        actor_user_id=current_user.id,
        actor_organization_id=current_user.organization_id,
        module_id=payload.module_id,
        code=payload.code,
        name=payload.name,
        description=payload.description,
        is_active=payload.is_active,
    )
    return ProductFeatureResponse.model_validate(feature)


@router.get("/product-features/{feature_id}", response_model=ProductFeatureResponse)
def get_product_feature(
    feature_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> ProductFeatureResponse:
    feature = product_catalog_service.get_feature(db, feature_id=feature_id)
    return ProductFeatureResponse.model_validate(feature)


@router.patch("/product-features/{feature_id}", response_model=ProductFeatureResponse)
def update_product_feature(
    feature_id: uuid.UUID,
    payload: ProductFeatureUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> ProductFeatureResponse:
    feature = product_catalog_service.update_feature(
        db,
        actor_user_id=current_user.id,
        actor_organization_id=current_user.organization_id,
        feature_id=feature_id,
        name=payload.name,
        description=payload.description,
        is_active=payload.is_active,
    )
    return ProductFeatureResponse.model_validate(feature)
