"use client";

import { useState, type CSSProperties, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { authApi, normalizeApiError } from "@/lib/apiClient";
import { Logo } from "@/components/branding/Logo";

export default function ForgotPasswordPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      // Backend always responds with the same generic message regardless of
      // whether the email is registered (anti-enumeration) -- the frontend
      // never distinguishes the two cases either.
      await authApi.forgotPassword(email);
      setSubmitted(true);
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
        height: "100vh",
        alignItems: "center",
        justifyContent: "center",
        flexDirection: "column",
        gap: 20,
      }}
    >
      <Logo height={48} />
      <form onSubmit={handleSubmit} className="ac-card" style={{ width: 360, padding: 32 }}>
        <h2 style={{ marginTop: 0 }}>Forgot password</h2>

        {submitted ? (
          <>
            <p style={{ fontSize: 14, marginBottom: 16 }}>
              If that email is registered, a reset code has been sent. Enter it on the next page along with a
              new password.
            </p>
            <button
              type="button"
              style={buttonStyle}
              onClick={() => router.push(`/reset-password?email=${encodeURIComponent(email)}`)}
            >
              I have a code
            </button>
          </>
        ) : (
          <>
            <p style={{ fontSize: 13, opacity: 0.8, marginBottom: 16 }}>
              Enter your account email and we&apos;ll send a 6-digit code to reset your password.
            </p>
            <label style={{ display: "block", marginBottom: 16 }}>
              <span style={{ display: "block", marginBottom: 4, fontSize: 13, opacity: 0.8 }}>Email</span>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                style={inputStyle}
              />
            </label>

            {error && (
              <p role="alert" style={{ color: "var(--ac-status-non-compliant)", fontSize: 13, marginBottom: 12 }}>
                {error}
              </p>
            )}

            <button type="submit" disabled={loading} style={buttonStyle}>
              {loading ? "Sending…" : "Send reset code"}
            </button>
          </>
        )}

        <p style={{ margin: "16px 0 0", fontSize: 13 }}>
          <Link href="/login">Back to sign in</Link>
        </p>
      </form>
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
