"use client";

// Ephemeral UI-only state (mobile sidebar open/closed) — not a data store.
// Mirrors the existing pattern of small, page-agnostic client contexts like
// RoleSimContext, scoped to a single UI concern with no business logic.

import { createContext, useContext, useState, type ReactNode } from "react";

interface SidebarDrawerValue {
  open: boolean;
  toggle: () => void;
  close: () => void;
}

const SidebarDrawerContext = createContext<SidebarDrawerValue | null>(null);

export function SidebarDrawerProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <SidebarDrawerContext.Provider value={{ open, toggle: () => setOpen((v) => !v), close: () => setOpen(false) }}>
      {children}
    </SidebarDrawerContext.Provider>
  );
}

export function useSidebarDrawer(): SidebarDrawerValue {
  const ctx = useContext(SidebarDrawerContext);
  if (!ctx) throw new Error("useSidebarDrawer must be used within SidebarDrawerProvider");
  return ctx;
}
