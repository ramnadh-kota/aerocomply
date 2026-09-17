"use client";

import { Suspense, useState, type CSSProperties, type FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { authApi, normalizeApiError } from "@/lib/apiClient";
import { Logo } from "@/components/branding/Logo";

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState(searchParams.get("email") ?? "");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await authApi.resetPassword(email, code, newPassword);
      setDone(true);
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
        <h2 style={{ marginTop: 0 }}>Reset password</h2>

        {done ? (
          <>
            <p style={{ fontSize: 14, marginBottom: 16 }}>
              Your password has been reset. You can now sign in with your new password.
            </p>
            <button type="button" style={buttonStyle} onClick={() => router.push("/login")}>
              Go to sign in
            </button>
          </>
        ) : (
          <>
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

            <label style={{ display: "block", marginBottom: 12 }}>
              <span style={{ display: "block", marginBottom: 4, fontSize: 13, opacity: 0.8 }}>6-digit code</span>
              <input
                type="text"
                inputMode="numeric"
                pattern="\d{6}"
                maxLength={6}
                required
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                style={inputStyle}
              />
            </label>

            <label style={{ display: "block", marginBottom: 16 }}>
              <span style={{ display: "block", marginBottom: 4, fontSize: 13, opacity: 0.8 }}>New password</span>
              <input
                type="password"
                required
                minLength={8}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                style={inputStyle}
              />
            </label>

            {error && (
              <p role="alert" style={{ color: "var(--ac-status-non-compliant)", fontSize: 13, marginBottom: 12 }}>
                {error}
              </p>
            )}

            <button type="submit" disabled={loading} style={buttonStyle}>
              {loading ? "Resetting…" : "Reset password"}
            </button>
          </>
        )}

        <p style={{ margin: "16px 0 0", fontSize: 13 }}>
          <Link href="/forgot-password">Request a new code</Link> · <Link href="/login">Back to sign in</Link>
        </p>
      </form>
    </main>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPasswordForm />
    </Suspense>
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
