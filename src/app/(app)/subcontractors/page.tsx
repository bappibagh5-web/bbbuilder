import { SubcontractorDirectory } from "@/components/subcontractors/subcontractor-directory";
import { subcontractors, subcontractorSummary } from "@/data";
export default function Page() {
  return (
    <SubcontractorDirectory
      initialRecords={subcontractors}
      summary={subcontractorSummary}
    />
  );
}
