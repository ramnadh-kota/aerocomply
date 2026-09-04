"use client";

import Link from "next/link";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { getVendorById, vendorPartAvailabilityForVendor, partRequestsForVendor } from "@/lib/mock/procurement";
import { vendorCosts, highestVendorSpend } from "@/lib/mock/finance";
import { auditEventsForObjectLabelContains } from "@/lib/mock/audit";

// M11.2 — Vendor detail. Every one of the 12 requested sections renders,
// even when the answer is "Insufficient source data." — that absence is
// itself the information, not a reason to hide the section.

function na(v: string | number | null | undefined): string {
  return v === null || v === undefined || v === "" ? "Insufficient source data." : String(v);
}

export default function VendorDetailPage({ params }: { params: { id: string } }) {
  const vendor = getVendorById(params.id);
  if (!vendor) notFound();

  const availability = vendorPartAvailabilityForVendor(vendor.id);
  const requests = partRequestsForVendor(vendor.id);
  const spendRecords = vendorCosts.filter((v) => v.vendorName === vendor.name);
  const totalSpend = spendRecords.reduce((s, v) => s + v.amount, 0);
  const topSpendOverall = highestVendorSpend();
  const auditEvents = auditEventsForObjectLabelContains(vendor.name);

  const fieldsTracked = [
    vendor.legalName, vendor.vendorCode, vendor.country, vendor.city, vendor.contactName,
    vendor.email, vendor.phone, vendor.approvedForAircraftTypes, vendor.suppliedPartCategories,
    vendor.capabilities, vendor.certifications, vendor.paymentTerms, vendor.aogSupport,
    vendor.leadTimeDays, vendor.reliabilityScore, vendor.qualityScore, vendor.deliveryScore,
  ];
  const completeness = Math.round((fieldsTracked.filter((f) => f !== null && f !== undefined).length / fieldsTracked.length) * 100);

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Procurement", href: "/procurement" }, { label: "Vendors", href: "/procurement/vendors" }, { label: vendor.name }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">{vendor.name}</h1>
          <p className="ac-subtitle">{na(vendor.legalName)} · {na(vendor.vendorCode)}</p>
        </div>
        <StatusBadge status={vendor.status === "ACTIVE" ? "ACTIVE" : "STORED"} />
      </div>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>1. Vendor Overview</h2>
        <div className="ac-card">
          <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>Location: {na(vendor.city)}{vendor.city && vendor.country ? ", " : ""}{na(vendor.country)}</p>
          <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>Contact: {na(vendor.contactName)} · {na(vendor.email)} · {na(vendor.phone)}</p>
          <p className="ac-text-sm" style={{ margin: 0 }}>Relationship: {vendor.relationshipStatus.replace(/_/g, " ")}</p>
        </div>
      </section>

      <div className="ac-grid-2 ac-section">
        <section>
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>2. Approval &amp; Quality</h2>
          <div className="ac-card">
            <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>Approval status: <StatusBadge status={vendor.approvalStatus === "APPROVED" ? "COMPLIANT" : vendor.approvalStatus === "UNKNOWN" ? "INSUFFICIENT_DATA" : vendor.approvalStatus === "PENDING" ? "PENDING" : "NON_COMPLIANT"} label={vendor.approvalStatus.replace(/_/g, " ")} /></p>
            <p className="ac-text-sm" style={{ margin: 0 }}>Quality status: <StatusBadge status={vendor.qualityStatus === "VERIFIED" ? "COMPLIANT" : vendor.qualityStatus === "UNKNOWN" ? "INSUFFICIENT_DATA" : vendor.qualityStatus === "UNDER_REVIEW" ? "REVIEW_REQUIRED" : "NON_COMPLIANT"} label={vendor.qualityStatus.replace(/_/g, " ")} /></p>
          </div>
        </section>
        <section>
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>3. Capabilities</h2>
          <div className="ac-card">
            <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>Categories: {vendor.suppliedPartCategories?.join(", ") ?? "Insufficient source data."}</p>
            <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>Capabilities: {vendor.capabilities?.join(", ") ?? "Insufficient source data."}</p>
            <p className="ac-text-sm" style={{ margin: 0 }}>Approved for: {vendor.approvedForAircraftTypes?.join(", ") ?? "Insufficient source data."}</p>
          </div>
        </section>
      </div>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>4–5. Supported Parts &amp; Availability</h2>
        <div className="ac-card" style={{ padding: 0 }}>
          {availability.length === 0 ? (
            <p className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>Insufficient source data. No parts availability recorded for this vendor.</p>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table className="ac-table">
                <thead><tr><th>Part</th><th>Availability</th><th>Qty Available</th><th>Lead Time</th><th>Unit Price</th><th>Certification</th><th>AOG</th></tr></thead>
                <tbody>
                  {availability.map((a) => (
                    <tr key={a.id}>
                      <td>{a.partId ? <Link href={`/maintenance/parts/${a.partId}`} className="ac-mono">{a.partNumber}</Link> : <span className="ac-mono">{a.partNumber}</span>}</td>
                      <td>{a.availabilityStatus.replace(/_/g, " ")}</td>
                      <td>{na(a.quantityAvailable)}</td>
                      <td>{a.leadTimeDays !== null ? `${a.leadTimeDays} day(s)` : "Insufficient source data."}</td>
                      <td>{a.unitPrice !== null ? `${a.currency ?? ""} ${a.unitPrice}` : "Insufficient source data."}</td>
                      <td>{a.certificationStatus.replace(/_/g, " ")}</td>
                      <td>{a.aogAvailability === null ? "Insufficient source data." : a.aogAvailability ? "Yes" : "No"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      <div className="ac-grid-2 ac-section">
        <section>
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>6. Commercial Terms</h2>
          <div className="ac-card">
            <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>Payment terms: {na(vendor.paymentTerms)}</p>
            <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>Currency: {na(vendor.currency)}</p>
            <p className="ac-text-sm" style={{ margin: 0 }}>Shipping regions: {vendor.shippingRegions?.join(", ") ?? "Insufficient source data."}</p>
          </div>
        </section>
        <section>
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>7–8. Delivery Performance &amp; AOG Support</h2>
          <div className="ac-card">
            <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>Delivery score: {na(vendor.deliveryScore)}</p>
            <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>Reliability score: {na(vendor.reliabilityScore)}</p>
            <p className="ac-text-sm" style={{ margin: 0 }}>AOG support: {vendor.aogSupport === null ? "Insufficient source data." : vendor.aogSupport ? "Confirmed" : "Not offered"}</p>
          </div>
        </section>
      </div>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>9. Compliance / Certification</h2>
        <div className="ac-card">
          <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
            {vendor.certifications?.join(", ") ?? "Insufficient source data."} — vendor-level certification claims are demo-labeled and have not been verified against a real regulatory registry.
          </p>
        </div>
      </section>

      <div className="ac-grid-2 ac-section">
        <section>
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>10. Procurement History</h2>
          <div className="ac-card">
            <p className="ac-text-sm" style={{ margin: "0 0 6px" }}>Total recorded spend: {spendRecords.length > 0 ? `USD ${totalSpend.toLocaleString()}` : "Insufficient source data."}</p>
            {topSpendOverall?.vendorName === vendor.name && <p className="ac-text-sm" style={{ margin: "0 0 6px" }}>This vendor has the highest single recorded vendor line item fleet-wide.</p>}
            <p className="ac-text-sm" style={{ margin: 0 }}>Part requests referencing this vendor: {requests.length > 0 ? requests.map((r) => <Link key={r.id} href={`/aircraft/${r.aircraftId}`} className="ac-mono" style={{ marginRight: 6 }}>{r.partNumber}</Link>) : "Insufficient source data."}</p>
          </div>
        </section>
        <section>
          <h2 className="ac-h2" style={{ marginBottom: 10 }}>11. Audit Timeline</h2>
          <div className="ac-card">
            {auditEvents.length === 0 ? <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Insufficient source data. No audit events reference this vendor by name.</p> : (
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
                {auditEvents.slice(0, 5).map((e) => <li key={e.id}>{e.timestamp}: {e.action.replace(/_/g, " ")}</li>)}
              </ul>
            )}
          </div>
        </section>
      </div>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>12. Data Completeness</h2>
        <div className="ac-card">
          <div className="ac-flex ac-items-center ac-gap-3">
            <p className="ac-kpi-value" style={{ fontSize: 28, margin: 0 }}>{completeness}%</p>
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>of tracked vendor fields have a recorded value. The rest show &ldquo;Insufficient source data.&rdquo; above rather than an assumed default.</p>
          </div>
        </div>
      </section>
    </div>
  );
}
