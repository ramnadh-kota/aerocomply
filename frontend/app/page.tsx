import Link from "next/link";

export default function HomePage() {
  return (
    <main style={{ display: "flex", height: "100vh", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 16 }}>
      <div style={{ textAlign: "center" }}>
        <h1 style={{ marginBottom: 4 }}>AeroComply</h1>
        <p style={{ opacity: 0.7, marginTop: 0 }}>Aviation regulatory compliance intelligence platform</p>
      </div>
      <div style={{ display: "flex", gap: 12 }}>
        <Link href="/dashboard" className="ac-btn ac-btn-primary">
          Enter Prototype (Mock Data)
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
