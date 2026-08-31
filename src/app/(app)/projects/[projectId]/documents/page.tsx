import { getProject, getProjectDocuments } from "@/data";
import { DocumentsModule } from "@/components/documents/documents-module";

export default async function Page({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  return getProject(projectId) ? <DocumentsModule projectId={projectId} initialDocuments={getProjectDocuments(projectId)} /> : null;
}
