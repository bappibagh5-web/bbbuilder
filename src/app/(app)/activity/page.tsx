import type { Metadata } from "next";
import { ActivityDirectory } from "@/components/activity-directory";
import { PageHeader } from "@/components/page-header";
import { globalActivity } from "@/data/global-activity";

export const metadata: Metadata = { title: "Activity" };
export default function Page() {
  return (
    <div className="mx-auto max-w-[1400px]">
      <PageHeader
        title="Activity"
        description="Review a unified history of project reviews, approvals, procurement, and awards."
      />
      <ActivityDirectory items={globalActivity} />
    </div>
  );
}
