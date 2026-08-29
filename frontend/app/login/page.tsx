"use client";

import { useState, type CSSProperties, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { ApiError, authApi } from "@/lib/apiClient";

export default function LoginPage() {
  const router = useRouter();
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
      // MVP: token storage; production should move to httpOnly cookies.
      window.localStorage.setItem("aerocomply_access_token", tokens.access_token);
      window.localStorage.setItem("aerocomply_refresh_token", tokens.refresh_token);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={{ display: "flex", height: "100vh", alignItems: "center", justifyContent: "center" }}>
      <form
        onSubmit={handleSubmit}
        style={{
          width: 360,
          padding: 32,
          borderRadius: 12,
          background: "#131c2e",
          border: "1px solid #23324a",
        }}
      >
        <h2 style={{ marginTop: 0 }}>Sign in to AeroComply</h2>

        <label style={{ display: "block", marginBottom: 12 }}>
          <span style={{ display: "block", marginBottom: 4, fontSize: 13, opacity: 0.8 }}>Email</span>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            style={inputStyle}
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

        {error && (
          <p role="alert" style={{ color: "#ff6b6b", fontSize: 13, marginBottom: 12 }}>
            {error}
          </p>
        )}

        <button type="submit" disabled={loading} style={buttonStyle}>
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}

const inputStyle: CSSProperties = {
  width: "100%",
  padding: "10px 12px",
  borderRadius: 8,
  border: "1px solid #2c3e5a",
  background: "#0b1220",
  color: "#e6ebf2",
  boxSizing: "border-box",
};

const buttonStyle: CSSProperties = {
  width: "100%",
  padding: "10px 12px",
  borderRadius: 8,
  border: "none",
  background: "#2f6fed",
  color: "white",
  fontWeight: 600,
  cursor: "pointer",
};
