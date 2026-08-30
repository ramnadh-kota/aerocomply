import Link from "next/link";
import { PLATFORM_NAME, PLATFORM_TAGLINE } from "@/lib/brand";

export default function HomePage() {
  return (
    <main style={{ display: "flex", height: "100vh", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 16 }}>
      <div style={{ textAlign: "center" }}>
        <h1 style={{ marginBottom: 4 }}>{PLATFORM_NAME}</h1>
        <p style={{ opacity: 0.7, marginTop: 0 }}>{PLATFORM_TAGLINE}</p>
      </div>
      <div style={{ display: "flex", gap: 12 }}>
        <Link href="/dashboard" className="ac-btn ac-btn-primary">
          Enter M0.5 Prototype
        </Link>
        <Link href="/login" className="ac-btn">
          Sign in
        </Link>
      </div>
      <p className="ac-text-sm ac-text-muted" style={{ maxWidth: 420, textAlign: "center" }}>
        The prototype uses fictional demo data and is not connected to the real backend. See the
        environment indicator in the sidebar.
      </p>
    </main>
  );
}
