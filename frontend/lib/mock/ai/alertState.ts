"use client";

// Lightweight, client-only acknowledge/resolve tracking for proactive alerts
// (lib/mock/ai/proactive.ts). Alerts are NOT stored objects — they are
// recomputed fresh from live mock data on every render (see
// getProactiveAlerts()) — so this only ever stores a status keyed by
// `alert.id`. If the underlying condition still exists, the same id is
// regenerated and this context re-attaches its acknowledged/resolved
// status to it; if the condition resolves, the alert simply stops being
// generated and its stored status becomes inert (harmless, never cleaned
// up — there's no backend to reconcile against).
//
// DEMO/LOCAL STATE ONLY: persisted to this browser's localStorage, exactly
// like the "seen" flag in components/onboarding/WelcomeTour.tsx. It is
// never synced to a backend, another device, or another user.

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { createElement } from "react";

export const ALERT_STATE_STORAGE_KEY = "kota-aerospace-alert-state";

export type AlertStatus = "OPEN" | "ACKNOWLEDGED" | "RESOLVED";

interface AlertStateMap {
  [alertId: string]: AlertStatus;
}

interface AlertStateContextValue {
  /** Status for one alert id — defaults to "OPEN" if never touched. */
  statusFor: (alertId: string) => AlertStatus;
  acknowledge: (alertId: string) => void;
  resolve: (alertId: string) => void;
  /** Return an acknowledged/resolved alert back to OPEN. */
  reopen: (alertId: string) => void;
}

const AlertStateContext = createContext<AlertStateContextValue | null>(null);

function loadStoredState(): AlertStateMap {
  try {
    const raw = window.localStorage.getItem(ALERT_STATE_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    if (parsed && typeof parsed === "object") return parsed as AlertStateMap;
    return {};
  } catch {
    // localStorage unavailable (private mode, etc.) or corrupt JSON —
    // fall back to an empty map rather than throwing.
    return {};
  }
}

export function AlertStateProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AlertStateMap>({});

  // Load persisted state once on mount (client-only — avoids SSR/client
  // markup mismatch since localStorage doesn't exist on the server).
  useEffect(() => {
    setState(loadStoredState());
  }, []);

  const setStatus = useCallback(
    (alertId: string, status: AlertStatus) => {
      setState((prev) => {
        const next = { ...prev, [alertId]: status };
        try {
          window.localStorage.setItem(ALERT_STATE_STORAGE_KEY, JSON.stringify(next));
        } catch {
          // best-effort persistence only
        }
        return next;
      });
    },
    []
  );

  const value = useMemo<AlertStateContextValue>(
    () => ({
      statusFor: (alertId: string) => state[alertId] ?? "OPEN",
      acknowledge: (alertId: string) => setStatus(alertId, "ACKNOWLEDGED"),
      resolve: (alertId: string) => setStatus(alertId, "RESOLVED"),
      reopen: (alertId: string) => setStatus(alertId, "OPEN"),
    }),
    [state, setStatus]
  );

  return createElement(AlertStateContext.Provider, { value }, children);
}

export function useAlertState(): AlertStateContextValue {
  const ctx = useContext(AlertStateContext);
  if (!ctx) throw new Error("useAlertState must be used within AlertStateProvider");
  return ctx;
}
