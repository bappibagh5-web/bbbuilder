import { CampaignDirectory } from "@/components/campaigns/campaign-directory";
import { outreachCampaigns, campaignSummary } from "@/data";
export default function Page() {
  return (
    <CampaignDirectory
      campaigns={outreachCampaigns}
      summary={campaignSummary}
    />
  );
}
