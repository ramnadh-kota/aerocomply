"use client";

// Demo/Real data-mode.
// When an authenticated session is active:
// - DEMO session -> DEMO mode (synthetic data)
// - REAL session -> REAL mode (FastAPI backend)
// Real users cannot cross-switch into demo data; demo sessions cannot call real APIs.

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useSession } from "@/lib/auth/SessionContext";

export const DATA_MODE_STORAGE_KEY = "aerocomply-data-mode";

export type DataMode = "DEMO" | "REAL";

interface DataModeContextValue {
  mode: DataMode;
  setMode: (mode: DataMode) => void;
  isReal: boolean;
  /** The backend base URL REAL mode talks to — for display only. */
  apiBaseUrl: string;
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
  let sessionType: "REAL" | "DEMO" | null = null;
  try {
    // eslint-disable-next-line react-hooks/rules-of-hooks
    const session = useSession();
    sessionType = session.sessionType;
  } catch {
    // Standalone tests or unmounted SessionProvider
    sessionType = null;
  }

  const [storedMode, setStoredModeState] = useState<DataMode>("DEMO");
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setStoredModeState(loadStoredMode());
    setHydrated(true);
  }, []);

  const setMode = (next: DataMode) => {
    // If in an active session, lock mode to the session boundary
    if (sessionType === "REAL" && next !== "REAL") return;
    if (sessionType === "DEMO" && next !== "DEMO") return;
    setStoredModeState(next);
    try {
      window.localStorage.setItem(DATA_MODE_STORAGE_KEY, next);
    } catch {
      // best-effort persistence only
    }
  };

  const effectiveMode: DataMode = useMemo(() => {
    if (sessionType === "REAL") return "REAL";
    if (sessionType === "DEMO") return "DEMO";
    return storedMode;
  }, [sessionType, storedMode]);

  const value = useMemo<DataModeContextValue>(
    () => ({
      mode: effectiveMode,
      setMode,
      isReal: effectiveMode === "REAL",
      apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1",
      hydrated,
    }),
    [effectiveMode, hydrated]
  );

  return <DataModeContext.Provider value={value}>{children}</DataModeContext.Provider>;
}

export function useDataMode(): DataModeContextValue {
  const ctx = useContext(DataModeContext);
  if (!ctx) throw new Error("useDataMode must be used within DataModeProvider");
  return ctx;
}
