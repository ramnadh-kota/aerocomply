import type { ReactNode } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { AviationBackground } from "@/components/layout/AviationBackground";
import { MroStateProvider } from "@/lib/mro-state/MroStateContext";
import { RoleSimProvider } from "@/lib/role-sim/RoleSimContext";
import { SidebarDrawerProvider } from "@/components/layout/SidebarDrawerContext";
import { WelcomeTour } from "@/components/onboarding/WelcomeTour";

export default function AppShellLayout({ children }: { children: ReactNode }) {
  return (
    <MroStateProvider>
      <RoleSimProvider>
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
                {children}
              </main>
            </div>
          </div>
          <WelcomeTour />
        </SidebarDrawerProvider>
      </RoleSimProvider>
    </MroStateProvider>
  );
}
