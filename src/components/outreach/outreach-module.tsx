"use client";
import { useState } from "react";
import { Mail, X } from "lucide-react";
import type {
  CampaignApprovalState,
  CampaignRecipient,
  Project,
  Subcontractor,
} from "@/types";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
const blank: CampaignApprovalState = {
  tradeScope: false,
  bidPackage: false,
  recipients: false,
  bidDeadline: false,
  emailContent: false,
  documents: false,
};
const steps = [
  "Preparing recipients",
  "Validating contact eligibility",
  "Preparing personalized invitations",
  "Recording campaign activity",
  "Demo invitations sent",
];
export function OutreachModule({
  project,
  trades,
  initialRecipients,
  companies,
}: {
  project: Project;
  trades: Array<{
    trade: string;
    invited: number;
    bids: number;
    status: string;
  }>;
  initialRecipients: CampaignRecipient[];
  companies: Subcontractor[];
}) {
  const [selectedTrade, setSelectedTrade] = useState("Electrical");
  const [recipients, setRecipients] = useState(initialRecipients);
  const [selectedRecipient, setSelectedRecipient] = useState(
    initialRecipients[0]?.subcontractorId ?? "",
  );
  const [checklist, setChecklist] = useState(blank);
  const [approved, setApproved] = useState(false);
  const [sent, setSent] = useState(true);
  const [sending, setSending] = useState(false);
  const [sendStep, setSendStep] = useState(-1);
  const [detail, setDetail] = useState<CampaignRecipient | null>(null);
  const [subject, setSubject] = useState(
    "Bid Invitation – Electrical – Retail Store Tenant Improvement – Coquitlam, BC",
  );
  const [body, setBody] = useState(
    "Hello {{companyName}},\n\nBB Builders is requesting subcontractor pricing for the {{trade}} scope for {{projectName}} ({{projectNumber}}) in {{location}}.\n\nBid Due: {{bidDeadline}}\nQuestions Due: {{questionsDeadline}}\n\nPlease review the bid package and clearly identify base bid, taxes, inclusions, exclusions, allowances, alternates, permit responsibility, schedule, and bid validity.\n\nThank you,\nBB Builders Estimating",
  );
  const companyMap = new Map(companies.map((c) => [c.id, c]));
  const selectedCompany = companyMap.get(selectedRecipient);
  const merged = body
    .replaceAll(
      "{{companyName}}",
      selectedCompany?.companyName ?? "Selected Company",
    )
    .replaceAll("{{trade}}", "Electrical")
    .replaceAll("{{projectName}}", project.name)
    .replaceAll("{{projectNumber}}", project.projectNumber)
    .replaceAll("{{location}}", `${project.city}, ${project.province}`)
    .replaceAll("{{bidDeadline}}", "September 14, 2026")
    .replaceAll("{{questionsDeadline}}", "September 9, 2026");
  const allChecked = Object.values(checklist).every(Boolean);
  const simulate = async () => {
    setSending(true);
    for (let i = 0; i < steps.length; i++) {
      setSendStep(i);
      await new Promise((r) =>
        setTimeout(
          r,
          window.matchMedia("(prefers-reduced-motion: reduce)").matches
            ? 80
            : 450,
        ),
      );
    }
    setSending(false);
    setSent(true);
  };
  const update = (
    id: string,
    fn: (r: CampaignRecipient) => CampaignRecipient,
  ) => setRecipients((items) => items.map((r) => (r.id === id ? fn(r) : r)));
  if (project.id !== "retail-store-coquitlam")
    return (
      <Card className="p-10 text-center">
        <Mail className="mx-auto h-8 w-8 text-slate-400" />
        <h2 className="mt-4 text-xl font-semibold">Campaigns Not Prepared</h2>
        <p className="mt-2 text-sm text-slate-500">
          Recipient approval is required before outreach can begin for{" "}
          {project.name}.
        </p>
      </Card>
    );
  return (
    <div className="space-y-5">
      <header>
        <h2 className="text-xl font-semibold">Bid Outreach</h2>
        <p className="mt-1 text-sm text-slate-500">
          Prepare, send, and track subcontractor bid invitations.
        </p>
        <p className="mt-1 text-sm font-medium">
          {project.name} · {project.projectNumber} · {project.city},{" "}
          {project.province} · Bid deadline September 14, 2026
        </p>
        <p className="mt-2 text-xs font-medium text-violet-700">
          Demo environment — email sending and recipient activity shown here are
          simulated.
        </p>
      </header>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
        {[
          ["Trade Campaigns", 10],
          ["Invitations Sent", 46],
          ["Opened", 39],
          ["Responses", 34],
          ["Bids Submitted", 31],
          ["Needs Follow-Up", 12],
        ].map(([l, v]) => (
          <Card key={l as string} className="p-4">
            <p className="text-2xl font-semibold">{v}</p>
            <p className="text-xs text-slate-500">{l}</p>
          </Card>
        ))}
      </section>
      <div className="grid gap-5 xl:grid-cols-[280px_1fr]">
        <aside>
          <label className="block xl:hidden">
            <span className="mb-1 block text-sm font-medium">
              Select trade campaign
            </span>
            <select
              value={selectedTrade}
              onChange={(e) => setSelectedTrade(e.target.value)}
              className="h-10 w-full rounded-lg border bg-white px-3"
            >
              {trades.map((t) => (
                <option key={t.trade}>{t.trade}</option>
              ))}
            </select>
          </label>
          <Card className="hidden overflow-hidden xl:block">
            <h3 className="border-b p-4 text-sm font-semibold">
              Trade Campaigns
            </h3>
            {trades.map((t) => (
              <button
                key={t.trade}
                onClick={() => setSelectedTrade(t.trade)}
                className={`w-full border-b p-3 text-left ${selectedTrade === t.trade ? "bg-blue-50" : ""}`}
              >
                <span className="text-sm font-semibold">{t.trade}</span>
                <p className="text-xs text-slate-500">
                  {t.invited} recipients · {t.bids} bids · {t.status}
                </p>
              </button>
            ))}
          </Card>
        </aside>
        <main className="min-w-0 space-y-5">
          {selectedTrade !== "Electrical" ? (
            <Card className="p-8 text-center">
              <h3 className="font-semibold">{selectedTrade} Outreach Active</h3>
              <p className="mt-2 text-sm text-slate-500">
                Use Electrical for the complete Task 06 campaign preparation and
                activity workflow.
              </p>
            </Card>
          ) : (
            <>
              <Card className="p-5">
                <h3 className="font-semibold">Electrical Campaign Readiness</h3>
                <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                  {[
                    ["Trade Scope", "Approved"],
                    ["Bid Package", "Approved for Outreach"],
                    ["Recipients", "6 approved"],
                    ["Contact Eligibility", "6 eligible"],
                    [
                      "Campaign Status",
                      sent
                        ? "Active"
                        : approved
                          ? "Approved"
                          : "Ready for Approval",
                    ],
                  ].map(([l, v]) => (
                    <div key={l} className="rounded-lg bg-slate-50 p-3">
                      <p className="text-xs text-slate-500">{l}</p>
                      <p className="mt-1 text-sm font-semibold">{v}</p>
                    </div>
                  ))}
                </div>
              </Card>
              <Card>
                <header className="border-b p-4">
                  <h3 className="font-semibold">RFQ Email Composer</h3>
                  <p className="text-xs text-slate-500">
                    Fictional demo sender addresses · changes reset on refresh
                  </p>
                </header>
                <div className="grid lg:grid-cols-2">
                  <div className="space-y-3 p-4">
                    {[
                      ["From Name", "BB Builders Estimating"],
                      [
                        "From Address",
                        "estimating@bbbuilders-demo.example.com",
                      ],
                      ["Reply-To", "bids@bbbuilders-demo.example.com"],
                    ].map(([l, v]) => (
                      <label key={l}>
                        <span className="mb-1 block text-xs font-semibold">
                          {l}
                        </span>
                        <input
                          value={v}
                          readOnly
                          className="h-9 w-full rounded-lg border bg-slate-50 px-3 text-sm"
                        />
                      </label>
                    ))}
                    <label>
                      <span className="mb-1 block text-xs font-semibold">
                        Subject
                      </span>
                      <input
                        value={subject}
                        onChange={(e) => setSubject(e.target.value)}
                        className="h-9 w-full rounded-lg border px-3 text-sm"
                      />
                    </label>
                    <label>
                      <span className="mb-1 block text-xs font-semibold">
                        Email body
                      </span>
                      <textarea
                        value={body}
                        onChange={(e) => setBody(e.target.value)}
                        rows={12}
                        className="w-full rounded-lg border p-3 text-sm"
                      />
                    </label>
                  </div>
                  <div className="border-t bg-slate-50 p-4 lg:border-l lg:border-t-0">
                    <label>
                      <span className="mb-1 block text-xs font-semibold">
                        Preview recipient
                      </span>
                      <select
                        value={selectedRecipient}
                        onChange={(e) => setSelectedRecipient(e.target.value)}
                        className="h-9 w-full rounded-lg border bg-white px-3 text-sm"
                      >
                        {recipients.map((r) => (
                          <option key={r.id} value={r.subcontractorId}>
                            {companyMap.get(r.subcontractorId)?.companyName}
                          </option>
                        ))}
                      </select>
                    </label>
                    <article className="mt-3 rounded-lg border bg-white p-4">
                      <p className="text-xs text-slate-500">Subject</p>
                      <p className="font-semibold">{subject}</p>
                      <pre className="mt-4 whitespace-pre-wrap font-sans text-sm leading-6">
                        {merged}
                      </pre>
                    </article>
                  </div>
                </div>
              </Card>
              <Card className="p-5">
                <h3 className="font-semibold">
                  Electrical Bid Package · Approved
                </h3>
                <p className="mt-1 text-sm">
                  14 scope items · 3 potential exclusions · 2 clarifications
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {[
                    "Electrical Drawings.pdf",
                    "Architectural Drawing Set.pdf",
                    "Project Specifications.pdf",
                    "Bid Instructions.pdf",
                    "Addendum 01.pdf",
                    "Addendum 02.pdf",
                  ].map((d) => (
                    <span
                      key={d}
                      className="rounded bg-slate-100 px-2 py-1 text-xs"
                    >
                      {d}
                    </span>
                  ))}
                </div>
              </Card>
              <RecipientTable
                recipients={recipients}
                companyMap={companyMap}
                onDetail={setDetail}
              />
              <Card>
                <div className="grid lg:grid-cols-[1fr_330px]">
                  <div className="p-5">
                    <h3 className="font-semibold">
                      Campaign Approval Checklist
                    </h3>
                    <div className="mt-4 grid gap-2 sm:grid-cols-2">
                      {Object.entries({
                        tradeScope: "Trade scope approved",
                        bidPackage: "Bid package approved",
                        recipients: "Recipients reviewed",
                        bidDeadline: "Bid deadline confirmed",
                        emailContent: "Email content reviewed",
                        documents: "Documents confirmed",
                      }).map(([key, label]) => (
                        <label
                          key={key}
                          className="flex items-center gap-3 rounded-lg border p-3 text-sm"
                        >
                          <input
                            type="checkbox"
                            checked={
                              checklist[key as keyof CampaignApprovalState]
                            }
                            onChange={(e) =>
                              setChecklist((v) => ({
                                ...v,
                                [key]: e.target.checked,
                              }))
                            }
                          />
                          {label}
                        </label>
                      ))}
                    </div>
                  </div>
                  <div className="border-t bg-slate-50 p-5 lg:border-l lg:border-t-0">
                    <Button
                      disabled={!allChecked || approved}
                      onClick={() => setApproved(true)}
                      className="w-full bg-primary text-white"
                    >
                      {approved ? "Campaign Approved" : "Approve Campaign"}
                    </Button>
                    {approved && (
                      <>
                        <p className="mt-3 text-sm font-semibold text-emerald-700">
                          Approved by Alex Morgan · Estimator
                        </p>
                        <p className="text-xs text-slate-500">
                          Demo timestamp: Aug 23, 2026, 4:00 PM
                        </p>
                        <Button
                          onClick={simulate}
                          disabled={sending}
                          className="mt-4 w-full"
                        >
                          Send Demo Invitations
                        </Button>
                      </>
                    )}
                    <p className="mt-3 text-xs text-slate-500">
                      In production, approval would be written to the project
                      audit trail before invitations are sent.
                    </p>
                  </div>
                </div>
                {(sending || sendStep === steps.length - 1) && (
                  <div className="border-t bg-violet-50 p-4">
                    <p className="text-xs font-semibold text-violet-800">
                      Demo Send Simulation — no email will be transmitted.
                    </p>
                    <div className="mt-2 grid gap-2 sm:grid-cols-5">
                      {steps.map((s, i) => (
                        <p
                          key={s}
                          className={`text-xs ${i <= sendStep ? "font-semibold" : "text-slate-400"}`}
                        >
                          {i < sendStep ? "✓ " : ""}
                          {s}
                        </p>
                      ))}
                    </div>
                  </div>
                )}
              </Card>
            </>
          )}
        </main>
      </div>
      <section>
        <h3 className="font-semibold">All-Trade Outreach Overview</h3>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {trades.map((t) => (
            <Card key={t.trade} className="p-4">
              <p className="font-semibold">{t.trade}</p>
              <p className="mt-2 text-sm">
                {t.invited} invited · {t.bids} bids
              </p>
              <p className="mt-1 text-xs text-slate-500">{t.status}</p>
            </Card>
          ))}
        </div>
      </section>
      {detail && (
        <RecipientPanel
          recipient={detail}
          company={companyMap.get(detail.subcontractorId)!}
          onClose={() => setDetail(null)}
          onUpdate={(fn) => {
            update(detail.id, fn);
            setDetail((current) => (current ? fn(current) : current));
          }}
        />
      )}
    </div>
  );
}
function RecipientTable({
  recipients,
  companyMap,
  onDetail,
}: {
  recipients: CampaignRecipient[];
  companyMap: Map<string, Subcontractor>;
  onDetail: (r: CampaignRecipient) => void;
}) {
  return (
    <Card>
      <header className="border-b p-4">
        <h3 className="font-semibold">Recipient Activity</h3>
      </header>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[900px] text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              {[
                "Company",
                "Sent",
                "Delivery",
                "Opened",
                "Response",
                "Bid",
                "Last Activity",
                "Follow-Up",
                "Actions",
              ].map((h) => (
                <th key={h} className="px-3 py-3">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y">
            {recipients.map((r) => (
              <tr key={r.id}>
                <td className="px-3 py-3 font-semibold">
                  {companyMap.get(r.subcontractorId)?.companyName}
                </td>
                <td className="px-3 py-3">{r.sentAt}</td>
                <td className="px-3 py-3">
                  {r.delivered ? "Delivered" : "Pending"}
                </td>
                <td className="px-3 py-3">{r.openedAt ?? "No"}</td>
                <td className="px-3 py-3">
                  {r.response}
                  {r.declineReason && (
                    <p className="text-xs text-slate-500">{r.declineReason}</p>
                  )}
                </td>
                <td className="px-3 py-3">{r.bidStatus}</td>
                <td className="px-3 py-3">{r.lastActivity}</td>
                <td className="px-3 py-3">{r.followUpStatus}</td>
                <td className="px-3 py-3">
                  <Button onClick={() => onDetail(r)}>View Timeline</Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
function RecipientPanel({
  recipient,
  company,
  onClose,
  onUpdate,
}: {
  recipient: CampaignRecipient;
  company: Subcontractor;
  onClose: () => void;
  onUpdate: (fn: (r: CampaignRecipient) => CampaignRecipient) => void;
}) {
  const [reply, setReply] = useState("");
  const [followUp, setFollowUp] = useState(false);
  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-slate-950/45"
      role="dialog"
      aria-modal="true"
      aria-label="Recipient activity"
    >
      <div className="h-full w-full max-w-2xl overflow-y-auto bg-white">
        <header className="sticky top-0 flex items-center justify-between border-b bg-white p-5">
          <div>
            <p className="text-xs text-violet-700">
              Simulated recipient activity
            </p>
            <h2 className="font-semibold">{company.companyName}</h2>
          </div>
          <button onClick={onClose} aria-label="Close recipient activity">
            <X className="h-5 w-5" />
          </button>
        </header>
        <div className="space-y-5 p-5">
          <dl className="grid gap-3 sm:grid-cols-3">
            {[
              ["Contact status", company.contactStatus],
              ["Qualification", company.qualificationStatus],
              ["Relationship", company.relationship],
              ["Trade", "Electrical"],
              ["Bid package", "Approved"],
              ["Response", recipient.response],
            ].map(([l, v]) => (
              <div key={l}>
                <dt className="text-xs text-slate-500">{l}</dt>
                <dd className="text-sm font-semibold">{v}</dd>
              </div>
            ))}
          </dl>
          <section>
            <h3 className="font-semibold">Activity Timeline</h3>
            <ol className="mt-3 border-l pl-5">
              {recipient.events.map((e) => (
                <li key={e.id} className="relative mb-4">
                  <span className="absolute -left-[25px] top-1 h-2 w-2 rounded-full bg-blue-600" />
                  <p className="text-xs text-slate-500">{e.occurredAt}</p>
                  <p className="text-sm font-semibold">{e.label}</p>
                  {e.detail && (
                    <p className="text-sm text-slate-600">{e.detail}</p>
                  )}
                </li>
              ))}
            </ol>
          </section>
          {recipient.question && (
            <section className="rounded-lg border p-4">
              <h3 className="font-semibold">Incoming Question</h3>
              <p className="mt-2 text-sm">“{recipient.question}”</p>
              <p className="mt-2 text-xs text-amber-700">
                {recipient.questionStatus}
              </p>
              <div className="mt-3 flex gap-2">
                <Button
                  onClick={() =>
                    onUpdate((r) => ({ ...r, questionStatus: "Reviewed" }))
                  }
                >
                  Mark Reviewed
                </Button>
                <Button
                  onClick={() =>
                    setReply(
                      "Fire alarm is currently identified as a separate clarification item. Please price the electrical scope excluding fire alarm unless otherwise noted in an addendum.",
                    )
                  }
                >
                  Prepare Demo Reply
                </Button>
              </div>
              {reply && (
                <label className="mt-3 block">
                  <span className="text-xs font-semibold text-violet-700">
                    Demo reply — not sent.
                  </span>
                  <textarea
                    value={reply}
                    onChange={(e) => setReply(e.target.value)}
                    rows={4}
                    className="mt-1 w-full rounded-lg border p-3 text-sm"
                  />
                </label>
              )}
            </section>
          )}
          {recipient.followUpStatus === "Follow-Up Recommended" && (
            <section className="rounded-lg border border-amber-200 bg-amber-50 p-4">
              <h3 className="font-semibold">Follow-Up Recommended</h3>
              <p className="mt-1 text-sm">
                Invitation sent Aug 20 · not opened · no response
              </p>
              <Button onClick={() => setFollowUp(true)} className="mt-3">
                Prepare Follow-Up
              </Button>
              {followUp && (
                <div className="mt-3 rounded bg-white p-3 text-sm">
                  <p className="font-semibold">
                    Reminder – Electrical Bid – Retail Store Tenant Improvement
                  </p>
                  <p className="mt-2">
                    Hello {company.companyName}, this is a reminder that pricing
                    is due September 14, 2026. Please let us know if you intend
                    to bid.
                  </p>
                  <p className="mt-2 text-xs text-violet-700">
                    Demo follow-up — no email will be sent.
                  </p>
                  <div className="mt-3 flex gap-2">
                    <Button
                      onClick={() =>
                        onUpdate((r) => ({
                          ...r,
                          followUpStatus: "Follow-Up Sent",
                          events: [
                            ...r.events,
                            {
                              id: `followup-${r.id}`,
                              recipientId: r.id,
                              type: "FollowUpSent",
                              label: "Demo follow-up sent",
                              occurredAt: "Aug 23, 4:22 PM",
                            },
                          ],
                        }))
                      }
                    >
                      Send Demo Follow-Up
                    </Button>
                    <Button
                      onClick={() =>
                        onUpdate((r) => ({
                          ...r,
                          followUpStatus: "Do Not Follow Up",
                        }))
                      }
                    >
                      Do Not Follow Up
                    </Button>
                  </div>
                </div>
              )}
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
