import type { Metadata } from "next";
import { BidOpportunitiesModule } from "@/components/bid-opportunities/bid-opportunities-module";
import { bidOpportunities } from "@/data";

export const metadata: Metadata = { title: "Bid Opportunities" };
export default function Page() {
  return <BidOpportunitiesModule initialItems={bidOpportunities} />;
}
