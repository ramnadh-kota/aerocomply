"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "@/lib/auth/SessionContext";
import { Logo } from "@/components/branding/Logo";

export default function HomePage() {
  const router = useRouter();
  const { user, isAuthenticated, loading } = useSession();

  useEffect(() => {
    if (loading) return;
    if (!isAuthenticated || !user) {
      router.replace("/login");
    } else {
      const isPlatformUser =
        user.roles?.some((r) => r === "PLATFORM_ADMIN" || r === "PLATFORM_STAFF") ?? false;
      router.replace(isPlatformUser ? "/platform/organizations" : "/dashboard");
    }
  }, [loading, isAuthenticated, user, router]);

  return (
    <main
      style={{
        display: "flex",
        height: "100vh",
        alignItems: "center",
        justifyContent: "center",
        flexDirection: "column",
        gap: 16,
      }}
    >
      <Logo height={64} />
      <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
        Redirecting…
      </p>
    </main>
  );
}
