import type { ReactNode } from "react";
import { SuiteGuard } from "@/components/auth/SuiteGuard";

export const metadata = {
  title: "Drone Fleet Registry — Kota Aerospace",
  description: "UAS drone fleet registration, battery analytics, and operational readiness.",
};

export default function DronesGroupLayout({ children }: { children: ReactNode }) {
  return (
    <SuiteGuard requiredSuite="DRONE_UAV">
      {children}
    </SuiteGuard>
  );
}
