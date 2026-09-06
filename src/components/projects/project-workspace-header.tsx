import { CalendarClock, MapPin, UserRound } from "lucide-react";
import type { Project } from "@/types";
import { formatDate } from "@/lib/utils";
import { StatusBadge } from "@/components/status-badge";
import { ProgressBar } from "@/components/progress-bar";

export function ProjectWorkspaceHeader({ project }: { project: Project }) {
  return <header className="overflow-hidden rounded-2xl border border-blue-100 bg-white shadow-[0_12px_32px_rgba(15,42,67,.09)]"><div className="border-t-4 border-t-[#173f5f] p-5 sm:p-7"><div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><span className="rounded-full bg-[#173f5f] px-3 py-1 text-[11px] font-bold uppercase tracking-[.12em] text-white">{project.projectNumber}</span><span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-slate-500">Reference project</span><StatusBadge status={project.status} /></div><h1 className="mt-3 text-2xl font-semibold tracking-tight text-slate-950 sm:text-[30px]">{project.name}</h1><div className="mt-4 flex flex-wrap gap-2.5 text-sm"><Metadata icon={<UserRound />} value={project.client} /><Metadata icon={<MapPin />} value={`${project.city}, ${project.province}`} /><Metadata icon={<CalendarClock />} value={formatDate(project.bidDeadline)} /></div></div><div className="min-w-48 rounded-xl border border-slate-200 bg-slate-50/80 p-4"><div className="mb-2 flex items-center justify-between text-xs"><span className="font-semibold text-slate-600">Project progress</span><span className="font-bold text-blue-700">{project.progress}%</span></div><ProgressBar value={project.progress} /></div></div></div></header>;
}

function Metadata({ icon, value }: { icon: React.ReactNode; value: string }) {
  return <span className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50/80 px-3 py-2 text-slate-600 shadow-sm [&_svg]:h-4 [&_svg]:w-4 [&_svg]:text-blue-600">{icon}{value}</span>;
}
