import type { ReactNode } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { AviationBackground } from "@/components/layout/AviationBackground";
import { MroStateProvider } from "@/lib/mro-state/MroStateContext";
import { RoleSimProvider } from "@/lib/role-sim/RoleSimContext";
import { SidebarDrawerProvider } from "@/components/layout/SidebarDrawerContext";
import { WelcomeTour } from "@/components/onboarding/WelcomeTour";
import { AlertStateProvider } from "@/lib/mock/ai/alertState";
import { AuthGuard } from "@/components/auth/AuthGuard";
import { RouteEntitlementGuard } from "@/components/auth/RouteEntitlementGuard";
import { EntitlementProvider } from "@/lib/entitlements/EntitlementContext";

// DataModeProvider/SessionProvider are mounted at the root layout (app/layout.tsx)
// so both the (app) shell and the standalone /login page share one session.

export default function AppShellLayout({ children }: { children: ReactNode }) {
  return (
    <AuthGuard>
      <EntitlementProvider>
        <MroStateProvider>
        <RoleSimProvider>
          <AlertStateProvider>
            <SidebarDrawerProvider>
              <AviationBackground />
              <div className="ac-shell">
                <a href="#ac-main-content" className="ac-skip-link">
                  Skip to main content
                </a>
                <Sidebar />
                <div className="ac-main">
                  <Topbar />
                  <main id="ac-main-content" className="ac-content">
                    <RouteEntitlementGuard>{children}</RouteEntitlementGuard>
                  </main>
                </div>
              </div>
              <WelcomeTour />
            </SidebarDrawerProvider>
          </AlertStateProvider>
        </RoleSimProvider>
      </MroStateProvider>
    </EntitlementProvider>
  </AuthGuard>
  );
}
