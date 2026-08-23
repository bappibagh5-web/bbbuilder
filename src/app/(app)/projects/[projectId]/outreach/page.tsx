import {
  getProject,
  outreachTradeSummary,
  electricalRecipients,
  subcontractors,
} from "@/data";
import { OutreachModule } from "@/components/outreach/outreach-module";
export default async function Page({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return (
    <OutreachModule
      project={getProject(projectId)!}
      trades={outreachTradeSummary}
      initialRecipients={
        projectId === "retail-store-coquitlam" ? electricalRecipients : []
      }
      companies={subcontractors}
    />
  );
}
