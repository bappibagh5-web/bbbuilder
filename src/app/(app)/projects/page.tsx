import type { Metadata } from "next";
import { ProjectsPageContent } from "@/components/projects/projects-page-content";

export const metadata: Metadata = { title: "Projects" };

export default function Page() {
  return <ProjectsPageContent />;
}
