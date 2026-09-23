"use client";

import { useState, type CSSProperties, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { authApi, normalizeApiError } from "@/lib/apiClient";
import {
  useSession,
  DEMO_USER_EMAIL,
  DEMO_USER_PASSWORD,
  DEMO_ORG_NAME,
} from "@/lib/auth/SessionContext";
import { useDataMode } from "@/lib/data-mode/DataModeContext";
import { Logo } from "@/components/branding/Logo";

export default function LoginPage() {
  const router = useRouter();
  const { login, loginWithDemo } = useSession();
  const { setMode } = useDataMode();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleRealOrDemoSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    const trimmedEmail = email.trim().toLowerCase();
    // Intercept exact demo credentials BEFORE calling the real backend auth API
    if (trimmedEmail === DEMO_USER_EMAIL.toLowerCase() && password === DEMO_USER_PASSWORD) {
      try {
        loginWithDemo();
        setMode("DEMO");
        router.push("/dashboard");
        return;
      } finally {
        setLoading(false);
      }
    }

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

  function handleDirectDemoEntry() {
    loginWithDemo();
    setMode("DEMO");
    router.push("/dashboard");
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

        <form onSubmit={handleRealOrDemoSubmit}>
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

        <div
          style={{
            margin: "24px 0 20px",
            borderTop: "1px solid var(--ac-border)",
            position: "relative",
            textAlign: "center",
          }}
        >
          <span
            style={{
              position: "relative",
              top: -10,
              background: "var(--ac-card-bg, #fff)",
              padding: "0 8px",
              fontSize: 11,
              color: "var(--ac-text-muted)",
              textTransform: "uppercase",
              letterSpacing: 0.5,
            }}
          >
            or demo access
          </span>
        </div>

        <div
          style={{
            padding: 16,
            borderRadius: "var(--ac-radius-md)",
            border: "1px dashed var(--ac-border)",
            background: "var(--ac-bg)",
            textAlign: "center",
          }}
        >
          <div
            style={{
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: 0.5,
              textTransform: "uppercase",
              color: "var(--ac-accent)",
              marginBottom: 4,
            }}
          >
            DEMO ENVIRONMENT · SYNTHETIC DATA
          </div>
          <p style={{ margin: "0 0 8px", fontSize: 12, color: "var(--ac-text-muted)" }}>
            {DEMO_ORG_NAME}
          </p>
          <p style={{ margin: "0 0 12px", fontSize: 11, color: "var(--ac-text-muted)", fontFamily: "monospace" }}>
            {DEMO_USER_EMAIL} / {DEMO_USER_PASSWORD}
          </p>
          <button
            type="button"
            onClick={handleDirectDemoEntry}
            style={demoButtonStyle}
          >
            Enter Demo Environment →
          </button>
        </div>
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

const demoButtonStyle: CSSProperties = {
  width: "100%",
  padding: "8px 12px",
  borderRadius: "var(--ac-radius-md)",
  border: "1px solid var(--ac-accent)",
  background: "transparent",
  color: "var(--ac-accent)",
  fontWeight: 600,
  fontSize: 13,
  cursor: "pointer",
};
