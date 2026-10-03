"use client";

import { useId, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { authApi, normalizeApiError } from "@/lib/apiClient";
import { useSession } from "@/lib/auth/SessionContext";
import { useDataMode } from "@/lib/data-mode/DataModeContext";
import { Logo } from "@/components/branding/Logo";
import { AerospaceShowcase } from "@/components/auth-showcase/AerospaceShowcase";
import styles from "./login.module.css";

function EyeIcon({ off }: { off: boolean }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z" />
      <circle cx="12" cy="12" r="3" />
      {off ? <path d="M4 4l16 16" /> : null}
    </svg>
  );
}

export default function LoginPage() {
  const router = useRouter();
  const { login } = useSession();
  const { setMode } = useDataMode();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const errorId = useId();

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (loading) return; // guard against a duplicate submit landing before re-render disables the button
    setError(null);
    setRetrying(false);
    setLoading(true);

    try {
      const tokens = await authApi.login(email, password, { onRetry: () => setRetrying(true) });
      const me = await login(tokens);
      setMode("REAL");
      const isPlatformUser =
        me.roles?.some((r) => r === "PLATFORM_ADMIN" || r === "PLATFORM_STAFF") ?? false;
      router.push(isPlatformUser ? "/platform/dashboard" : "/dashboard");
    } catch (err) {
      setError(normalizeApiError(err).message);
    } finally {
      setLoading(false);
      setRetrying(false);
    }
  }

  return (
    <div className={styles.shell}>
      <section className={styles.formSide} aria-labelledby="login-title">
        <div className={styles.brand}>
          <Logo height={96} />
        </div>

        <main className={styles.main}>
          <h1 id="login-title" className={styles.welcome}>
            Welcome back.
          </h1>
          <p className={styles.intro}>
            Sign in to your workspace to monitor fleets, manage maintenance and compliance, and unlock
            intelligence across every asset.
          </p>

          <form onSubmit={handleSubmit} aria-busy={loading}>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="login-email">
                Email
              </label>
              <input
                id="login-email"
                className={styles.input}
                type="email"
                name="email"
                autoComplete="username"
                inputMode="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@company.com"
                aria-invalid={error ? true : undefined}
                aria-describedby={error ? errorId : undefined}
              />
            </div>

            <div className={styles.field}>
              <label className={styles.label} htmlFor="login-password">
                Password
              </label>
              <div className={styles.inputWrap}>
                <input
                  id="login-password"
                  className={`${styles.input} ${styles.hasToggle}`}
                  type={showPassword ? "text" : "password"}
                  name="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Password"
                  aria-invalid={error ? true : undefined}
                  aria-describedby={error ? errorId : undefined}
                />
                <button
                  type="button"
                  className={styles.toggle}
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  aria-pressed={showPassword}
                >
                  <EyeIcon off={showPassword} />
                </button>
              </div>
            </div>

            <div className={styles.forgotRow}>
              <Link href="/forgot-password" className={styles.link}>
                Forgot password?
              </Link>
            </div>

            <div aria-live="polite">
              {error && (
                <p id={errorId} role="alert" className={styles.error}>
                  {error}
                </p>
              )}
            </div>

            <button type="submit" disabled={loading} className={styles.submit}>
              {loading ? <span className={styles.spinner} aria-hidden="true" /> : null}
              {retrying ? "Connecting…" : loading ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <p className={styles.access}>Access is provisioned by your organization administrator.</p>
        </main>
      </section>

      <AerospaceShowcase />
    </div>
  );
}
