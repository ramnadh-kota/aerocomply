import type { ReactNode } from "react";
import { SuiteGuard } from "@/components/auth/SuiteGuard";

export const metadata = {
  title: "Commercial Aircraft — Kota Aerospace",
  description: "Commercial aircraft fleet airworthiness, CAMO, MRO work orders, and inspections.",
};

export default function AircraftGroupLayout({ children }: { children: ReactNode }) {
  return (
    <SuiteGuard requiredSuite="AIRCRAFT">
      {children}
    </SuiteGuard>
  );
}
