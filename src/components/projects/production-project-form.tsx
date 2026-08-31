"use client";

import { useMemo, useState } from "react";
import { ApiError } from "@/lib/api-client";
import { instantToLocalInput, zonedLocalDateTimeToIso } from "@/lib/project-time";
import { projectsApi, type AreaUnitCode, type ProductionProject, type ProjectTypeCode, type ProjectWritePayload } from "@/lib/projects";

type FormState = {
  project_number: string; name: string; project_timezone: string; client_name: string;
  project_type: ProjectTypeCode; description: string; site_address_line_1: string;
  site_address_line_2: string; city: string; province_state: string; postal_zip_code: string;
  country: string; estimated_area: string; area_unit: AreaUnitCode; bid_deadline: string;
  questions_deadline: string; site_visit_date: string; planned_start_date: string;
  substantial_completion_date: string; opening_or_handover_date: string;
};

const commonTimezones = ["America/Vancouver", "America/Edmonton", "America/Winnipeg", "America/Toronto", "America/Halifax", "America/St_Johns", "UTC"];
const inputClass = "h-10 w-full rounded-lg border bg-white px-3 text-sm outline-none focus:border-slate-500 disabled:bg-slate-50 disabled:text-slate-500";

function initialState(project?: ProductionProject): FormState {
  const browserTimezone = typeof Intl !== "undefined" ? Intl.DateTimeFormat().resolvedOptions().timeZone : "";
  const timezone = project?.project_timezone ?? browserTimezone;
  return {
    project_number: project?.project_number ?? "", name: project?.name ?? "",
    project_timezone: timezone, client_name: project?.client_name ?? "",
    project_type: project?.project_type ?? "other", description: project?.description ?? "",
    site_address_line_1: project?.site_address_line_1 ?? "", site_address_line_2: project?.site_address_line_2 ?? "",
    city: project?.city ?? "", province_state: project?.province_state ?? "",
    postal_zip_code: project?.postal_zip_code ?? "", country: project?.country ?? "CA",
    estimated_area: project?.estimated_area ?? "", area_unit: project?.area_unit ?? "sf",
    bid_deadline: project ? instantToLocalInput(project.bid_deadline, timezone) : "",
    questions_deadline: project ? instantToLocalInput(project.questions_deadline, timezone) : "",
    site_visit_date: project?.site_visit_date ?? "", planned_start_date: project?.planned_start_date ?? "",
    substantial_completion_date: project?.substantial_completion_date ?? "",
    opening_or_handover_date: project?.opening_or_handover_date ?? "",
  };
}

export function ProductionProjectForm({ organizationSlug, project, onSaved, onCancel }: { organizationSlug: string; project?: ProductionProject; onSaved: (project: ProductionProject) => void; onCancel?: () => void }) {
  const [form, setForm] = useState(() => initialState(project));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const editing = Boolean(project);
  const timezoneOptions = useMemo(() => form.project_timezone && !commonTimezones.includes(form.project_timezone) ? [form.project_timezone, ...commonTimezones] : commonTimezones, [form.project_timezone]);
  const set = <Key extends keyof FormState>(key: Key, value: FormState[Key]) => setForm((current) => ({ ...current, [key]: value }));

  function validate() {
    const next: Record<string, string> = {};
    if (!form.project_number.trim()) next.project_number = "Project number is required.";
    if (!form.name.trim()) next.name = "Project name is required.";
    if (!form.project_timezone.trim()) next.project_timezone = "Project timezone is required.";
    else { try { new Intl.DateTimeFormat("en", { timeZone: form.project_timezone }).format(); } catch { next.project_timezone = "Enter a valid IANA timezone."; } }
    if (form.estimated_area && Number(form.estimated_area) <= 0) next.estimated_area = "Area must be greater than zero.";
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  function payload(): ProjectWritePayload {
    const optionalDateTime = (value: string) => value ? zonedLocalDateTimeToIso(value, form.project_timezone) : null;
    const optionalDate = (value: string) => value || null;
    return {
      project_number: form.project_number.trim(), name: form.name.trim(), project_timezone: form.project_timezone.trim(),
      client_name: form.client_name.trim(), project_type: form.project_type, description: form.description.trim(),
      site_address_line_1: form.site_address_line_1.trim(), site_address_line_2: form.site_address_line_2.trim(),
      city: form.city.trim(), province_state: form.province_state.trim(), postal_zip_code: form.postal_zip_code.trim(),
      country: form.country.trim().toUpperCase() || "CA", estimated_area: form.estimated_area || null,
      area_unit: form.area_unit, bid_deadline: optionalDateTime(form.bid_deadline),
      questions_deadline: optionalDateTime(form.questions_deadline), site_visit_date: optionalDate(form.site_visit_date),
      planned_start_date: optionalDate(form.planned_start_date), substantial_completion_date: optionalDate(form.substantial_completion_date),
      opening_or_handover_date: optionalDate(form.opening_or_handover_date),
    };
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (submitting || !validate()) return;
    setSubmitting(true); setSubmitError(null); setErrors({});
    try {
      const body = payload();
      const saved = project ? await projectsApi.update(organizationSlug, project.id, body) : await projectsApi.create(organizationSlug, body);
      onSaved(saved);
    } catch (reason) {
      if (reason instanceof ApiError) {
        const payload = reason.payload;
        if (payload && typeof payload === "object" && !Array.isArray(payload)) {
          const fieldErrors: Record<string, string> = {};
          for (const [key, value] of Object.entries(payload)) {
            if (Array.isArray(value) && value.length) fieldErrors[key] = String(value[0]);
            else if (typeof value === "string") fieldErrors[key] = value;
          }
          if (Object.keys(fieldErrors).length) setErrors(fieldErrors);
        }
        setSubmitError(reason.status === 403 ? "You do not have permission to save this project." : reason.message);
      } else setSubmitError(reason instanceof Error ? reason.message : "The project could not be saved.");
    } finally { setSubmitting(false); }
  }

  return (
    <form onSubmit={submit} className="space-y-6">
      {submitError && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{submitError}</div>}
      <Section title="Project information" description="Core identity and client details."><Field label="Project number" required error={errors.project_number}><input value={form.project_number} onChange={(e) => set("project_number", e.target.value)} className={inputClass} /></Field><Field label="Project name" required error={errors.name}><input value={form.name} onChange={(e) => set("name", e.target.value)} className={inputClass} /></Field><Field label="Client"><input value={form.client_name} onChange={(e) => set("client_name", e.target.value)} className={inputClass} /></Field><Field label="Project type"><select value={form.project_type} onChange={(e) => set("project_type", e.target.value as ProjectTypeCode)} className={inputClass}><option value="retail">Retail</option><option value="restaurant">Restaurant</option><option value="office">Office</option><option value="commercial">Commercial</option><option value="other">Other</option></select></Field><div className="sm:col-span-2"><Field label="Description"><textarea value={form.description} onChange={(e) => set("description", e.target.value)} rows={4} className="w-full rounded-lg border bg-white px-3 py-2 text-sm outline-none focus:border-slate-500" /></Field></div></Section>
      <Section title="Location and timezone" description="Deadlines are interpreted in the project timezone."><Field label="Address line 1"><input value={form.site_address_line_1} onChange={(e) => set("site_address_line_1", e.target.value)} className={inputClass} /></Field><Field label="Address line 2"><input value={form.site_address_line_2} onChange={(e) => set("site_address_line_2", e.target.value)} className={inputClass} /></Field><Field label="City"><input value={form.city} onChange={(e) => set("city", e.target.value)} className={inputClass} /></Field><Field label="Province / state"><input value={form.province_state} onChange={(e) => set("province_state", e.target.value)} className={inputClass} /></Field><Field label="Postal / ZIP code"><input value={form.postal_zip_code} onChange={(e) => set("postal_zip_code", e.target.value)} className={inputClass} /></Field><Field label="Country code"><input value={form.country} maxLength={2} onChange={(e) => set("country", e.target.value)} className={inputClass} /></Field><Field label="Project timezone" required error={errors.project_timezone}><input list="project-timezones" value={form.project_timezone} onChange={(e) => set("project_timezone", e.target.value)} placeholder="America/Vancouver" className={inputClass} /><datalist id="project-timezones">{timezoneOptions.map((zone) => <option key={zone} value={zone} />)}</datalist></Field><div /></Section>
      <Section title="Characteristics" description="Optional project size information."><Field label="Estimated area" error={errors.estimated_area}><input type="number" min="0.01" step="0.01" value={form.estimated_area} onChange={(e) => set("estimated_area", e.target.value)} className={inputClass} /></Field><Field label="Area unit"><select value={form.area_unit} onChange={(e) => set("area_unit", e.target.value as AreaUnitCode)} className={inputClass}><option value="sf">Square feet</option><option value="m2">Square metres</option></select></Field></Section>
      <Section title="Tender deadlines" description="Enter local project times; the API receives an explicit UTC offset."><Field label="Bid deadline" error={errors.bid_deadline}><input type="datetime-local" value={form.bid_deadline} onChange={(e) => set("bid_deadline", e.target.value)} className={inputClass} /></Field><Field label="Questions deadline" error={errors.questions_deadline}><input type="datetime-local" value={form.questions_deadline} onChange={(e) => set("questions_deadline", e.target.value)} className={inputClass} /></Field></Section>
      <Section title="Milestone dates" description="These remain date-only values."><Field label="Site visit"><input type="date" value={form.site_visit_date} onChange={(e) => set("site_visit_date", e.target.value)} className={inputClass} /></Field><Field label="Planned start"><input type="date" value={form.planned_start_date} onChange={(e) => set("planned_start_date", e.target.value)} className={inputClass} /></Field><Field label="Substantial completion"><input type="date" value={form.substantial_completion_date} onChange={(e) => set("substantial_completion_date", e.target.value)} className={inputClass} /></Field><Field label="Opening / handover"><input type="date" value={form.opening_or_handover_date} onChange={(e) => set("opening_or_handover_date", e.target.value)} className={inputClass} /></Field></Section>
      <div className="flex flex-col-reverse gap-3 border-t pt-5 sm:flex-row sm:justify-end">{onCancel && <button type="button" onClick={onCancel} disabled={submitting} className="h-10 rounded-lg border bg-white px-4 text-sm font-semibold text-slate-700">Cancel</button>}<button type="submit" disabled={submitting} className="h-10 rounded-lg bg-primary px-5 text-sm font-semibold text-white disabled:opacity-60">{submitting ? "Saving…" : editing ? "Save Changes" : "Create Project"}</button></div>
    </form>
  );
}

function Section({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  return <section className="rounded-xl border"><div className="border-b bg-slate-50 px-4 py-3"><h2 className="font-semibold text-slate-900">{title}</h2><p className="mt-0.5 text-xs text-slate-500">{description}</p></div><div className="grid gap-5 p-4 sm:grid-cols-2">{children}</div></section>;
}

function Field({ label, required, error, children }: { label: string; required?: boolean; error?: string; children: React.ReactNode }) {
  return <label className="block"><span className="mb-1.5 block text-sm font-medium text-slate-700">{label}{required && <span className="text-red-600"> *</span>}</span>{children}{error && <span className="mt-1 block text-xs text-red-600">{error}</span>}</label>;
}
