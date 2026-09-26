"use client";

// Reactive, session-scoped synthetic Demo Store for KOTA Aerospace Demo Operations.
// Exclusively used during DEMO sessions (DEMO_ORG_ID). Never contacts live backend APIs.
// Mutations persist across route changes in sessionStorage during the demo session.

import { DEMO_ASSETS } from "@/lib/demo/demoAssets";
import { DEMO_DRONES } from "@/lib/demo/demoDrones";
import {
  DEMO_TENANT_INVITATIONS,
  DEMO_TENANT_DASHBOARD_STATS,
  DEMO_TENANT_PROFILE,
  DEMO_TENANT_SETTINGS,
} from "@/lib/demo/demoTenant";
import type { AssetResponse, AssetCreateRequest } from "@/lib/api/assets";
import type { DroneResponse, DroneCreateRequest } from "@/lib/api/drones";
import type { TenantInvitation, TenantDashboardStats } from "@/lib/api/tenant";
import type { CurrentUser } from "@/lib/apiClient";
import { DEMO_ORG_ID } from "@/lib/auth/SessionContext";

const DEMO_STORE_KEY = "aerocomply_demo_store_v1";

interface DemoStoreState {
  assets: AssetResponse[];
  drones: DroneResponse[];
  invitations: TenantInvitation[];
  profile?: Partial<CurrentUser>;
}

let inMemoryState: DemoStoreState | null = null;
const listeners = new Set<() => void>();

function notifyListeners() {
  listeners.forEach((listener) => {
    try {
      listener();
    } catch {
      // ignore
    }
  });
}

function loadInitialState(): DemoStoreState {
  if (typeof window !== "undefined") {
    try {
      const raw = window.sessionStorage.getItem(DEMO_STORE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed.assets) && Array.isArray(parsed.invitations)) {
          return parsed;
        }
      }
    } catch {
      // fallback
    }
  }
  return {
    assets: [...DEMO_ASSETS],
    drones: [...DEMO_DRONES],
    invitations: [...DEMO_TENANT_INVITATIONS],
  };
}

function getState(): DemoStoreState {
  if (!inMemoryState) {
    inMemoryState = loadInitialState();
  }
  return inMemoryState;
}

function saveState(state: DemoStoreState) {
  inMemoryState = state;
  if (typeof window !== "undefined") {
    try {
      window.sessionStorage.setItem(DEMO_STORE_KEY, JSON.stringify(state));
    } catch {
      // best-effort
    }
  }
  notifyListeners();
}

export const demoStore = {
  subscribe(callback: () => void): () => void {
    listeners.add(callback);
    return () => listeners.delete(callback);
  },

  // ---------------------------------------------------------------------------
  // Assets
  // ---------------------------------------------------------------------------
  getAssets(): AssetResponse[] {
    return getState().assets;
  },

  getAssetById(id: string): AssetResponse | null {
    return getState().assets.find((a) => a.id === id) || null;
  },

  addAsset(req: AssetCreateRequest): AssetResponse {
    const state = getState();
    const id = `demo-asset-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
    const newAsset: AssetResponse = {
      id,
      organization_id: DEMO_ORG_ID,
      asset_type: req.asset_type.toUpperCase(),
      registration: req.registration.trim().toUpperCase(),
      manufacturer: req.manufacturer?.trim() || null,
      model: req.model?.trim() || null,
      serial_number: req.serial_number?.trim() || `SN-${id.slice(-6).toUpperCase()}`,
      status: req.status || "ACTIVE",
      facility_id: req.facility_id || null,
      acquired_at: new Date().toISOString(),
      retired_at: null,
      created_at: new Date().toISOString(),
    };

    const updatedAssets = [newAsset, ...state.assets];
    let updatedDrones = state.drones;

    // If drone, also reflect in drone collection
    if (newAsset.asset_type === "DRONE") {
      const newDrone: DroneResponse = {
        id: newAsset.id,
        organization_id: DEMO_ORG_ID,
        asset_type: "DRONE",
        registration: newAsset.registration,
        manufacturer: newAsset.manufacturer,
        model: newAsset.model,
        serial_number: newAsset.serial_number,
        status: newAsset.status,
        facility_id: newAsset.facility_id ?? null,
        created_at: newAsset.created_at,
      };
      updatedDrones = [newDrone, ...state.drones];
    }

    saveState({
      ...state,
      assets: updatedAssets,
      drones: updatedDrones,
    });

    return newAsset;
  },

  updateAsset(id: string, updates: Partial<AssetResponse>): AssetResponse | null {
    const state = getState();
    let updatedAsset: AssetResponse | null = null;
    const updatedAssets = state.assets.map((a) => {
      if (a.id === id) {
        updatedAsset = { ...a, ...updates };
        return updatedAsset;
      }
      return a;
    });

    if (updatedAsset) {
      saveState({
        ...state,
        assets: updatedAssets,
      });
    }
    return updatedAsset;
  },

  // ---------------------------------------------------------------------------
  // Drones
  // ---------------------------------------------------------------------------
  getDrones(): DroneResponse[] {
    return getState().drones;
  },

  addDrone(req: DroneCreateRequest): DroneResponse {
    const state = getState();
    const id = `demo-drn-${Date.now().toString(36)}`;
    const newDrone: DroneResponse = {
      id,
      organization_id: DEMO_ORG_ID,
      asset_type: "DRONE",
      registration: req.registration.trim().toUpperCase(),
      manufacturer: req.manufacturer?.trim() || null,
      model: req.model?.trim() || null,
      serial_number: req.serial_number?.trim() || null,
      status: "ACTIVE",
      facility_id: req.facility_id || null,
      created_at: new Date().toISOString(),
    };

    const newAsset: AssetResponse = {
      id,
      organization_id: DEMO_ORG_ID,
      asset_type: "DRONE",
      registration: newDrone.registration,
      manufacturer: newDrone.manufacturer,
      model: newDrone.model,
      serial_number: newDrone.serial_number,
      status: newDrone.status,
      facility_id: newDrone.facility_id,
      acquired_at: newDrone.created_at,
      retired_at: null,
      created_at: newDrone.created_at,
    };

    saveState({
      ...state,
      drones: [newDrone, ...state.drones],
      assets: [newAsset, ...state.assets],
    });

    return newDrone;
  },

  // ---------------------------------------------------------------------------
  // Invitations
  // ---------------------------------------------------------------------------
  getInvitations(): TenantInvitation[] {
    return getState().invitations;
  },

  addInvitation(data: { email: string; full_name?: string; role?: string; role_id?: string; role_name?: string }): TenantInvitation {
    const state = getState();
    const id = `demo-inv-${Date.now().toString(36)}`;
    const email = data.email.trim().toLowerCase();
    const fullName = data.full_name?.trim() || email.split("@")[0] || "Demo User";
    const role = data.role || data.role_name || "FLEET_OPERATOR";
    const newInv: TenantInvitation = {
      id,
      user_id: `demo-usr-${Date.now().toString(36)}`,
      email,
      full_name: fullName,
      role,
      status: "PENDING",
      created_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
      can_resend: true,
      can_cancel: true,
    };

    saveState({
      ...state,
      invitations: [newInv, ...state.invitations],
    });

    return newInv;
  },

  cancelInvitation(id: string): boolean {
    const state = getState();
    const updated = state.invitations.map((inv) =>
      inv.id === id ? { ...inv, status: "CANCELLED" as const, can_cancel: false, can_resend: false } : inv
    );
    saveState({ ...state, invitations: updated });
    return true;
  },

  resendInvitation(id: string): boolean {
    const state = getState();
    const updated = state.invitations.map((inv) =>
      inv.id === id
        ? {
            ...inv,
            expires_at: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
          }
        : inv
    );
    saveState({ ...state, invitations: updated });
    return true;
  },

  // ---------------------------------------------------------------------------
  // Dynamic Dashboard Stats
  // ---------------------------------------------------------------------------
  getDashboardStats(): TenantDashboardStats {
    const state = getState();
    const aircraftCount = state.assets.filter((a) => a.asset_type === "AIRCRAFT").length;
    const droneCount = state.assets.filter((a) => a.asset_type === "DRONE").length;
    const pendingInvCount = state.invitations.filter((i) => i.status === "PENDING").length;

    return {
      ...DEMO_TENANT_DASHBOARD_STATS,
      fleet_count: state.assets.length,
      aircraft_count: aircraftCount,
      drone_count: droneCount,
      pending_invitations_count: pendingInvCount,
    };
  },

  // ---------------------------------------------------------------------------
  // Profile (Demo Interactive Mode)
  // ---------------------------------------------------------------------------
  getProfile(): Partial<CurrentUser> | null {
    return getState().profile || null;
  },

  updateProfile(updates: Partial<CurrentUser>): void {
    const state = getState();
    const current = state.profile || {};
    saveState({
      ...state,
      profile: {
        ...current,
        ...updates,
      },
    });
  },

  reset(): void {
    if (typeof window !== "undefined") {
      try {
        window.sessionStorage.removeItem(DEMO_STORE_KEY);
      } catch {
        // ignore
      }
    }
    inMemoryState = {
      assets: [...DEMO_ASSETS],
      drones: [...DEMO_DRONES],
      invitations: [...DEMO_TENANT_INVITATIONS],
    };
    notifyListeners();
  },
};

if (typeof globalThis !== "undefined") {
  (globalThis as any).__aerocomply_demo_get_asset__ = (id: string) => demoStore.getAssetById(id);
}
