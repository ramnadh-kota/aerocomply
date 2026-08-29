import type { ReactNode } from "react";

export const metadata = {
  title: "AeroComply",
  description: "Aviation compliance intelligence platform",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: "system-ui, sans-serif", background: "#0b1220", color: "#e6ebf2" }}>
        {children}
      </body>
    </html>
  );
}
