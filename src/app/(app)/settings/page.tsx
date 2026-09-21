import type { Metadata } from "next";
import { PageHeader } from "@/components/page-header";
import { ProductionSettingsWorkspace } from "@/components/settings/production-settings-workspace";

export const metadata: Metadata = { title: "Settings" };
export default function Page() {
  return (
    <div className="mx-auto max-w-[1400px]">
      <PageHeader
        title="Settings"
        description="Manage organization identity, user access, outreach email, and integrations."
      />
      <ProductionSettingsWorkspace />
    </div>
  );
}
