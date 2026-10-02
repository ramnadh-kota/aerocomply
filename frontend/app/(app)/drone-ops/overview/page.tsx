import { OperationsOverview } from "@/components/drone-ops/OperationsOverview";

export const metadata = {
  title: "Operations Overview — Drone Operations — Kota Aerospace",
  description: "Live fleet status, active missions, alerts, and telemetry overview for the Kota Aerospace drone fleet.",
};

// This page uses client-side simulation; mark it as a client-rendered page
// by ensuring OperationsOverview (which uses useEffect) is the primary component.
// The page itself can remain a server component since it just renders the client
// component root.
export default function OperationsOverviewPage() {
  return <OperationsOverview />;
}
