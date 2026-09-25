"use client";

import { useState, type CSSProperties, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { authApi, normalizeApiError } from "@/lib/apiClient";
import { useSession } from "@/lib/auth/SessionContext";
import { useDataMode } from "@/lib/data-mode/DataModeContext";
import { Logo } from "@/components/branding/Logo";

export default function LoginPage() {
  const router = useRouter();
  const { login } = useSession();
  const { setMode } = useDataMode();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const tokens = await authApi.login(email, password);
      const me = await login(tokens);
      setMode("REAL");
      const isPlatformUser =
        me.roles?.some((r) => r === "PLATFORM_ADMIN" || r === "PLATFORM_STAFF") ?? false;
      router.push(isPlatformUser ? "/platform/organizations" : "/dashboard");
    } catch (err) {
      setError(normalizeApiError(err).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main
      style={{
        display: "flex",
        minHeight: "100vh",
        alignItems: "center",
        justifyContent: "center",
        flexDirection: "column",
        gap: 20,
        padding: 24,
      }}
    >
      <Logo height={48} />
      <div
        className="ac-card"
        style={{
          width: 380,
          padding: 32,
        }}
      >
        <h2 style={{ marginTop: 0 }}>Sign in</h2>

        <form onSubmit={handleSubmit}>
          <label style={{ display: "block", marginBottom: 12 }}>
            <span style={{ display: "block", marginBottom: 4, fontSize: 13, opacity: 0.8 }}>Email</span>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={inputStyle}
              placeholder="name@company.com"
            />
          </label>

          <label style={{ display: "block", marginBottom: 16 }}>
            <span style={{ display: "block", marginBottom: 4, fontSize: 13, opacity: 0.8 }}>Password</span>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={inputStyle}
            />
          </label>

          <p style={{ margin: "0 0 16px", fontSize: 13 }}>
            <Link href="/forgot-password">Forgot password?</Link>
          </p>

          {error && (
            <p
              role="alert"
              style={{ color: "var(--ac-status-non-compliant)", fontSize: 13, marginBottom: 12 }}
            >
              {error}
            </p>
          )}

          <button type="submit" disabled={loading} style={buttonStyle}>
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </main>
  );
}

const inputStyle: CSSProperties = {
  width: "100%",
  padding: "10px 12px",
  borderRadius: "var(--ac-radius-md)",
  border: "1px solid var(--ac-border)",
  background: "var(--ac-bg)",
  color: "var(--ac-text-primary)",
  boxSizing: "border-box",
};

const buttonStyle: CSSProperties = {
  width: "100%",
  padding: "10px 12px",
  borderRadius: "var(--ac-radius-md)",
  border: "none",
  background: "var(--ac-accent)",
  color: "white",
  fontWeight: 600,
  cursor: "pointer",
};
