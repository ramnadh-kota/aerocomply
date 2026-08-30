import type { ReactNode } from "react";
import "./globals.css";
import { PLATFORM_NAME, PLATFORM_TAGLINE } from "@/lib/brand";

export const metadata = {
  title: PLATFORM_NAME,
  description: PLATFORM_TAGLINE,
};

// Applies the persisted theme before first paint, so there is no
// light-then-dark (or dark-then-light) flash on load. Reads localStorage
// only — falls back to light (the product default) if unavailable/unset.
const THEME_BOOTSTRAP_SCRIPT = `
(function () {
  try {
    var t = localStorage.getItem("aerocomply-theme");
    if (t === "dark") document.documentElement.setAttribute("data-theme", "dark");
  } catch (e) {}
})();
`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP_SCRIPT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
