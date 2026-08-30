"use client";

import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { vendors, vendorPartAvailabilityForVendor } from "@/lib/mock/procurement";
import type { VendorApprovalStatus, VendorQualityStatus } from "@/lib/mock/types";

// M11.1 — Vendor Intelligence workspace. Server Component, plain <table>
// (no DataTable) — same low-risk pattern as /finance and /executive, no
// function-valued props crossing a Server/Client boundary.

function approvalBadge(s: VendorApprovalStatus): { status: Parameters<typeof StatusBadge>[0]["status"]; label: string } {
  switch (s) {
    case "APPROVED": return { status: "COMPLIANT", label: "Approved" };
    case "PENDING": return { status: "PENDING", label: "Pending" };
    case "SUSPENDED": return { status: "NON_COMPLIANT", label: "Suspended" };
    case "NOT_APPROVED": return { status: "NON_COMPLIANT", label: "Not Approved" };
    default: return { status: "INSUFFICIENT_DATA", label: "Unknown" };
  }
}

function qualityBadge(s: VendorQualityStatus): { status: Parameters<typeof StatusBadge>[0]["status"]; label: string } {
  switch (s) {
    case "VERIFIED": return { status: "COMPLIANT", label: "Verified" };
    case "UNDER_REVIEW": return { status: "REVIEW_REQUIRED", label: "Under Review" };
    case "ISSUES_OPEN": return { status: "NON_COMPLIANT", label: "Issues Open" };
    default: return { status: "INSUFFICIENT_DATA", label: "Unknown" };
  }
}

// A deterministic, explainable procurement-risk heuristic — never a
// black-box score. UNKNOWN inputs push risk toward "Unknown", not "Low".
function vendorRisk(v: (typeof vendors)[number]): { status: Parameters<typeof StatusBadge>[0]["status"]; label: string } {
  if (v.approvalStatus === "UNKNOWN" || v.qualityStatus === "UNKNOWN") return { status: "INSUFFICIENT_DATA", label: "Unknown" };
  if (v.approvalStatus === "SUSPENDED" || v.approvalStatus === "NOT_APPROVED" || v.qualityStatus === "ISSUES_OPEN") return { status: "NON_COMPLIANT", label: "High" };
  if (v.approvalStatus === "PENDING" || v.qualityStatus === "UNDER_REVIEW") return { status: "REVIEW_REQUIRED", label: "Medium" };
  return { status: "COMPLIANT", label: "Low" };
}

export default function VendorIntelligencePage() {
  const approved = vendors.filter((v) => v.approvalStatus === "APPROVED").length;
  const aogSupport = vendors.filter((v) => v.aogSupport === true).length;
  const verifiedCert = vendors.filter((v) => v.qualityStatus === "VERIFIED").length;
  const openIssues = vendors.filter((v) => v.qualityStatus === "ISSUES_OPEN" || v.approvalStatus === "SUSPENDED").length;
  const deliveryScores = vendors.map((v) => v.deliveryScore).filter((s): s is number => s !== null);
  const avgDelivery = deliveryScores.length > 0 ? Math.round(deliveryScores.reduce((s, n) => s + n, 0) / deliveryScores.length) : null;
  const insufficientCount = vendors.filter((v) => v.approvalStatus === "UNKNOWN" || v.qualityStatus === "UNKNOWN").length;

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Procurement", href: "/procurement" }, { label: "Vendor Intelligence" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Vendor Intelligence</h1>
          <p className="ac-subtitle">Compare approved suppliers, availability, lead time, quality and procurement risk.</p>
        </div>
      </div>

      <section className="ac-section">
        <div className="ac-kpi-grid">
          <div className="ac-kpi-card"><p className="ac-kpi-label">Approved Vendors</p><p className="ac-kpi-value">{approved} / {vendors.length}</p></div>
          <div className="ac-kpi-card"><p className="ac-kpi-label">AOG Support</p><p className="ac-kpi-value">{aogSupport}</p></div>
          <div className="ac-kpi-card"><p className="ac-kpi-label">Verified Certification</p><p className="ac-kpi-value">{verifiedCert}</p></div>
          <div className="ac-kpi-card"><p className="ac-kpi-label">Open Vendor Issues</p><p className="ac-kpi-value">{openIssues}</p></div>
          <div className="ac-kpi-card"><p className="ac-kpi-label">Avg. Delivery Score</p><p className="ac-kpi-value">{avgDelivery !== null ? avgDelivery : "Insufficient source data."}</p></div>
          <div className="ac-kpi-card"><p className="ac-kpi-label">Vendors w/ Insufficient Data</p><p className="ac-kpi-value">{insufficientCount}</p></div>
        </div>
      </section>

      <div className="ac-card" style={{ padding: 0 }}>
        <table className="ac-table">
          <thead>
            <tr><th>Vendor</th><th>Approval</th><th>Quality</th><th>Lead Time</th><th>AOG</th><th>Certification</th><th>Delivery Score</th><th>Vendor Risk</th><th>Parts Available</th></tr>
          </thead>
          <tbody>
            {vendors.map((v) => {
              const lines = vendorPartAvailabilityForVendor(v.id);
              const anyVerifiedCert = lines.some((l) => l.certificationStatus === "VERIFIED");
              return (
                <tr key={v.id}>
                  <td><Link href={`/procurement/vendors/${v.id}`} className="ac-mono">{v.name}</Link></td>
                  <td><StatusBadge {...approvalBadge(v.approvalStatus)} /></td>
                  <td><StatusBadge {...qualityBadge(v.qualityStatus)} /></td>
                  <td>{v.leadTimeDays !== null ? `${v.leadTimeDays} day(s)` : "Insufficient source data."}</td>
                  <td>{v.aogSupport === null ? "Insufficient source data." : v.aogSupport ? "Yes" : "No"}</td>
                  <td>{lines.length === 0 ? "Insufficient source data." : anyVerifiedCert ? "Verified (some lines)" : "Not Verified"}</td>
                  <td>{v.deliveryScore !== null ? v.deliveryScore : "Insufficient source data."}</td>
                  <td><StatusBadge {...vendorRisk(v)} /></td>
                  <td>{lines.length > 0 ? `${lines.length} part(s)` : "Insufficient source data."}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
