import { redirect } from "next/navigation";

// Root /drone-ops → redirect to Operations Overview.
export default function DroneOpsRoot() {
  redirect("/drone-ops/overview");
}
