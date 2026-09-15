import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { ReportView } from "@/components/reports/ReportView";
import { buildReportData } from "@/lib/mock/reports";

export default async function ReportDetailPage(props: { params: Promise<{ id: string }> }) {
  const params = await props.params;
  const report = buildReportData(params.id);
  if (!report) notFound();

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Reports", href: "/reports" }, { label: report.title }]} />
      <ReportView report={report} />
    </div>
  );
}
