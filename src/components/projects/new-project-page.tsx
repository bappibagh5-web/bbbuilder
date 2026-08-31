"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { useOrganization, canEditProjects } from "@/components/organizations/organization-provider";
import { OrganizationAccessState } from "@/components/organizations/organization-access-state";
import { PageHeader } from "@/components/page-header";
import { Card } from "@/components/ui/card";
import { ProductionProjectForm } from "./production-project-form";

export function NewProjectPage() {
  const router = useRouter();
  const { memberships, activeMembership } = useOrganization();
  if (!activeMembership) return <OrganizationAccessState multiple={memberships.length > 1} />;
  if (!canEditProjects(activeMembership)) return <Card className="mx-auto max-w-2xl p-8 text-center"><h1 className="text-xl font-semibold">Read-only project access</h1><p className="mt-2 text-sm text-slate-500">Your Viewer role can inspect projects but cannot create them.</p><Link href="/projects" className="mt-5 inline-flex rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white">Back to Projects</Link></Card>;
  return <div className="mx-auto max-w-5xl"><div className="flex items-start gap-4"><Link href="/projects" aria-label="Back to projects" className="mt-1 rounded-lg border bg-white p-2 text-slate-600"><ArrowLeft className="h-4 w-4" /></Link><PageHeader title="New Project" description={`Create a persistent project for ${activeMembership.organization.name}.`} /></div><Card className="mt-7 p-5 sm:p-7"><ProductionProjectForm organizationSlug={activeMembership.organization.slug} onSaved={(project) => router.push(`/projects/${project.id}`)} /></Card></div>;
}
