import Link from "next/link";

export default function HomePage() {
  return (
    <main style={{ display: "flex", height: "100vh", alignItems: "center", justifyContent: "center" }}>
      <div style={{ textAlign: "center" }}>
        <h1>AeroComply</h1>
        <p style={{ opacity: 0.7 }}>Aviation compliance intelligence platform</p>
        <Link href="/login" style={{ color: "#4da3ff" }}>
          Go to login
        </Link>
      </div>
    </main>
  );
}
