import type { Metadata } from "next";
import { NewProjectPage } from "@/components/projects/new-project-page";

export const metadata: Metadata = { title: "New Project" };

export default function Page() {
  return <NewProjectPage />;
}
