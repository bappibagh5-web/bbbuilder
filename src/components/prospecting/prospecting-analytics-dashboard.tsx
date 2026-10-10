"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { AnalyticsCampaign, AnalyticsMetrics, AnalyticsRange, AnalyticsRecipient, prospectingApi } from "@/lib/prospecting";

const ranges: { value: AnalyticsRange; label: string }[] = [{ value: "7d", label: "Last 7 days" }, { value: "30d", label: "Last 30 days" }, { value: "90d", label: "Last 90 days" }, { value: "all", label: "All time" }];
const filters = ["all", "opened", "clicked", "replied", "bounced", "unsubscribed", "not_opened"];

export function ProspectingAnalyticsDashboard({ slug }: { slug: string }) {
  const [range, setRange] = useState<AnalyticsRange>("30d");
  const [sort, setSort] = useState("newest");
  const [overview, setOverview] = useState<Awaited<ReturnType<typeof prospectingApi.analytics>> | null>(null);
  const [campaigns, setCampaigns] = useState<AnalyticsCampaign[]>([]);
  const [selectedCampaign, setSelectedCampaign] = useState<number | null>(null);
  const [campaignDetail, setCampaignDetail] = useState<Awaited<ReturnType<typeof prospectingApi.analyticsCampaign>> | null>(null);
  const [engagement, setEngagement] = useState("all");
  const [search, setSearch] = useState("");
  const [recipients, setRecipients] = useState<AnalyticsRecipient[]>([]);
  const [recipientCount, setRecipientCount] = useState(0);
  const [recipientPage, setRecipientPage] = useState(1);
  const [selectedRecipient, setSelectedRecipient] = useState<number | null>(null);
  const [recipientDetail, setRecipientDetail] = useState<Awaited<ReturnType<typeof prospectingApi.analyticsRecipient>> | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([prospectingApi.analytics(slug, range), prospectingApi.analyticsCampaigns(slug, range, sort)])
      .then(([summary, campaignData]) => { if (active) { setOverview(summary); setCampaigns(campaignData.results); } })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "Analytics could not be loaded."); })
    return () => { active = false; };
  }, [slug, range, sort]);

  useEffect(() => {
    const query = new URLSearchParams({ range, engagement, search, page: String(recipientPage) });
    if (selectedCampaign) query.set("campaign", String(selectedCampaign));
    const timer = window.setTimeout(() => {
      prospectingApi.analyticsRecipients(slug, query).then((data) => { setRecipients(data.results); setRecipientCount(data.count); }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Recipient engagement could not be loaded."));
    }, 200);
    return () => window.clearTimeout(timer);
  }, [slug, range, engagement, search, selectedCampaign, recipientPage]);

  useEffect(() => {
    if (selectedCampaign) void prospectingApi.analyticsCampaign(slug, selectedCampaign, range).then(setCampaignDetail).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Campaign analytics could not be loaded."));
  }, [slug, selectedCampaign, range]);

  useEffect(() => {
    if (selectedRecipient) void prospectingApi.analyticsRecipient(slug, selectedRecipient).then(setRecipientDetail).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Recipient activity could not be loaded."));
  }, [slug, selectedRecipient]);

  if (!overview && !error) return <Notice text="Loading Prospecting analytics…" />;
  if (error && !overview) return <Notice text={error} error />;
  if (!overview) return null;
  const summary = overview.summary;
  return <div className="space-y-6">
    <header className="flex flex-wrap items-end justify-between gap-4"><div><h2 className="text-2xl font-bold text-slate-950">Prospecting Analytics</h2><p className="mt-1 text-sm text-slate-600">Performance across cold-email campaigns</p></div><select aria-label="Analytics period" value={range} onChange={(event) => { setRange(event.target.value as AnalyticsRange); setRecipientPage(1); }} className="h-10 rounded-lg border bg-white px-3 text-sm font-semibold">{ranges.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></header>
    {error && <Notice text={error} error />}
    {!summary.messages_sent && !campaigns.length ? <Notice text="No campaigns yet. Analytics will appear after a campaign is created." /> : <>
      <MetricGrid metrics={summary} />
      <TrackingStatus metrics={summary} />
      <Trend rows={overview.trend} />
      <CampaignTable campaigns={campaigns} sort={sort} onSort={setSort} selected={selectedCampaign} onSelect={(id) => { setCampaignDetail(null); setSelectedCampaign(selectedCampaign === id ? null : id); setRecipientPage(1); }} />
      {selectedCampaign && <CampaignDetail data={campaignDetail?.campaign.id === selectedCampaign && campaignDetail.range === range ? campaignDetail : null} />}
      <RecipientEngagement recipients={recipients} count={recipientCount} page={recipientPage} setPage={setRecipientPage} engagement={engagement} setEngagement={(value) => { setEngagement(value); setRecipientPage(1); }} search={search} setSearch={(value) => { setSearch(value); setRecipientPage(1); }} onSelect={(id) => { setRecipientDetail(null); setSelectedRecipient(id); }} />
    </>}
    {selectedRecipient && <RecipientDrawer data={recipientDetail?.recipient.id === selectedRecipient ? recipientDetail : null} onClose={() => setSelectedRecipient(null)} />}
  </div>;
}

function MetricGrid({ metrics }: { metrics: AnalyticsMetrics }) {
  const cards = [
    ["Prospects contacted", metrics.prospects_contacted, null], ["Emails sent", metrics.messages_sent, null],
    ["Delivered", metrics.delivered, metrics.rates.delivery], ["Opened", metrics.opened, metrics.rates.open],
    ["Clicked", metrics.clicked, metrics.rates.click], ["Replied", metrics.replied, metrics.rates.reply],
    ["Bounced", metrics.bounced, metrics.rates.bounce], ["Unsubscribed", metrics.unsubscribed, metrics.rates.unsubscribe],
  ] as const;
  return <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{cards.map(([label, value, rate]) => <Card key={label} className="p-4"><p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</p><div className="mt-2 flex items-end justify-between"><strong className="text-2xl text-slate-950">{value.toLocaleString()}</strong>{rate !== null && <span className="rounded-full bg-indigo-50 px-2 py-1 text-xs font-semibold text-indigo-700">{rate}%</span>}</div><p className="mt-1 text-xs text-slate-500">{label === "Emails sent" ? "Successful message submissions" : label === "Prospects contacted" ? "Unique recipients with a sent message" : "Unique provider-correlated messages"}</p></Card>)}</div>;
}

function TrackingStatus({ metrics }: { metrics: AnalyticsMetrics }) { return <div className={`rounded-xl border px-4 py-3 text-sm ${metrics.tracking.available ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-amber-200 bg-amber-50 text-amber-900"}`}><strong>Tracking status:</strong> {metrics.tracking.message} <span title="Open events are provider-reported and may be affected by email-client privacy features." className="ml-1 cursor-help underline decoration-dotted">About opens</span></div>; }

function Trend({ rows }: { rows: { date: string; sent: number; delivered: number; opened: number; replied: number }[] }) {
  const visible = rows.slice(-30); const maximum = Math.max(1, ...visible.flatMap((row) => [row.sent, row.delivered, row.opened, row.replied]));
  return <Card className="p-5"><div className="flex items-center justify-between"><div><h3 className="font-semibold">Performance trend</h3><p className="text-sm text-slate-500">Persisted activity by day—no interpolation</p></div><div className="flex gap-3 text-xs text-slate-600"><Legend color="bg-indigo-600" text="Sent" /><Legend color="bg-sky-500" text="Delivered" /><Legend color="bg-violet-500" text="Opened" /><Legend color="bg-emerald-500" text="Replied" /></div></div>{visible.length ? <div className="mt-6 flex h-44 items-end gap-2 overflow-x-auto border-b border-slate-200 pb-1">{visible.map((row) => <div key={row.date} className="flex min-w-8 flex-1 items-end justify-center gap-0.5" title={`${row.date}: ${row.sent} sent, ${row.delivered} delivered, ${row.opened} opened, ${row.replied} replied`}><Bar value={row.sent} max={maximum} color="bg-indigo-600" /><Bar value={row.delivered} max={maximum} color="bg-sky-500" /><Bar value={row.opened} max={maximum} color="bg-violet-500" /><Bar value={row.replied} max={maximum} color="bg-emerald-500" /></div>)}</div> : <p className="mt-6 text-sm text-slate-500">No message activity in this period.</p>}</Card>;
}
function Bar({ value, max, color }: { value: number; max: number; color: string }) { return <span className={`w-1.5 rounded-t ${color}`} style={{ height: `${Math.max(value ? 6 : 0, value * 150 / max)}px` }} />; }
function Legend({ color, text }: { color: string; text: string }) { return <span className="flex items-center gap-1"><i className={`h-2 w-2 rounded-full ${color}`} />{text}</span>; }

function CampaignTable({ campaigns, sort, onSort, selected, onSelect }: { campaigns: AnalyticsCampaign[]; sort: string; onSort: (value: string) => void; selected: number | null; onSelect: (id: number) => void }) {
  return <Card className="overflow-hidden"><div className="flex items-center justify-between border-b p-5"><div><h3 className="font-semibold">Campaign performance</h3><p className="text-sm text-slate-500">Message outcomes and unique engagement</p></div><select aria-label="Sort campaigns" value={sort} onChange={(event) => onSort(event.target.value)} className="rounded-lg border bg-white px-3 py-2 text-sm"><option value="newest">Newest</option><option value="sent">Most sent</option><option value="open_rate">Highest open rate</option><option value="reply_rate">Highest reply rate</option></select></div>{campaigns.length ? <div className="overflow-x-auto"><table className="min-w-full text-left text-sm"><thead className="bg-slate-50 text-xs uppercase text-slate-500"><tr>{["Campaign", "Status", "Recipients", "Sent", "Delivered", "Opened", "Clicked", "Replied", "Bounced", "Unsubscribed", "Open rate", "Reply rate", "Last activity"].map((item) => <th key={item} className="px-3 py-3 font-semibold">{item}</th>)}</tr></thead><tbody className="divide-y">{campaigns.map((item) => <tr key={item.id} className={selected === item.id ? "bg-indigo-50" : "hover:bg-slate-50"}><td className="px-3 py-3"><button className="font-semibold text-indigo-800" onClick={() => onSelect(item.id)}>{item.name}</button></td><td className="px-3 py-3 capitalize">{item.status}</td><td className="px-3 py-3">{item.enrolled}</td><td className="px-3 py-3">{item.messages_sent}</td><td className="px-3 py-3">{valueOrUnavailable(item.delivered, item)}</td><td className="px-3 py-3">{valueOrUnavailable(item.opened, item)}</td><td className="px-3 py-3">{valueOrUnavailable(item.clicked, item)}</td><td className="px-3 py-3">{item.replied}</td><td className="px-3 py-3">{valueOrUnavailable(item.bounced, item)}</td><td className="px-3 py-3">{item.unsubscribed}</td><td className="px-3 py-3">{formatRate(item.rates.open)}</td><td className="px-3 py-3">{formatRate(item.rates.reply)}</td><td className="whitespace-nowrap px-3 py-3 text-xs text-slate-500">{formatDate(item.last_activity)}</td></tr>)}</tbody></table></div> : <Notice text="No campaigns match this period." />}</Card>;
}
function CampaignDetail({ data }: { data: Awaited<ReturnType<typeof prospectingApi.analyticsCampaign>> | null }) { if (!data) return <Notice text="Loading campaign detail…" />; const item = data.campaign; return <Card className="p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="text-lg font-semibold">{item.name}</h3><p className="text-sm text-slate-500">{item.status} · launched {formatDate(item.launched_at)} · {item.step_count} sequence steps</p></div><Link href={`/prospecting/campaigns/${item.id}`} className="text-sm font-semibold text-indigo-700">Open campaign</Link></div><div className="mt-4 grid gap-3 sm:grid-cols-4"><Mini label="Enrolled" value={item.enrolled} /><Mini label="Active" value={item.active} /><Mini label="Completed" value={item.completed} /><Mini label="Cancelled" value={item.cancelled} /></div><div className="mt-5 grid gap-3 rounded-xl bg-slate-50 p-4 sm:grid-cols-4 lg:grid-cols-8"><Mini label="Sent" value={item.messages_sent} /><Mini label={`Delivered · ${formatRate(item.rates.delivery)}`} value={item.delivered} /><Mini label={`Opened · ${formatRate(item.rates.open)}`} value={item.opened} /><Mini label={`Clicked · ${formatRate(item.rates.click)}`} value={item.clicked} /><Mini label={`Replied · ${formatRate(item.rates.reply)}`} value={item.replied} /><Mini label="Bounced" value={item.bounced} /><Mini label="Complained" value={item.complained} /><Mini label="Unsubscribed" value={item.unsubscribed} /></div><h4 className="mt-6 font-semibold">Performance by sequence step</h4>{data.steps.length ? <div className="mt-3 grid gap-3 lg:grid-cols-2">{data.steps.map((step) => <div key={step.id} className="rounded-xl border p-4"><strong>Step {step.step_number} — {step.label}</strong><div className="mt-3 grid grid-cols-3 gap-2 text-sm"><Mini label="Sent" value={step.sent} /><Mini label="Delivered" value={step.delivered} /><Mini label="Opened" value={step.opened} /><Mini label="Clicked" value={step.clicked} /><Mini label="Replied" value={step.replied} /><Mini label="Bounced" value={step.bounced} /></div></div>)}</div> : <p className="mt-3 text-sm text-slate-500">No frozen sequence activity is available.</p>}</Card>; }

function RecipientEngagement({ recipients, count, page, setPage, engagement, setEngagement, search, setSearch, onSelect }: { recipients: AnalyticsRecipient[]; count: number; page: number; setPage: (value: number) => void; engagement: string; setEngagement: (value: string) => void; search: string; setSearch: (value: string) => void; onSelect: (id: number) => void }) {
  return <Card className="overflow-hidden"><div className="border-b p-5"><h3 className="font-semibold">Recipient engagement</h3><p className="text-sm text-slate-500">Who opened, clicked, replied, bounced, or unsubscribed</p><div className="mt-4 flex flex-wrap gap-2">{filters.map((value) => <button key={value} onClick={() => setEngagement(value)} className={`rounded-full px-3 py-1.5 text-xs font-semibold ${engagement === value ? "bg-indigo-700 text-white" : "bg-slate-100 text-slate-700"}`}>{value.replace("_", " ")}</button>)}<input aria-label="Search recipient engagement" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search name, company, email" className="ml-auto h-9 min-w-64 rounded-lg border px-3 text-sm" /></div></div>{recipients.length ? <><div className="overflow-x-auto"><table className="min-w-full text-left text-sm"><thead className="bg-slate-50 text-xs uppercase text-slate-500"><tr>{["Recipient", "Campaign", "Step", "Sent", "Delivered", "First opened", "Opens", "First clicked", "Clicks", "Replied", "State"].map((item) => <th key={item} className="px-3 py-3">{item}</th>)}</tr></thead><tbody className="divide-y">{recipients.map((item) => <tr key={item.id} className="cursor-pointer hover:bg-slate-50" onClick={() => onSelect(item.id)}><td className="px-3 py-3"><strong>{item.name || item.email}</strong><p className="text-xs text-slate-500">{item.company} · {item.email}</p></td><td className="px-3 py-3">{item.campaign.name}</td><td className="px-3 py-3">{item.step ?? "—"}</td><td className="px-3 py-3">{formatDate(item.sent_at)}</td><td className="px-3 py-3">{formatDate(item.delivered_at)}</td><td className="px-3 py-3">{formatDate(item.first_opened_at)}</td><td className="px-3 py-3">{item.open_count}</td><td className="px-3 py-3">{formatDate(item.first_clicked_at)}</td><td className="px-3 py-3">{item.click_count}</td><td className="px-3 py-3">{formatDate(item.replied_at)}</td><td className="px-3 py-3 capitalize">{item.state}</td></tr>)}</tbody></table></div><div className="flex items-center justify-between border-t px-5 py-3 text-sm"><span>{count.toLocaleString()} recipients</span><div className="flex gap-2"><button disabled={page === 1} onClick={() => setPage(page - 1)} className="rounded border px-3 py-1 disabled:opacity-40">Previous</button><button disabled={page * 25 >= count} onClick={() => setPage(page + 1)} className="rounded border px-3 py-1 disabled:opacity-40">Next</button></div></div></> : <Notice text="No recipient engagement matches these filters." />}</Card>;
}

function RecipientDrawer({ data, onClose }: { data: Awaited<ReturnType<typeof prospectingApi.analyticsRecipient>> | null; onClose: () => void }) { return <div className="fixed inset-0 z-50 flex justify-end bg-slate-950/30" onClick={onClose}><aside className="h-full w-full max-w-lg overflow-y-auto bg-white p-6 shadow-2xl" onClick={(event) => event.stopPropagation()}><div className="flex justify-between"><h3 className="text-lg font-bold">Recipient activity</h3><button onClick={onClose} aria-label="Close recipient activity" className="rounded border px-3 py-1">Close</button></div>{!data ? <p className="mt-6 text-sm text-slate-500">Loading activity…</p> : <><div className="mt-5 rounded-xl bg-slate-50 p-4"><strong>{data.recipient.name || data.recipient.email}</strong><p className="text-sm text-slate-600">{data.recipient.company} · {data.recipient.email}</p><p className="mt-2 text-xs text-slate-500">{data.recipient.campaign.name} · Step {data.recipient.current_step} · {data.recipient.state}</p><p className="mt-1 text-xs text-slate-500">Reply: {data.recipient.reply_state.replace("_", " ")} · Suppression: {data.recipient.suppression || "none"}</p></div><div className="mt-6 space-y-4 border-l-2 border-slate-200 pl-5">{data.timeline.length ? data.timeline.map((item, index) => <div key={`${item.at}-${index}`} className="relative"><i className="absolute -left-[27px] top-1.5 h-3 w-3 rounded-full bg-indigo-600 ring-4 ring-white" /><strong className="text-sm">{item.label}</strong><p className="text-xs text-slate-500">{new Date(item.at).toLocaleString()}</p></div>) : <p className="text-sm text-slate-500">No persisted activity yet.</p>}</div></>}</aside></div>; }

function Mini({ label, value }: { label: string; value: number }) { return <div><strong className="text-lg">{value}</strong><p className="text-xs text-slate-500">{label}</p></div>; }
function Notice({ text, error = false }: { text: string; error?: boolean }) { return <div role={error ? "alert" : "status"} className={`rounded-xl border p-5 text-sm ${error ? "border-red-200 bg-red-50 text-red-800" : "bg-white text-slate-600"}`}>{text}</div>; }
function formatRate(value: number | null) { return value === null ? "—" : `${value}%`; }
function formatDate(value: string | null) { return value ? new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "—"; }
function valueOrUnavailable(value: number, campaign: AnalyticsCampaign) { return !campaign.tracking.available && campaign.messages_sent ? "Awaiting events" : value; }
