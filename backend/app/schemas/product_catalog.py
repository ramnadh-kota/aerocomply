"""Phase 18.2: request/response schemas for the platform product catalog.

Mirrors the style of app/schemas/plan.py -- pure serialization/validation
shapes, no business logic. ORM objects are never returned directly.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ProductSuiteCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    display_order: int = 0
    is_active: bool = True


class ProductSuiteUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    display_order: int | None = None
    is_active: bool | None = None


class ProductSuiteResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    display_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProductModuleCreateRequest(BaseModel):
    suite_id: uuid.UUID
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    display_order: int = 0
    is_active: bool = True


class ProductModuleUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    display_order: int | None = None
    is_active: bool | None = None


class ProductModuleResponse(BaseModel):
    id: uuid.UUID
    suite_id: uuid.UUID
    code: str
    name: str
    description: str | None
    display_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProductPageCreateRequest(BaseModel):
    module_id: uuid.UUID
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    route: str | None = Field(default=None, max_length=255)
    display_order: int = 0
    is_active: bool = True


class ProductPageUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    route: str | None = Field(default=None, max_length=255)
    display_order: int | None = None
    is_active: bool | None = None


class ProductPageResponse(BaseModel):
    id: uuid.UUID
    module_id: uuid.UUID
    code: str
    name: str
    description: str | None
    route: str | None
    display_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProductFeatureCreateRequest(BaseModel):
    module_id: uuid.UUID
    code: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    is_active: bool = True


class ProductFeatureUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    is_active: bool | None = None


class ProductFeatureResponse(BaseModel):
    id: uuid.UUID
    module_id: uuid.UUID
    code: str
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProductModuleWithChildrenResponse(ProductModuleResponse):
    pages: list[ProductPageResponse] = []
    features: list[ProductFeatureResponse] = []


class ProductSuiteWithChildrenResponse(ProductSuiteResponse):
    modules: list[ProductModuleWithChildrenResponse] = []
