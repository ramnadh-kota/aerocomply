"use client";

// Demo/Real data-mode switch. DEMO (default) is the existing, unchanged
// client-side mock-data experience the rest of this prototype was built on.
// REAL calls the actual FastAPI backend (see frontend/lib/apiClient.ts and
// frontend/lib/api/*) running locally on NEXT_PUBLIC_API_BASE_URL.
//
// Persisted to this browser's localStorage only, exactly like the alert
// state / welcome-tour "seen" flag patterns elsewhere in this app — never
// synced to a backend or another device.

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export const DATA_MODE_STORAGE_KEY = "aerocomply-data-mode";

export type DataMode = "DEMO" | "REAL";

interface DataModeContextValue {
  mode: DataMode;
  setMode: (mode: DataMode) => void;
  isReal: boolean;
  /** The backend base URL REAL mode talks to — for display only. */
  apiBaseUrl: string;
  /**
   * True once the persisted mode has been read from localStorage. Pages that
   * call notFound() on a mock-data miss (e.g. [id] detail routes) must wait
   * for this before evaluating DEMO-branch lookups — otherwise a REAL-only id
   * on first paint (mode still defaulted to DEMO) trips notFound()
   * irrecoverably, since Next's not-found boundary doesn't un-throw when
   * mode flips a moment later.
   */
  hydrated: boolean;
}

const DataModeContext = createContext<DataModeContextValue | null>(null);

function loadStoredMode(): DataMode {
  try {
    const raw = window.localStorage.getItem(DATA_MODE_STORAGE_KEY);
    return raw === "REAL" ? "REAL" : "DEMO";
  } catch {
    return "DEMO";
  }
}

export function DataModeProvider({ children }: { children: ReactNode }) {
  // Default DEMO on both server and first client render to avoid a
  // hydration mismatch; the persisted choice (if any) is applied right
  // after mount, client-only.
  const [mode, setModeState] = useState<DataMode>("DEMO");
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setModeState(loadStoredMode());
    setHydrated(true);
  }, []);

  const setMode = (next: DataMode) => {
    setModeState(next);
    try {
      window.localStorage.setItem(DATA_MODE_STORAGE_KEY, next);
    } catch {
      // best-effort persistence only
    }
  };

  const value = useMemo<DataModeContextValue>(
    () => ({
      mode,
      setMode,
      isReal: mode === "REAL",
      apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1",
      hydrated,
    }),
    [mode, hydrated]
  );

  return <DataModeContext.Provider value={value}>{children}</DataModeContext.Provider>;
}

export function useDataMode(): DataModeContextValue {
  const ctx = useContext(DataModeContext);
  if (!ctx) throw new Error("useDataMode must be used within DataModeProvider");
  return ctx;
}
