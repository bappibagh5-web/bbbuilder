import type { Metadata } from "next";
import { PageHeader } from "@/components/page-header";
import { SettingsPanel } from "@/components/settings-panel";

export const metadata: Metadata = { title: "Settings" };
export default function Page() {
  return (
    <div className="mx-auto max-w-[1400px]">
      <PageHeader
        title="Settings"
        description="Review the organization and workflow defaults used throughout this demonstration."
      />
      <SettingsPanel />
    </div>
  );
}
