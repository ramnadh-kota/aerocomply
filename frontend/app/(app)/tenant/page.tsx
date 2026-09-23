import { redirect } from "next/navigation";

export default function TenantRootPage() {
  redirect("/tenant/dashboard");
}
