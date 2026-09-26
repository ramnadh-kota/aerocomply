"use client";

import { useEffect, useState, useRef, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBadge } from "@/components/status/StatusBadge";
import { useSession } from "@/lib/auth/SessionContext";
import { authApi, normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";

type Tab = "profile" | "preferences" | "security";

const PHONE_REGEX = /^\+?[0-9\s\-()]{7,32}$/;

function EmailVerificationSection() {
  const { user, accessToken, isDemo } = useSession();
  const [requested, setRequested] = useState(false);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [confirmed, setConfirmed] = useState(false);

  if (!user) return null;

  if (user.email_verified || confirmed || isDemo) {
    return (
      <div className="ac-card" style={{ padding: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <StatusBadge status="COMPLIANT" label="Email Verified" />
          <span className="ac-text-sm ac-text-muted">{user.email}</span>
        </div>
      </div>
    );
  }

  const requestCode = () => {
    if (!accessToken) return;
    setBusy(true);
    setError(null);
    authApi
      .requestEmailVerification(accessToken)
      .then(() => setRequested(true))
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setBusy(false));
  };

  const confirmCode = () => {
    if (!accessToken || !code.trim()) return;
    setBusy(true);
    setError(null);
    authApi
      .confirmEmailVerification(accessToken, code.trim())
      .then(() => setConfirmed(true))
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setBusy(false));
  };

  return (
    <div className="ac-card" style={{ padding: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <StatusBadge status="UNKNOWN" label="Email Not Verified" />
        <span className="ac-text-sm ac-text-muted">{user.email}</span>
      </div>
      {!requested ? (
        <button type="button" className="ac-btn" onClick={requestCode} disabled={busy}>
          {busy ? "Sending Code..." : "Send Verification Code"}
        </button>
      ) : (
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <input
            className="ac-input"
            style={{ width: 140 }}
            placeholder="6-digit code"
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
            aria-label="Verification code"
          />
          <button type="button" className="ac-btn" onClick={confirmCode} disabled={busy || code.length !== 6}>
            {busy ? "Verifying..." : "Confirm Code"}
          </button>
          <button type="button" className="ac-btn" onClick={requestCode} disabled={busy}>
            Resend
          </button>
        </div>
      )}
      {error && (
        <p className="ac-text-sm" style={{ margin: "8px 0 0", color: "var(--ac-status-non-compliant)" }}>
          {error.message}
        </p>
      )}
    </div>
  );
}

function ProfileContent() {
  const searchParams = useSearchParams();
  const initialTab = (searchParams.get("tab") as Tab) || "profile";
  const [activeTab, setActiveTab] = useState<Tab>(initialTab);

  const { user, accessToken, isDemo, organizationName, updateUser } = useSession();

  // Profile Edit State
  const [isEditing, setIsEditing] = useState(false);
  const [fullName, setFullName] = useState(user?.full_name || "");
  const [phoneNumber, setPhoneNumber] = useState(user?.phone_number || "");
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Photo state
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadingPhoto, setUploadingPhoto] = useState(false);
  const [photoError, setPhotoError] = useState<string | null>(null);
  const [photoSuccess, setPhotoSuccess] = useState<string | null>(null);

  // Email Change Workflow State
  const [showEmailChange, setShowEmailChange] = useState(false);
  const [newEmail, setNewEmail] = useState("");
  const [emailOtp, setEmailOtp] = useState("");
  const [emailWorkflowPending, setEmailWorkflowPending] = useState(!!user?.pending_email);
  const [emailWorkflowBusy, setEmailWorkflowBusy] = useState(false);
  const [emailWorkflowMsg, setEmailWorkflowMsg] = useState<string | null>(null);
  const [emailWorkflowError, setEmailWorkflowError] = useState<string | null>(null);

  // Preference states
  const [density, setDensity] = useState<"comfortable" | "compact">("comfortable");
  const [notifAog, setNotifAog] = useState(true);
  const [notifMaintenance, setNotifMaintenance] = useState(true);
  const [notifRegulatory, setNotifRegulatory] = useState(true);
  const [aiStyle, setAiStyle] = useState<"balanced" | "concise" | "thorough">("balanced");
  const [prefSaved, setPrefSaved] = useState(false);

  // Password reset state
  const [resetRequested, setResetRequested] = useState(false);

  // Synchronize form states when user session updates
  useEffect(() => {
    if (user) {
      setFullName(user.full_name || "");
      setPhoneNumber(user.phone_number || "");
      if (user.pending_email) {
        setEmailWorkflowPending(true);
      }
    }
  }, [user]);

  // Load client-only preferences from localStorage
  useEffect(() => {
    try {
      const savedDensity = localStorage.getItem("aerocomply_pref_density");
      if (savedDensity === "compact" || savedDensity === "comfortable") setDensity(savedDensity);
      const savedAiStyle = localStorage.getItem("aerocomply_pref_ai_style");
      if (savedAiStyle && ["balanced", "concise", "thorough"].includes(savedAiStyle)) {
        setAiStyle(savedAiStyle as any);
      }
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    const tabParam = searchParams.get("tab") as Tab;
    if (tabParam && ["profile", "preferences", "security"].includes(tabParam)) {
      setActiveTab(tabParam);
    }
  }, [searchParams]);

  const initials = fullName
    ? fullName
        .split(" ")
        .map((p) => p[0])
        .filter(Boolean)
        .slice(0, 2)
        .join("")
        .toUpperCase()
    : "KA";

  // --- Photo Handlers ---
  const handlePhotoFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Reset input so re-selecting same file triggers change
    e.target.value = "";

    // 1. Client-side MIME validation
    const allowedTypes = ["image/jpeg", "image/png", "image/webp"];
    if (!allowedTypes.includes(file.type.toLowerCase())) {
      setPhotoError("Unsupported image format. Allowed formats: PNG, JPEG, WEBP.");
      setPhotoSuccess(null);
      return;
    }

    // 2. Client-side file size validation (2 MB)
    if (file.size > 2 * 1024 * 1024) {
      setPhotoError("Profile photo exceeds maximum limit of 2 MB.");
      setPhotoSuccess(null);
      return;
    }

    setUploadingPhoto(true);
    setPhotoError(null);
    setPhotoSuccess(null);

    try {
      if (isDemo || !accessToken) {
        // Demo Simulation: Use FileReader to create base64 preview
        const reader = new FileReader();
        reader.onload = () => {
          const dataUrl = reader.result as string;
          updateUser({ profile_photo_url: dataUrl });
          setPhotoSuccess("Profile photo updated (Demo interactive simulation).");
          setUploadingPhoto(false);
        };
        reader.onerror = () => {
          setPhotoError("Failed to read image file.");
          setUploadingPhoto(false);
        };
        reader.readAsDataURL(file);
      } else {
        // Real API Upload
        const updated = await authApi.uploadPhoto(accessToken, file);
        updateUser(updated);
        setPhotoSuccess("Profile photo uploaded and saved successfully.");
        setUploadingPhoto(false);
      }
    } catch (err: any) {
      const normalized = normalizeApiError(err);
      setPhotoError(normalized.message || "Failed to upload photo.");
      setUploadingPhoto(false);
    }
  };

  const handleRemovePhoto = async () => {
    setUploadingPhoto(true);
    setPhotoError(null);
    setPhotoSuccess(null);

    try {
      if (isDemo || !accessToken) {
        updateUser({ profile_photo_url: null });
        setPhotoSuccess("Profile photo removed.");
      } else {
        const updated = await authApi.deletePhoto(accessToken);
        updateUser(updated);
        setPhotoSuccess("Profile photo removed.");
      }
    } catch (err: any) {
      const normalized = normalizeApiError(err);
      setPhotoError(normalized.message || "Failed to remove photo.");
    } finally {
      setUploadingPhoto(false);
    }
  };

  // --- Personal Details Form Handlers ---
  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanName = fullName.trim();
    const cleanPhone = phoneNumber.trim();

    if (!cleanName) {
      setSaveError("Full legal name cannot be empty.");
      return;
    }

    if (cleanPhone && !PHONE_REGEX.test(cleanPhone)) {
      setSaveError("Invalid phone number format. Allowed: digits, spaces, hyphens, plus sign, parentheses.");
      return;
    }

    setSaving(true);
    setSaveError(null);
    setSaveSuccess(null);

    try {
      if (isDemo || !accessToken) {
        // Demo mode update
        updateUser({
          full_name: cleanName,
          phone_number: cleanPhone || null,
        });
        setSaveSuccess("Profile details updated successfully (Demo session).");
      } else {
        // Real mode update
        const updated = await authApi.updateMe(accessToken, {
          full_name: cleanName,
          phone_number: cleanPhone || null,
        });
        updateUser(updated);
        setSaveSuccess("Profile details updated and persisted successfully.");
      }
      setIsEditing(false);
    } catch (err: any) {
      const normalized = normalizeApiError(err);
      setSaveError(normalized.message || "Failed to update profile.");
    } finally {
      setSaving(false);
    }
  };

  // --- Email Change Workflow Handlers ---
  const handleRequestEmailChange = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanEmail = newEmail.trim().toLowerCase();

    if (!cleanEmail || !cleanEmail.includes("@") || !cleanEmail.includes(".")) {
      setEmailWorkflowError("Please enter a valid email address.");
      return;
    }

    if (cleanEmail === user?.email?.toLowerCase()) {
      setEmailWorkflowError("The new email must be different from your current verified email.");
      return;
    }

    setEmailWorkflowBusy(true);
    setEmailWorkflowError(null);
    setEmailWorkflowMsg(null);

    try {
      if (isDemo || !accessToken) {
        // Demo Simulation: simulate dispatch without external email
        updateUser({ pending_email: cleanEmail });
        setEmailWorkflowPending(true);
        setEmailWorkflowMsg(`DEMO SIMULATION · Verification code sent to ${cleanEmail}. Use code 123456 to confirm.`);
      } else {
        const res = await authApi.requestEmailChange(accessToken, cleanEmail);
        updateUser({ pending_email: cleanEmail });
        setEmailWorkflowPending(true);
        setEmailWorkflowMsg(res.message || `Verification code sent to ${cleanEmail}.`);
      }
    } catch (err: any) {
      const normalized = normalizeApiError(err);
      setEmailWorkflowError(normalized.message || "Failed to request email change.");
    } finally {
      setEmailWorkflowBusy(false);
    }
  };

  const handleConfirmEmailChange = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanCode = emailOtp.trim();

    if (cleanCode.length !== 6) {
      setEmailWorkflowError("Verification code must be exactly 6 digits.");
      return;
    }

    setEmailWorkflowBusy(true);
    setEmailWorkflowError(null);
    setEmailWorkflowMsg(null);

    try {
      if (isDemo || !accessToken) {
        const simulatedEmail = user?.pending_email || newEmail;
        updateUser({
          email: simulatedEmail,
          pending_email: null,
          email_verified: true,
        });
        setEmailWorkflowPending(false);
        setShowEmailChange(false);
        setNewEmail("");
        setEmailOtp("");
        setSaveSuccess(`Email successfully updated to ${simulatedEmail} (Demo simulation).`);
      } else {
        const updated = await authApi.confirmEmailChange(accessToken, cleanCode);
        updateUser(updated);
        setEmailWorkflowPending(false);
        setShowEmailChange(false);
        setNewEmail("");
        setEmailOtp("");
        setSaveSuccess(`Email address successfully verified and updated to ${updated.email}.`);
      }
    } catch (err: any) {
      const normalized = normalizeApiError(err);
      setEmailWorkflowError(normalized.message || "Failed to confirm email change code.");
    } finally {
      setEmailWorkflowBusy(false);
    }
  };

  const handleCancelEmailChange = async () => {
    setEmailWorkflowBusy(true);
    setEmailWorkflowError(null);

    try {
      if (isDemo || !accessToken) {
        updateUser({ pending_email: null });
        setEmailWorkflowPending(false);
        setShowEmailChange(false);
        setNewEmail("");
        setEmailOtp("");
        setEmailWorkflowMsg("Email change request cancelled.");
      } else {
        const updated = await authApi.cancelEmailChange(accessToken);
        updateUser(updated);
        setEmailWorkflowPending(false);
        setShowEmailChange(false);
        setNewEmail("");
        setEmailOtp("");
        setEmailWorkflowMsg("Pending email change cancelled.");
      }
    } catch (err: any) {
      const normalized = normalizeApiError(err);
      setEmailWorkflowError(normalized.message || "Failed to cancel email change.");
    } finally {
      setEmailWorkflowBusy(false);
    }
  };

  // --- UI Preferences Handlers ---
  const handleSavePreferences = () => {
    try {
      localStorage.setItem("aerocomply_pref_density", density);
      localStorage.setItem("aerocomply_pref_ai_style", aiStyle);
    } catch {
      // ignore
    }
    setPrefSaved(true);
    setTimeout(() => setPrefSaved(false), 2500);
  };

  const handleRequestPasswordReset = async () => {
    if (!user?.email) return;
    try {
      await authApi.forgotPassword(user.email);
      setResetRequested(true);
    } catch {
      setResetRequested(true);
    }
  };

  return (
    <div className="ac-page">
      <PageHeader
        breadcrumbs={[
          { label: "Dashboard", href: "/dashboard" },
          { label: "Personal Account", href: "/profile" },
          { label: activeTab === "profile" ? "Profile" : activeTab === "preferences" ? "Preferences" : "Security" },
        ]}
        title="My Account & Profile"
        subtitle="Manage your personal identity, contact details, authentication credentials, and user preferences."
      />

      {/* Mode Indicator */}
      <div style={{ marginBottom: 16 }}>
        {isDemo ? (
          <div
            style={{
              padding: "10px 16px",
              background: "rgba(59, 130, 246, 0.08)",
              border: "1px solid rgba(59, 130, 246, 0.25)",
              borderRadius: 6,
              fontSize: 13,
            }}
          >
            <strong>DEMO SESSION</strong> · Personal profile edits are active for this synthetic interactive session without modifying live databases or dispatching external emails.
          </div>
        ) : (
          <div
            style={{
              padding: "10px 16px",
              background: "rgba(16, 185, 129, 0.08)",
              border: "1px solid rgba(16, 185, 129, 0.25)",
              borderRadius: 6,
              fontSize: 13,
            }}
          >
            <strong>REAL ENVIRONMENT</strong> · Authenticated user account synchronized with backend PostgreSQL identity services and audit logs.
          </div>
        )}
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 8, borderBottom: "1px solid var(--ac-border)", marginBottom: 20 }}>
        <button
          type="button"
          onClick={() => { setActiveTab("profile"); setSaveSuccess(null); }}
          className="ac-btn"
          style={{
            borderBottom: activeTab === "profile" ? "2px solid var(--ac-primary, #38bdf8)" : "none",
            borderRadius: "6px 6px 0 0",
            fontWeight: activeTab === "profile" ? 600 : 400,
          }}
        >
          👤 Personal Profile
        </button>
        <button
          type="button"
          onClick={() => { setActiveTab("preferences"); setSaveSuccess(null); }}
          className="ac-btn"
          style={{
            borderBottom: activeTab === "preferences" ? "2px solid var(--ac-primary, #38bdf8)" : "none",
            borderRadius: "6px 6px 0 0",
            fontWeight: activeTab === "preferences" ? 600 : 400,
          }}
        >
          ⚙ My Preferences
        </button>
        <button
          type="button"
          onClick={() => { setActiveTab("security"); setSaveSuccess(null); }}
          className="ac-btn"
          style={{
            borderBottom: activeTab === "security" ? "2px solid var(--ac-primary, #38bdf8)" : "none",
            borderRadius: "6px 6px 0 0",
            fontWeight: activeTab === "security" ? 600 : 400,
          }}
        >
          🔒 Security &amp; Credentials
        </button>
      </div>

      {saveSuccess && (
        <div
          style={{
            padding: "10px 16px",
            background: "rgba(16, 185, 129, 0.15)",
            border: "1px solid #10b981",
            borderRadius: 6,
            color: "#6ee7b7",
            marginBottom: 20,
            fontSize: 14,
          }}
        >
          ✓ {saveSuccess}
        </div>
      )}

      {saveError && (
        <div
          style={{
            padding: "10px 16px",
            background: "rgba(239, 68, 68, 0.15)",
            border: "1px solid #ef4444",
            borderRadius: 6,
            color: "#fca5a5",
            marginBottom: 20,
            fontSize: 14,
          }}
        >
          {saveError}
        </div>
      )}

      {/* TAB 1: PERSONAL PROFILE */}
      {activeTab === "profile" && (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(280px, 340px) 1fr", gap: 24, alignItems: "start" }}>
          {/* Avatar & Read-Only Summary Card */}
          <div className="ac-card" style={{ padding: 24, textAlign: "center" }}>
            <div style={{ position: "relative", width: 96, height: 96, margin: "0 auto 16px" }}>
              {user?.profile_photo_url ? (
                <img
                  src={user.profile_photo_url}
                  alt={user?.full_name || "Profile Photo"}
                  style={{
                    width: 96,
                    height: 96,
                    borderRadius: "50%",
                    objectFit: "cover",
                    border: "3px solid var(--ac-primary, #38bdf8)",
                    boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
                  }}
                />
              ) : (
                <div
                  style={{
                    width: 96,
                    height: 96,
                    borderRadius: "50%",
                    background: "rgba(56, 189, 248, 0.15)",
                    border: "2px solid #38bdf8",
                    color: "#38bdf8",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 32,
                    fontWeight: 700,
                  }}
                >
                  {initials}
                </div>
              )}
            </div>

            <h2 style={{ fontSize: 20, fontWeight: 700, margin: "0 0 4px" }}>{user?.full_name || "Aerospace User"}</h2>
            <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 16px" }}>{user?.email}</p>

            <div style={{ display: "flex", justifyContent: "center", gap: 6, flexWrap: "wrap", marginBottom: 16 }}>
              {user?.roles?.map((role) => (
                <span
                  key={role}
                  style={{
                    padding: "3px 8px",
                    background: "var(--ac-bg-surface-hover, #1f2937)",
                    border: "1px solid var(--ac-border, #374151)",
                    borderRadius: 4,
                    fontSize: 11,
                    fontWeight: 600,
                    textTransform: "uppercase",
                  }}
                >
                  {role.replace(/_/g, " ")}
                </span>
              ))}
            </div>

            {/* Read-Only Context Information */}
            <div style={{ borderTop: "1px solid var(--ac-border)", paddingTop: 16, textAlign: "left", fontSize: 13 }}>
              <div style={{ marginBottom: 8 }}>
                <span className="ac-text-muted">Organization (Read-only):</span>{" "}
                <strong>{organizationName || "KOTA Operations"}</strong>
              </div>
              <div style={{ marginBottom: 12 }}>
                <span className="ac-text-muted">User ID:</span>{" "}
                <span className="ac-mono" style={{ fontSize: 11 }}>{user?.id ? `${user.id.slice(0, 12)}…` : "—"}</span>
              </div>
              <div style={{ padding: "8px 10px", background: "var(--ac-bg-surface-hover)", borderRadius: 6, fontSize: 12 }}>
                <span className="ac-text-muted">Organization governance and fleet privileges are managed under </span>
                <Link href="/tenant/settings" style={{ color: "var(--ac-primary, #38bdf8)", fontWeight: 600 }}>
                  Organization Settings →
                </Link>
              </div>
            </div>
          </div>

          {/* Profile Details & Photo Editor */}
          <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
            {/* 1. Profile Photo Management Card */}
            <div className="ac-card" style={{ padding: 24 }}>
              <h3 style={{ fontSize: 18, fontWeight: 600, margin: "0 0 6px" }}>Profile Photo</h3>
              <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 16px" }}>
                Upload a real profile picture (PNG, JPEG, WEBP up to 2 MB) to represent your identity across Topbar and flight operations.
              </p>

              <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={handlePhotoFileSelect}
                  accept="image/png,image/jpeg,image/webp"
                  style={{ display: "none" }}
                  aria-label="Upload profile photo"
                />

                <button
                  type="button"
                  className="ac-btn"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploadingPhoto}
                  style={{ background: "var(--ac-primary, #38bdf8)", color: "#000", fontWeight: 600 }}
                >
                  {uploadingPhoto ? "Uploading..." : user?.profile_photo_url ? "Change Photo" : "Upload Photo"}
                </button>

                {user?.profile_photo_url && (
                  <button
                    type="button"
                    className="ac-btn"
                    onClick={handleRemovePhoto}
                    disabled={uploadingPhoto}
                    style={{ color: "var(--ac-status-non-compliant)" }}
                  >
                    Remove Photo
                  </button>
                )}

                <span className="ac-text-xs ac-text-muted">
                  {user?.profile_photo_url ? "Custom photo active" : "Using initials avatar"}
                </span>
              </div>

              {photoSuccess && (
                <p className="ac-text-sm" style={{ color: "var(--ac-status-compliant)", margin: "12px 0 0" }}>
                  ✓ {photoSuccess}
                </p>
              )}
              {photoError && (
                <p className="ac-text-sm" style={{ color: "var(--ac-status-non-compliant)", margin: "12px 0 0" }}>
                  ⚠ {photoError}
                </p>
              )}
            </div>

            {/* 2. Personal Information Card */}
            <div className="ac-card" style={{ padding: 24 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                <div>
                  <h3 style={{ fontSize: 18, fontWeight: 600, margin: 0 }}>Personal Information</h3>
                  <p className="ac-text-sm ac-text-muted" style={{ margin: "4px 0 0" }}>
                    Authoritative personal contact information persisted to your account.
                  </p>
                </div>
                {!isEditing && (
                  <button
                    type="button"
                    className="ac-btn"
                    onClick={() => { setIsEditing(true); setSaveSuccess(null); }}
                  >
                    ✎ Edit Details
                  </button>
                )}
              </div>

              {!isEditing ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                  <div>
                    <div className="ac-text-xs ac-text-muted" style={{ textTransform: "uppercase", letterSpacing: 0.5 }}>
                      Full Legal Name
                    </div>
                    <div style={{ fontSize: 16, fontWeight: 600, marginTop: 4 }}>
                      {user?.full_name || "—"}
                    </div>
                  </div>

                  <div>
                    <div className="ac-text-xs ac-text-muted" style={{ textTransform: "uppercase", letterSpacing: 0.5 }}>
                      Work Email Address
                    </div>
                    <div style={{ fontSize: 15, marginTop: 4, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                      <strong>{user?.email || "—"}</strong>
                      {user?.email_verified ? (
                        <StatusBadge status="COMPLIANT" label="Verified" />
                      ) : (
                        <StatusBadge status="NON_COMPLIANT" label="Unverified" />
                      )}
                      {!showEmailChange && !emailWorkflowPending && (
                        <button
                          type="button"
                          className="ac-btn"
                          style={{ fontSize: 12, padding: "3px 8px" }}
                          onClick={() => { setShowEmailChange(true); setEmailWorkflowError(null); }}
                        >
                          Change Email
                        </button>
                      )}
                    </div>
                  </div>

                  <div>
                    <div className="ac-text-xs ac-text-muted" style={{ textTransform: "uppercase", letterSpacing: 0.5 }}>
                      Contact Phone Number (Authoritative)
                    </div>
                    <div style={{ fontSize: 15, marginTop: 4 }}>
                      {user?.phone_number ? (
                        <strong>{user.phone_number}</strong>
                      ) : (
                        <span className="ac-text-muted">Not specified</span>
                      )}
                    </div>
                  </div>
                </div>
              ) : (
                <form onSubmit={handleSaveProfile}>
                  <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                    <div>
                      <label htmlFor="user-full-name" style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
                        Full Legal Name *
                      </label>
                      <input
                        id="user-full-name"
                        type="text"
                        className="ac-input"
                        value={fullName}
                        onChange={(e) => setFullName(e.target.value)}
                        required
                        style={{ width: "100%", maxWidth: 420 }}
                        placeholder="e.g. Capt. Vikram Sharma"
                      />
                    </div>

                    <div>
                      <label htmlFor="user-phone-number" style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
                        Contact Phone Number
                      </label>
                      <input
                        id="user-phone-number"
                        type="tel"
                        className="ac-input"
                        value={phoneNumber}
                        onChange={(e) => setPhoneNumber(e.target.value)}
                        style={{ width: "100%", maxWidth: 420 }}
                        placeholder="+91 98765 43210 or +1 (555) 019-2834"
                      />
                      <span className="ac-text-xs ac-text-muted" style={{ display: "block", marginTop: 4 }}>
                        Persisted authoritatively to your user account profile in PostgreSQL.
                      </span>
                    </div>

                    <div style={{ display: "flex", gap: 12, marginTop: 8 }}>
                      <button
                        type="submit"
                        className="ac-btn"
                        disabled={saving}
                        style={{ background: "var(--ac-primary, #38bdf8)", color: "#000", fontWeight: 600 }}
                      >
                        {saving ? "Saving Changes..." : "Save Changes"}
                      </button>
                      <button
                        type="button"
                        className="ac-btn"
                        disabled={saving}
                        onClick={() => {
                          setIsEditing(false);
                          setFullName(user?.full_name || "");
                          setPhoneNumber(user?.phone_number || "");
                        }}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                </form>
              )}

              {/* 3. Verified Email Change Workflow */}
              {(showEmailChange || emailWorkflowPending || user?.pending_email) && (
                <div
                  style={{
                    marginTop: 24,
                    padding: 18,
                    background: "var(--ac-bg-surface-hover, rgba(255,255,255,0.02))",
                    border: "1px solid var(--ac-border)",
                    borderRadius: 8,
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                    <h4 style={{ fontSize: 15, fontWeight: 600, margin: 0 }}>Verified Email Change Workflow</h4>
                    <span className="ac-badge ac-badge-warning" style={{ fontSize: 11 }}>Verification Required</span>
                  </div>

                  {isDemo && (
                    <div
                      style={{
                        padding: "8px 12px",
                        background: "rgba(59, 130, 246, 0.12)",
                        border: "1px solid rgba(59, 130, 246, 0.3)",
                        borderRadius: 6,
                        fontSize: 12,
                        marginBottom: 14,
                      }}
                    >
                      <strong>DEMO SIMULATION</strong> · No external email dispatched. You can verify with code <strong>123456</strong>.
                    </div>
                  )}

                  {!emailWorkflowPending && !user?.pending_email ? (
                    <form onSubmit={handleRequestEmailChange}>
                      <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 12px" }}>
                        Your active email address (<strong>{user?.email}</strong>) will remain active and verified until you confirm the 6-digit code sent to your new address.
                      </p>
                      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                        <input
                          type="email"
                          className="ac-input"
                          placeholder="new.email@example.com"
                          value={newEmail}
                          onChange={(e) => setNewEmail(e.target.value)}
                          required
                          style={{ width: 280 }}
                          aria-label="New email address"
                        />
                        <button
                          type="submit"
                          className="ac-btn"
                          disabled={emailWorkflowBusy || !newEmail.trim()}
                          style={{ background: "var(--ac-primary, #38bdf8)", color: "#000", fontWeight: 600 }}
                        >
                          {emailWorkflowBusy ? "Requesting..." : "Send Verification Code"}
                        </button>
                        <button
                          type="button"
                          className="ac-btn"
                          disabled={emailWorkflowBusy}
                          onClick={() => { setShowEmailChange(false); setEmailWorkflowError(null); }}
                        >
                          Cancel
                        </button>
                      </div>
                    </form>
                  ) : (
                    <form onSubmit={handleConfirmEmailChange}>
                      <div style={{ marginBottom: 12 }}>
                        <span className="ac-text-sm ac-text-muted">Pending New Email:</span>{" "}
                        <strong style={{ color: "var(--ac-primary, #38bdf8)" }}>
                          {user?.pending_email || newEmail}
                        </strong>
                      </div>
                      <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 12px" }}>
                        Enter the 6-digit verification code sent to the new email address to complete the change.
                      </p>
                      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                        <input
                          type="text"
                          className="ac-input"
                          placeholder="6-digit code"
                          maxLength={6}
                          value={emailOtp}
                          onChange={(e) => setEmailOtp(e.target.value.replace(/\D/g, "").slice(0, 6))}
                          style={{ width: 140, letterSpacing: 2, fontWeight: 700 }}
                          aria-label="6-digit email confirmation code"
                        />
                        <button
                          type="submit"
                          className="ac-btn"
                          disabled={emailWorkflowBusy || emailOtp.length !== 6}
                          style={{ background: "var(--ac-primary, #38bdf8)", color: "#000", fontWeight: 600 }}
                        >
                          {emailWorkflowBusy ? "Confirming..." : "Confirm & Update Email"}
                        </button>
                        <button
                          type="button"
                          className="ac-btn"
                          disabled={emailWorkflowBusy}
                          onClick={handleCancelEmailChange}
                          style={{ color: "var(--ac-status-non-compliant)" }}
                        >
                          Cancel Email Change
                        </button>
                      </div>
                    </form>
                  )}

                  {emailWorkflowMsg && (
                    <p className="ac-text-sm" style={{ color: "var(--ac-primary, #38bdf8)", margin: "10px 0 0" }}>
                      ℹ {emailWorkflowMsg}
                    </p>
                  )}
                  {emailWorkflowError && (
                    <p className="ac-text-sm" style={{ color: "var(--ac-status-non-compliant)", margin: "10px 0 0" }}>
                      ⚠ {emailWorkflowError}
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: MY PREFERENCES */}
      {activeTab === "preferences" && (
        <div className="ac-card" style={{ padding: 24, maxWidth: 680 }}>
          <h3 style={{ fontSize: 18, fontWeight: 600, margin: "0 0 6px" }}>Personal UI Preferences</h3>
          <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 24px" }}>
            Adjust display density, alerts, and workspace interaction to your personal preference. These are client-scoped to this browser.
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <div>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 8 }}>
                Display Density
              </label>
              <div style={{ display: "flex", gap: 12 }}>
                <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontSize: 14 }}>
                  <input
                    type="radio"
                    name="density"
                    value="comfortable"
                    checked={density === "comfortable"}
                    onChange={() => setDensity("comfortable")}
                  />
                  Comfortable (Standard spacing)
                </label>
                <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontSize: 14 }}>
                  <input
                    type="radio"
                    name="density"
                    value="compact"
                    checked={density === "compact"}
                    onChange={() => setDensity("compact")}
                  />
                  Compact (High-density telemetry & tables)
                </label>
              </div>
            </div>

            <div style={{ borderTop: "1px solid var(--ac-border)", paddingTop: 16 }}>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 8 }}>
                Notification Subscriptions
              </label>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <label style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 14, cursor: "pointer" }}>
                  <input
                    type="checkbox"
                    checked={notifAog}
                    onChange={(e) => setNotifAog(e.target.checked)}
                  />
                  <span>AOG / Grounding critical priority alerts</span>
                </label>
                <label style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 14, cursor: "pointer" }}>
                  <input
                    type="checkbox"
                    checked={notifMaintenance}
                    onChange={(e) => setNotifMaintenance(e.target.checked)}
                  />
                  <span>Upcoming scheduled maintenance &amp; RII milestones</span>
                </label>
                <label style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 14, cursor: "pointer" }}>
                  <input
                    type="checkbox"
                    checked={notifRegulatory}
                    onChange={(e) => setNotifRegulatory(e.target.checked)}
                  />
                  <span>Regulatory updates &amp; Airworthiness Directive bulletins</span>
                </label>
              </div>
            </div>

            <div style={{ borderTop: "1px solid var(--ac-border)", paddingTop: 16 }}>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 8 }}>
                AI Assistant (Lisa) Reasoning Detail
              </label>
              <select
                className="ac-input"
                value={aiStyle}
                onChange={(e) => setAiStyle(e.target.value as any)}
                style={{ width: "100%", maxWidth: 320 }}
              >
                <option value="balanced">Balanced (Standard narrative + action links)</option>
                <option value="concise">Concise (Immediate status &amp; blockers only)</option>
                <option value="thorough">Thorough (Detailed regulation &amp; maintenance citations)</option>
              </select>
            </div>

            <div style={{ marginTop: 12 }}>
              <button
                type="button"
                className="ac-btn"
                onClick={handleSavePreferences}
                style={{ background: "var(--ac-primary, #38bdf8)", color: "#000", fontWeight: 600 }}
              >
                {prefSaved ? "✓ Preferences Saved" : "Save Preferences"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: SECURITY & CREDENTIALS */}
      {activeTab === "security" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 20, maxWidth: 680 }}>
          {/* Email Verification */}
          <div className="ac-card" style={{ padding: 24 }}>
            <h3 style={{ fontSize: 18, fontWeight: 600, margin: "0 0 6px" }}>Email Verification</h3>
            <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 16px" }}>
              Verified work email allows password recovery and high-security operations.
            </p>
            <EmailVerificationSection />
          </div>

          {/* Password Management */}
          <div className="ac-card" style={{ padding: 24 }}>
            <h3 style={{ fontSize: 18, fontWeight: 600, margin: "0 0 6px" }}>Password &amp; Credentials</h3>
            <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 16px" }}>
              Secure password reset via authenticated one-time OTP email delivery.
            </p>
            {!resetRequested ? (
              <button type="button" className="ac-btn" onClick={handleRequestPasswordReset}>
                Request Password Reset Link
              </button>
            ) : (
              <div
                style={{
                  padding: "10px 14px",
                  background: "rgba(59, 130, 246, 0.1)",
                  border: "1px solid rgba(59, 130, 246, 0.3)",
                  borderRadius: 6,
                  fontSize: 13,
                }}
              >
                A password reset confirmation has been dispatched to <strong>{user?.email}</strong>. Follow the instructions in the email.
              </div>
            )}
          </div>

          {/* Active Session Info */}
          <div className="ac-card" style={{ padding: 24 }}>
            <h3 style={{ fontSize: 18, fontWeight: 600, margin: "0 0 6px" }}>Active Session Context</h3>
            <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 16px" }}>
              Current cryptographic authentication and tenant authorization details.
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, fontSize: 13 }}>
              <div>
                <span className="ac-text-muted">Environment:</span>{" "}
                <strong>{isDemo ? "DEMO (Synthetic)" : "REAL (Live)"}</strong>
              </div>
              <div>
                <span className="ac-text-muted">Session Type:</span>{" "}
                <strong>{isDemo ? "Demo Sandbox" : "Bearer JWT"}</strong>
              </div>
              <div>
                <span className="ac-text-muted">Organization ID:</span>{" "}
                <span className="ac-mono" style={{ fontSize: 11 }}>{user?.organization_id || "—"}</span>
              </div>
              <div>
                <span className="ac-text-muted">Assigned Roles:</span>{" "}
                <strong>{user?.roles?.join(", ") || "—"}</strong>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ProfilePage() {
  return (
    <Suspense fallback={<div className="ac-page"><p>Loading profile...</p></div>}>
      <ProfileContent />
    </Suspense>
  );
}
