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
  const demoProject = getProject(projectId);
  if (!demoProject) return null;
  return (
    <OutreachModule
      project={demoProject}
      trades={outreachTradeSummary}
      initialRecipients={
        projectId === "retail-store-coquitlam" ? electricalRecipients : []
      }
      companies={subcontractors}
    />
  );
}
