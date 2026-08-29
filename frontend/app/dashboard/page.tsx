"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { authApi, type CurrentUser } from "@/lib/apiClient";

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<CurrentUser | null>(null);

  useEffect(() => {
    const token = window.localStorage.getItem("aerocomply_access_token");
    if (!token) {
      router.push("/login");
      return;
    }
    authApi
      .me(token)
      .then(setUser)
      .catch(() => router.push("/login"));
  }, [router]);

  if (!user) return null;

  return (
    <main style={{ padding: 32 }}>
      <h1>Dashboard</h1>
      <p>
        Signed in as <strong>{user.full_name}</strong> ({user.email}) — roles: {user.roles.join(", ")}
      </p>
      <p style={{ opacity: 0.6, fontSize: 14 }}>
        Fleet compliance score, aircraft counts, and action-required summaries land in M1/M4/M5 per the
        approved milestone sequence.
      </p>
    </main>
  );
}
