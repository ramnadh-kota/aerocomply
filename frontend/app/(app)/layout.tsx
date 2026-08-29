import type { ReactNode } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { AviationBackground } from "@/components/layout/AviationBackground";

export default function AppShellLayout({ children }: { children: ReactNode }) {
  return (
    <>
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
    </>
  );
}
