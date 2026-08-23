import { ComparisonDirectory } from "@/components/comparisons/comparison-directory";
import { comparisonQueue, comparisonSummary } from "@/data";
export default function Page() {
  return (
    <ComparisonDirectory items={comparisonQueue} summary={comparisonSummary} />
  );
}
