import { ProspectingP2Workspace } from "@/components/prospecting/prospecting-p2-workspace";

export default async function Page({ params }: PageProps<"/prospecting/campaigns/[campaignId]">) {
  const { campaignId } = await params;
  return <ProspectingP2Workspace mode="campaign" campaignId={Number(campaignId)} />;
}
