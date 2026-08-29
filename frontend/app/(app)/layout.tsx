import type { ReactNode } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { AviationBackground } from "@/components/layout/AviationBackground";
import { MroStateProvider } from "@/lib/mro-state/MroStateContext";
// DIAGNOSTIC (temporary): RoleSimProvider wrapping removed to isolate whether
// the Role Simulation layer is responsible for the /organization/roles
// static-generation timeout. See diagnostic commit "isolate role simulation
// build timeout". Not a permanent change — do not build on top of this.

export default function AppShellLayout({ children }: { children: ReactNode }) {
  return (
    <MroStateProvider>
      <AviationBackground />
      <div className="ac-shell">
        <a href="#ac-main-content" className="ac-skip-link">
          Skip to main content
        </a>
        <Sidebar />
        <div className="ac-main">
          <Topbar />
          <main id="ac-main-content" className="ac-content">
            {children}
          </main>
        </div>
      </div>
    </MroStateProvider>
  );
}
