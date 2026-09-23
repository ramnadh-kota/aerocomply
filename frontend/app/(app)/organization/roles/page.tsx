import { redirect } from "next/navigation";

export default function RolesRedirectPage() {
  redirect("/tenant/roles");
}
