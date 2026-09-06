"use client";

import { ArrowLeft, Building2, Mail, MapPin, Phone, Search, Star } from "lucide-react";
import { useState } from "react";

import { Card } from "@/components/ui/card";
import type {
  ContractorCompanyProfile,
  ContractorContact,
  ContractorContactInput,
  ContractorContactEnrichment,
  ContractorContactSuggestion,
} from "@/lib/contractors";

type ContactForm = {
  name: string;
  title: string;
  email: string;
  phone: string;
  is_primary: boolean;
  is_active: boolean;
};

const emptyContact: ContactForm = {
  name: "",
  title: "",
  email: "",
  phone: "",
  is_primary: false,
  is_active: true,
};

export function ContractorProfilePanel({
  profile,
  canManage,
  busy,
  onBack,
  onSave,
  onFindContactDetails,
}: {
  profile: ContractorCompanyProfile;
  canManage: boolean;
  busy: boolean;
  onBack: () => void;
  onSave: (contactId: number | null, input: ContractorContactInput) => Promise<void>;
  onFindContactDetails: () => Promise<ContractorContactEnrichment>;
}) {
  const [editingId, setEditingId] = useState<number | "new" | null>(null);
  const [form, setForm] = useState<ContactForm>(emptyContact);
  const [enrichment, setEnrichment] = useState<ContractorContactEnrichment | null>(null);
  const [enriching, setEnriching] = useState(false);
  const isGoogle = profile.source_type === "discovered" && profile.external_provider === "google_places";

  function startNew() {
    setEditingId("new");
    setForm(emptyContact);
  }

  function applySuggestion(suggestion: ContractorContactSuggestion) {
    setEditingId("new");
    setForm({ name: suggestion.name, title: suggestion.title, email: suggestion.email, phone: suggestion.phone, is_primary: suggestion.is_primary, is_active: suggestion.is_active });
  }

  async function findContactDetails() {
    setEnriching(true);
    try {
      const result = await onFindContactDetails();
      setEnrichment(result);
      if (result.suggestions[0]) applySuggestion(result.suggestions[0]);
    } finally {
      setEnriching(false);
    }
  }

  function startEdit(contact: ContractorContact) {
    setEditingId(contact.id);
    setForm({
      name: contact.name,
      title: contact.title,
      email: contact.email,
      phone: contact.phone,
      is_primary: contact.is_primary,
      is_active: contact.is_active,
    });
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onSave(editingId === "new" ? null : editingId, form);
    setEditingId(null);
  }

  return (
    <Card className="overflow-hidden border-blue-200 shadow-md">
      <div className="border-b bg-slate-50 p-5">
        <button type="button" onClick={onBack} className="inline-flex items-center gap-2 text-sm font-semibold text-blue-700 hover:text-blue-900">
          <ArrowLeft className="h-4 w-4" /> Back to trade candidates
        </button>
        <div className="mt-4 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-xl font-semibold text-slate-950">{profile.display_name}</h3>
              <span className={`rounded-full px-2 py-1 text-[10px] font-bold uppercase ${profile.source_type === "internal" ? "bg-blue-100 text-blue-700" : "bg-indigo-100 text-indigo-700"}`}>
                {profile.source_type === "internal" ? "Internal" : "Google"}
              </span>
              <span className={`rounded-full px-2 py-1 text-[10px] font-bold uppercase ${profile.contact_ready ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>
                {profile.contact_ready ? "Contact ready" : "Missing contact"}
              </span>
            </div>
            <p className="mt-2 flex items-center gap-2 text-sm text-slate-600"><MapPin className="h-4 w-4" />{profile.address || `${profile.city}, ${profile.province}`}</p>
            {profile.phone && <p className="mt-1 flex items-center gap-2 text-sm text-slate-600"><Phone className="h-4 w-4" />{profile.phone}</p>}
            {profile.website && <a href={profile.website} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-2 text-sm font-semibold text-blue-700 hover:underline"><Building2 className="h-4 w-4" />Visit website</a>}
            {profile.google_rating !== null && <p className="mt-2 flex items-center gap-2 text-sm font-medium text-slate-700"><Star className="h-4 w-4 fill-amber-400 text-amber-400" />Google {profile.google_rating.toFixed(1)}{profile.google_review_count !== null ? ` · ${profile.google_review_count} reviews` : ""}</p>}
          </div>
          <div className="text-sm sm:text-right">
            <p className="font-semibold text-slate-900">Shortlist status</p>
            {profile.shortlist_statuses.map((item) => <p key={item.scope_package} className="mt-1 text-slate-600">{item.trade_category}: <span className="font-semibold capitalize">{item.status.replaceAll("_", " ")}</span></p>)}
          </div>
        </div>
      </div>

      <div className="grid gap-6 p-5 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
        <section>
          <h4 className="font-semibold text-slate-950">Trade capabilities</h4>
          <div className="mt-3 flex flex-wrap gap-2">
            {profile.trade_capabilities.filter((item) => item.is_active).map((capability) => <span key={capability.id} className="rounded-full bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700">{capability.trade_label}</span>)}
          </div>
        </section>

        <section>
          <div className="flex items-center justify-between gap-3">
            <div><h4 className="font-semibold text-slate-950">Contacts</h4><p className="mt-1 text-xs text-slate-500">Contact ready requires an active primary contact with an email or phone.</p></div>
            {canManage && <div className="flex flex-wrap gap-2">{isGoogle && <button type="button" onClick={findContactDetails} disabled={busy || enriching || !profile.website} className="inline-flex items-center gap-2 rounded-lg bg-[#173f5f] px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"><Search className="h-4 w-4" />{enriching ? "Checking public sources…" : "Find Contact Details"}</button>}<button type="button" onClick={startNew} className={`${isGoogle ? "border border-slate-200 bg-white text-slate-700" : "bg-[#173f5f] text-white"} rounded-lg px-3 py-2 text-sm font-semibold`}>{isGoogle ? "Add manually" : "Add contact"}</button></div>}
          </div>
          {enrichment && <div className="mt-3 rounded-xl border border-indigo-200 bg-indigo-50/40 p-4">{enrichment.suggestions.length === 0 ? <><p className="font-semibold text-slate-900">No public contact found</p><p className="mt-1 text-sm text-slate-600">Add a contact manually if you have verified details.</p></> : <><p className="font-semibold text-slate-900">Suggested public contact details</p><p className="mt-1 text-xs text-slate-500">Review and confirm before saving. Nothing is saved automatically.</p><div className="mt-3 space-y-2">{enrichment.suggestions.map((suggestion) => <div key={`${suggestion.email}-${suggestion.phone}`} className="rounded-lg border bg-white p-3"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-sm font-semibold text-slate-900">{suggestion.name}</p>{suggestion.title && <p className="text-xs text-slate-500">{suggestion.title}</p>}<p className="mt-1 text-xs text-slate-600">{suggestion.email}{suggestion.phone ? ` · ${suggestion.phone}` : ""}</p>{suggestion.sources.map((source) => <a key={source.url} href={source.url} target="_blank" rel="noreferrer" className="mt-1 block text-xs font-semibold text-blue-700">Source: {source.label}</a>)}</div><button type="button" onClick={() => applySuggestion(suggestion)} className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-xs font-semibold text-blue-700">Use suggestion</button></div></div>)}</div></>}</div>}
          <div className="mt-3 space-y-3">
            {profile.contacts.length === 0 && <div className="rounded-lg border border-dashed p-4 text-sm text-slate-500">No contacts have been added.</div>}
            {profile.contacts.map((contact) => <div key={contact.id} className={`rounded-lg border p-4 ${contact.is_active ? "bg-white" : "bg-slate-50 opacity-70"}`}><div className="flex items-start justify-between gap-3"><div><div className="flex flex-wrap items-center gap-2"><p className="font-semibold text-slate-900">{contact.name}</p>{contact.is_primary && <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-bold uppercase text-emerald-700">Primary</span>}<span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${contact.is_active ? "bg-blue-50 text-blue-700" : "bg-slate-200 text-slate-600"}`}>{contact.is_active ? "Active" : "Inactive"}</span></div>{contact.title && <p className="mt-1 text-sm text-slate-500">{contact.title}</p>}{contact.email && <a href={`mailto:${contact.email}`} className="mt-2 flex items-center gap-2 text-sm text-blue-700"><Mail className="h-4 w-4" />{contact.email}</a>}{contact.phone && <p className="mt-1 flex items-center gap-2 text-sm text-slate-600"><Phone className="h-4 w-4" />{contact.phone}</p>}</div>{canManage && <button type="button" onClick={() => startEdit(contact)} className="text-sm font-semibold text-blue-700">Edit contact</button>}</div></div>)}
          </div>

          {canManage && editingId !== null && <form onSubmit={submit} className="mt-4 grid gap-3 rounded-xl border border-blue-200 bg-blue-50/40 p-4 sm:grid-cols-2"><label className="text-xs font-semibold text-slate-700">Name<input required value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} className="mt-1 h-10 w-full rounded-lg border bg-white px-3 text-sm" /></label><label className="text-xs font-semibold text-slate-700">Title / role<input value={form.title} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} className="mt-1 h-10 w-full rounded-lg border bg-white px-3 text-sm" /></label><label className="text-xs font-semibold text-slate-700">Email<input type="email" value={form.email} onChange={(event) => setForm((current) => ({ ...current, email: event.target.value }))} className="mt-1 h-10 w-full rounded-lg border bg-white px-3 text-sm" /></label><label className="text-xs font-semibold text-slate-700">Phone<input value={form.phone} onChange={(event) => setForm((current) => ({ ...current, phone: event.target.value }))} className="mt-1 h-10 w-full rounded-lg border bg-white px-3 text-sm" /></label><label className="inline-flex items-center gap-2 text-sm font-medium text-slate-700"><input type="checkbox" checked={form.is_primary} onChange={(event) => setForm((current) => ({ ...current, is_primary: event.target.checked }))} />Primary contact</label><label className="inline-flex items-center gap-2 text-sm font-medium text-slate-700"><input type="checkbox" checked={form.is_active} onChange={(event) => setForm((current) => ({ ...current, is_active: event.target.checked }))} />Active</label><div className="flex gap-2 sm:col-span-2"><button type="submit" disabled={busy} className="rounded-lg bg-[#173f5f] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy ? "Saving…" : "Save contact"}</button><button type="button" onClick={() => setEditingId(null)} className="rounded-lg border bg-white px-4 py-2 text-sm font-semibold text-slate-700">Cancel</button></div></form>}
        </section>
      </div>
    </Card>
  );
}
