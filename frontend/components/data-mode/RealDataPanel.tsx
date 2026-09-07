"use client";

// Shared loading/empty/error chrome for REAL-mode data fetches, kept
// consistent across Aircraft/Work Orders/Tasks REAL-mode panels. DEMO mode
// never renders this — it's purely additive to the existing mock UI.

import type { ReactNode } from "react";
import { StatusBadge } from "@/components/status/StatusBadge";
import Link from "next/link";
import type { ApiErrorKind } from "@/lib/apiClient";

export function RealDataPanel({
  loading,
  error,
  isEmpty,
  emptyMessage,
  children,
}: {
  loading: boolean;
  error: { kind: ApiErrorKind; message: string } | null;
  isEmpty: boolean;
  emptyMessage: string;
  children: ReactNode;
}) {
  if (loading) {
    return (
      <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
        <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Loading from the connected backend…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
        <div className="ac-flex ac-gap-2" style={{ alignItems: "center", marginBottom: 6 }}>
          <StatusBadge status="NON_COMPLIANT" label={error.kind === "unauthorized" ? "Session Expired" : "Request Failed"} />
        </div>
        <p className="ac-text-sm" style={{ margin: 0 }}>{error.message}</p>
        {error.kind === "unauthorized" && (
          <p className="ac-text-sm ac-text-muted" style={{ margin: "6px 0 0" }}>
            <Link href="/login">Sign in again →</Link>
          </p>
        )}
      </div>
    );
  }

  if (isEmpty) {
    return (
      <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
        <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>{emptyMessage}</p>
      </div>
    );
  }

  return <>{children}</>;
}
