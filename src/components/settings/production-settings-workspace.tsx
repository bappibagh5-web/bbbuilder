"use client";

import { useEffect, useState } from "react";
import { Building2, Link2, Mail, ShieldCheck, UserPlus } from "lucide-react";
import { OrganizationAccessState } from "@/components/organizations/organization-access-state";
import { useOrganization } from "@/components/organizations/organization-provider";
import { SettingsPanel } from "@/components/settings-panel";
import { Card } from "@/components/ui/card";
import { settingsApi, type MembershipListResponse, type MembershipRole, type OrganizationMember, type OrganizationSettingsResponse } from "@/lib/settings";

type Tab = "organization" | "users" | "email" | "integrations";
const tabs: { value: Tab; label: string; icon: typeof Building2 }[] = [
  { value: "organization", label: "Organization", icon: Building2 },
  { value: "users", label: "Users & Access", icon: ShieldCheck },
  { value: "email", label: "Email & Outreach", icon: Mail },
  { value: "integrations", label: "Integrations", icon: Link2 },
];

export function ProductionSettingsWorkspace() {
  const { memberships, activeMembership } = useOrganization();
  const [tab, setTab] = useState<Tab>("organization");
  if (!activeMembership) return <OrganizationAccessState multiple={memberships.length > 1} />;
  return (
    <div className="mt-6 space-y-5">
      <nav aria-label="Settings sections" className="flex gap-2 overflow-x-auto rounded-xl border bg-white p-2 shadow-sm">
        {tabs.map((item) => { const Icon = item.icon; return <button key={item.value} type="button" onClick={() => setTab(item.value)} className={`inline-flex shrink-0 items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold ${tab === item.value ? "bg-[#173f5f] text-white" : "text-slate-600 hover:bg-slate-100"}`} aria-current={tab === item.value ? "page" : undefined}><Icon className="h-4 w-4" />{item.label}</button>; })}
      </nav>
      {tab === "organization" && <OrganizationSection slug={activeMembership.organization.slug} />}
      {tab === "users" && <UsersAccessSection slug={activeMembership.organization.slug} />}
      {tab === "email" && <SettingsPanel section="email" />}
      {tab === "integrations" && <><SettingsPanel section="integrations" /><Card className="max-w-4xl p-6"><h2 className="font-semibold text-slate-900">Future integrations</h2><p className="mt-1 text-sm text-slate-600">Google discovery, Prospecting providers, and project-management synchronization are not configured in this checkpoint.</p></Card></>}
    </div>
  );
}

function OrganizationSection({ slug }: { slug: string }) {
  const [data, setData] = useState<OrganizationSettingsResponse | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { const controller = new AbortController(); settingsApi.organization(slug, controller.signal).then(setData).catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Organization settings could not be loaded."); }); return () => controller.abort(); }, [slug]);
  if (error) return <State title="Organization settings unavailable" detail={error} error />;
  if (!data) return <State title="Loading organization settings…" />;
  const organization = data.organization;
  return <Card className="max-w-4xl p-6"><div className="flex items-start justify-between gap-4"><div><h2 className="text-lg font-semibold text-slate-900">Organization identity</h2><p className="mt-1 text-sm text-slate-600">Core organization information used throughout BB Builders.</p></div><span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">{organization.status_label}</span></div><dl className="mt-6 grid gap-4 sm:grid-cols-2"><Detail label="Display name" value={organization.name} /><Detail label="Legal name" value={organization.legal_name || "Not provided"} /><Detail label="Organization slug" value={organization.slug} /><Detail label="Default timezone" value={organization.default_timezone} /><Detail label="Your access" value={data.access.role_label} /><Detail label="Created" value={new Date(organization.created_at).toLocaleDateString()} /></dl><p className="mt-5 rounded-lg bg-slate-50 p-3 text-sm text-slate-600">Organization identity is read-only in this checkpoint.</p></Card>;
}

function UsersAccessSection({ slug }: { slug: string }) {
  const [data, setData] = useState<MembershipListResponse | null>(null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<MembershipRole>("viewer");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const canManage = data?.can_manage_members ?? false;

  useEffect(() => { const controller = new AbortController(); settingsApi.memberships(slug, controller.signal).then(setData).catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Users & Access could not be loaded."); }); return () => controller.abort(); }, [slug]);
  async function mutate(action: () => Promise<OrganizationMember>, success: string) { setBusy(true); setError(""); setNotice(""); try { const member = await action(); setData((current) => current ? { ...current, results: current.results.some((item) => item.id === member.id) ? current.results.map((item) => item.id === member.id ? member : item) : [...current.results, member].sort((a, b) => a.email.localeCompare(b.email)) } : current); setNotice(success); } catch (reason) { setError(reason instanceof Error ? reason.message : "The access change could not be completed."); } finally { setBusy(false); } }
  async function addMember() { await mutate(() => settingsApi.addMembership(slug, email, role), "Organization access added."); setEmail(""); setRole("viewer"); }
  async function changeRole(member: OrganizationMember, next: MembershipRole) { if (next === member.role || !window.confirm(`Change ${member.email} from ${member.role_label} to ${data?.roles.find((item) => item.value === next)?.label}?`)) return; await mutate(() => settingsApi.updateMembership(slug, member.id, { role: next }), "Member role updated."); }
  async function changeStatus(member: OrganizationMember, active: boolean) { const action = active ? "reactivate" : "deactivate"; if (!window.confirm(`${action[0].toUpperCase()}${action.slice(1)} access for ${member.email}?`)) return; await mutate(() => settingsApi.updateMembership(slug, member.id, { is_active: active }), active ? "Membership reactivated." : "Membership deactivated."); }

  if (!data && !error) return <State title="Loading Users & Access…" />;
  if (!data && error) return <State title="Users & Access unavailable" detail={error} error />;
  return <div className="max-w-5xl space-y-4">{error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}{notice && <p role="status" className="rounded-lg bg-blue-50 p-3 text-sm text-blue-800">{notice}</p>}{canManage && <Card className="p-5"><div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-lg bg-blue-50 text-blue-700"><UserPlus className="h-5 w-5" /></span><div><h2 className="font-semibold">Add existing user</h2><p className="text-sm text-slate-600">The user must already have a BB Builders account. Email invitations are not implemented.</p></div></div><div className="mt-4 grid gap-3 sm:grid-cols-[1fr_220px_auto]"><input aria-label="Existing user email" type="email" value={email} disabled={busy} onChange={(event) => setEmail(event.target.value)} placeholder="existing-user@example.com" className="h-10 rounded-lg border px-3" /><select aria-label="New member role" value={role} disabled={busy} onChange={(event) => setRole(event.target.value as MembershipRole)} className="h-10 rounded-lg border bg-white px-3">{data?.roles.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select><button type="button" disabled={busy || !email.trim()} onClick={() => void addMember()} className="rounded-lg bg-[#173f5f] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Add access</button></div></Card>}
    <Card className="overflow-hidden"><div className="border-b p-5"><h2 className="font-semibold text-slate-900">Organization members</h2><p className="mt-1 text-sm text-slate-600">Access is deactivated rather than deleted so historical ownership remains intact.</p></div>{!data?.results.length ? <State title="No organization members found" detail="An active Admin must add an existing BB Builders user." /> : <div className="overflow-x-auto"><table className="w-full min-w-[850px] text-left text-sm"><thead className="bg-slate-50 text-xs uppercase text-slate-500"><tr>{["Member", "Role", "Status", "Joined", "Last login", "Actions"].map((heading) => <th key={heading} className="px-4 py-3">{heading}</th>)}</tr></thead><tbody className="divide-y">{data.results.map((member) => <tr key={member.id}><td className="px-4 py-4"><strong>{member.display_name}</strong><p className="text-xs text-slate-500">{member.email}</p></td><td className="px-4 py-4">{member.can_change_role ? <select aria-label={`Role for ${member.email}`} value={member.role} disabled={busy} onChange={(event) => void changeRole(member, event.target.value as MembershipRole)} className="rounded-lg border bg-white px-2 py-1.5">{data.roles.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select> : member.role_label}</td><td className="px-4 py-4"><span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${member.is_active ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}`}>{member.is_active ? "Active" : "Inactive"}</span></td><td className="px-4 py-4">{new Date(member.created_at).toLocaleDateString()}</td><td className="px-4 py-4">{member.last_login ? new Date(member.last_login).toLocaleString() : "Never"}</td><td className="px-4 py-4">{member.can_deactivate ? <button type="button" disabled={busy} onClick={() => void changeStatus(member, false)} className="font-semibold text-red-700 hover:underline">Deactivate</button> : member.can_reactivate ? <button type="button" disabled={busy} onClick={() => void changeStatus(member, true)} className="font-semibold text-blue-700 hover:underline">Reactivate</button> : <span className="text-xs text-slate-500">No actions</span>}</td></tr>)}</tbody></table></div>}</Card>
  </div>;
}

function Detail({ label, value }: { label: string; value: string }) { return <div className="rounded-lg border bg-white p-4"><dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</dt><dd className="mt-1 text-sm font-medium text-slate-900">{value}</dd></div>; }
function State({ title, detail, error = false }: { title: string; detail?: string; error?: boolean }) { return <Card className={`max-w-4xl p-10 text-center ${error ? "border-red-200" : ""}`}><h2 className="font-semibold text-slate-900">{title}</h2>{detail && <p className="mt-1 text-sm text-slate-500">{detail}</p>}</Card>; }
