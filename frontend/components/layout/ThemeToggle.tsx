"use client";

import { useEffect, useState } from "react";

const STORAGE_KEY = "aerocomply-theme";

/** Light/dark theme toggle. Deliberately NOT a React context — this is a
 * single UI preference read/written straight to the DOM + localStorage, not
 * domain state, so it doesn't warrant (or belong in) a new state-management
 * system alongside MroStateContext/RoleSimContext. See the bootstrap script
 * in app/layout.tsx for how the initial theme is applied before paint. */
export function ThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark">("light");

  useEffect(() => {
    setTheme((document.documentElement.getAttribute("data-theme") as "dark") === "dark" ? "dark" : "light");
  }, []);

  function toggle() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // localStorage unavailable (private mode, etc.) — theme still applies for this page view.
    }
  }

  return (
    <button className="ac-btn" onClick={toggle} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`} title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`} style={{ padding: "8px 10px" }}>
      <span aria-hidden="true">{theme === "dark" ? "☀" : "☾"}</span>
    </button>
  );
}
