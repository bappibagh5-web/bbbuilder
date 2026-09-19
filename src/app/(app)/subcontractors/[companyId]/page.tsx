import { SubcontractorDetail } from "@/components/subcontractors/subcontractor-detail";

export default async function Page({ params }: { params: Promise<{ companyId: string }> }) {
  const { companyId } = await params;
  return <SubcontractorDetail companyId={Number(companyId)} />;
}
