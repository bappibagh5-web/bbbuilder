import { AwardedDirectory } from "@/components/awarded/awarded-directory";
import { awardedProjects, awardedSummary } from "@/data";
export default function Page() {
  return <AwardedDirectory items={awardedProjects} summary={awardedSummary} />;
}
