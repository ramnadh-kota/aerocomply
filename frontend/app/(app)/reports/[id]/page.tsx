import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { ReportView } from "@/components/reports/ReportView";
import { buildReportData } from "@/lib/mock/reports";

export default function ReportDetailPage({ params }: { params: { id: string } }) {
  const report = buildReportData(params.id);
  if (!report) notFound();

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Reports", href: "/reports" }, { label: report.title }]} />
      <ReportView report={report} />
    </div>
  );
}
