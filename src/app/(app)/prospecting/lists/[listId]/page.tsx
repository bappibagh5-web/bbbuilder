import { ProspectingWorkspace } from "@/components/prospecting/prospecting-workspace";

export default async function ProspectingListPage({ params }: PageProps<"/prospecting/lists/[listId]">) {
  const { listId } = await params;
  return <ProspectingWorkspace mode="detail" listId={Number(listId)} />;
}
