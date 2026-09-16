// Phase 18.2: typed REAL-mode client for platform product catalog
// administration (backend/app/api/v1/product_catalog.py). Requires
// PLATFORM_MANAGE on the backend — a non-platform-admin user calling these
// gets a 403 regardless of what the frontend shows. This client is
// intentionally thin, following lib/api/plan.ts's exact pattern: it only
// maps HTTP requests/responses to typed shapes. All validation/audit/
// transaction behavior lives in app.services.product_catalog_service.

import { apiRequest } from "@/lib/apiClient";

export interface ProductSuiteResponse {
  id: string;
  code: string;
  name: string;
  description: string | null;
  display_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProductModuleResponse {
  id: string;
  suite_id: string;
  code: string;
  name: string;
  description: string | null;
  display_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProductPageResponse {
  id: string;
  module_id: string;
  code: string;
  name: string;
  description: string | null;
  route: string | null;
  display_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProductFeatureResponse {
  id: string;
  module_id: string;
  code: string;
  name: string;
  description: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProductModuleWithChildrenResponse extends ProductModuleResponse {
  pages: ProductPageResponse[];
  features: ProductFeatureResponse[];
}

export interface ProductSuiteWithChildrenResponse extends ProductSuiteResponse {
  modules: ProductModuleWithChildrenResponse[];
}

export interface ProductSuiteCreateRequest {
  code: string;
  name: string;
  description?: string | null;
  display_order?: number;
  is_active?: boolean;
}

export interface ProductModuleCreateRequest {
  suite_id: string;
  code: string;
  name: string;
  description?: string | null;
  display_order?: number;
  is_active?: boolean;
}

export interface ProductPageCreateRequest {
  module_id: string;
  code: string;
  name: string;
  description?: string | null;
  route?: string | null;
  display_order?: number;
  is_active?: boolean;
}

export interface ProductFeatureCreateRequest {
  module_id: string;
  code: string;
  name: string;
  description?: string | null;
  is_active?: boolean;
}

export const productCatalogApi = {
  getCatalogTree: (accessToken: string) =>
    apiRequest<ProductSuiteWithChildrenResponse[]>("/platform/product-catalog", { accessToken }),

  listSuites: (accessToken: string) =>
    apiRequest<ProductSuiteResponse[]>("/platform/product-suites", { accessToken }),

  createSuite: (accessToken: string, payload: ProductSuiteCreateRequest) =>
    apiRequest<ProductSuiteResponse>("/platform/product-suites", { method: "POST", body: payload, accessToken }),

  createModule: (accessToken: string, payload: ProductModuleCreateRequest) =>
    apiRequest<ProductModuleResponse>("/platform/product-modules", { method: "POST", body: payload, accessToken }),

  createPage: (accessToken: string, payload: ProductPageCreateRequest) =>
    apiRequest<ProductPageResponse>("/platform/product-pages", { method: "POST", body: payload, accessToken }),

  createFeature: (accessToken: string, payload: ProductFeatureCreateRequest) =>
    apiRequest<ProductFeatureResponse>("/platform/product-features", {
      method: "POST",
      body: payload,
      accessToken,
    }),
};
