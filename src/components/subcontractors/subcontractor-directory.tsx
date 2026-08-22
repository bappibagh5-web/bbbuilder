"use client";
import { useMemo, useState } from "react";
import { Plus, Search, X } from "lucide-react";
import type {
  ContractorQualificationStatus,
  ContractorRelationship,
  Subcontractor,
} from "@/types";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

const metricLabels = [
  "Total Subcontractors",
  "Active Trade Partners",
  "New Prospects",
  "Needs Qualification",
  "Trades Covered",
];
const tone = (value: string) =>
  value === "Qualified" || value === "Active" || value === "Eligible"
    ? "bg-emerald-50 text-emerald-700"
    : value.includes("Review") || value.includes("Conditional")
      ? "bg-amber-50 text-amber-800"
      : "bg-slate-100 text-slate-700";

export function SubcontractorDirectory({
  initialRecords,
  summary,
}: {
  initialRecords: Subcontractor[];
  summary: {
    total: number;
    active: number;
    prospects: number;
    needsQualification: number;
    tradesCovered: number;
  };
}) {
  const [records, setRecords] = useState(initialRecords);
  const [selected, setSelected] = useState<Subcontractor | null>(null);
  const [adding, setAdding] = useState(false);
  const [filters, setFilters] = useState({
    search: "",
    trade: "",
    city: "",
    relationship: "",
    qualification: "",
    status: "",
  });
  const trades = [...new Set(records.map((item) => item.primaryTrade))].sort();
  const cities = [...new Set(records.map((item) => item.city))].sort();
  const filtered = useMemo(
    () =>
      records.filter(
        (item) =>
          (!filters.search ||
            item.companyName
              .toLowerCase()
              .includes(filters.search.toLowerCase())) &&
          (!filters.trade || item.primaryTrade === filters.trade) &&
          (!filters.city || item.city === filters.city) &&
          (!filters.relationship ||
            item.relationship === filters.relationship) &&
          (!filters.qualification ||
            item.qualificationStatus === filters.qualification) &&
          (!filters.status || item.status === filters.status),
      ),
    [records, filters],
  );
  const values = [
    summary.total,
    summary.active,
    summary.prospects,
    summary.needsQualification,
    summary.tradesCovered,
  ];
  return (
    <div className="space-y-5">
      <header className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Subcontractors</h1>
          <p className="mt-1 text-sm text-slate-500">
            Maintain trade partners, qualification information, service areas,
            and bid history.
          </p>
          <p className="mt-2 text-xs font-medium text-violet-700">
            Demo environment — subcontractor companies and contact details shown
            here are fictional.
          </p>
        </div>
        <Button
          onClick={() => setAdding(true)}
          className="self-start bg-primary text-white hover:bg-primary/90"
        >
          <Plus className="h-4 w-4" />
          Add Demo Subcontractor
        </Button>
      </header>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {metricLabels.map((label, index) => (
          <Card key={label} className="p-4">
            <p className="text-2xl font-semibold">{values[index]}</p>
            <p className="mt-1 text-xs text-slate-500">{label}</p>
          </Card>
        ))}
      </section>
      <Card>
        <div className="grid gap-3 border-b p-4 md:grid-cols-3 xl:grid-cols-6">
          <label className="relative md:col-span-2 xl:col-span-1">
            <span className="sr-only">Search company</span>
            <Search className="absolute left-3 top-3 h-4 w-4 text-slate-400" />
            <input
              value={filters.search}
              onChange={(e) =>
                setFilters((v) => ({ ...v, search: e.target.value }))
              }
              placeholder="Search company"
              className="h-10 w-full rounded-lg border pl-9 pr-3 text-sm"
            />
          </label>
          {[
            ["trade", trades],
            ["city", cities],
            [
              "relationship",
              ["Preferred", "Existing", "New Prospect", "Do Not Invite"],
            ],
            [
              "qualification",
              [
                "Qualified",
                "Conditionally Qualified",
                "Needs Review",
                "Unqualified",
              ],
            ],
            ["status", ["Active", "Inactive"]],
          ].map(([key, options]) => (
            <label key={key as string}>
              <span className="sr-only">Filter by {key as string}</span>
              <select
                value={filters[key as keyof typeof filters]}
                onChange={(e) =>
                  setFilters((v) => ({ ...v, [key as string]: e.target.value }))
                }
                className="h-10 w-full rounded-lg border bg-white px-3 text-sm"
              >
                <option value="">All {key as string}</option>
                {(options as string[]).map((option) => (
                  <option key={option}>{option}</option>
                ))}
              </select>
            </label>
          ))}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1200px] text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                {[
                  "Company",
                  "Primary Trade",
                  "Location",
                  "Service Area",
                  "Rating",
                  "Relationship",
                  "Qualification",
                  "Bid Activity",
                  "Status",
                  "Actions",
                ].map((item) => (
                  <th key={item} className="px-4 py-3 font-semibold">
                    {item}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y">
              {filtered.map((item) => (
                <tr key={item.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <button
                      onClick={() => setSelected(item)}
                      className="font-semibold text-blue-700 hover:underline"
                    >
                      {item.companyName}
                    </button>
                    <p className="text-xs text-slate-500">
                      {item.contactStatus}
                    </p>
                  </td>
                  <td className="px-4 py-3">{item.primaryTrade}</td>
                  <td className="px-4 py-3">
                    {item.city}, {item.province}
                  </td>
                  <td className="max-w-44 px-4 py-3 text-xs text-slate-600">
                    {item.serviceAreas.join(", ")}
                  </td>
                  <td className="px-4 py-3">
                    ★ {item.rating}{" "}
                    <span className="text-xs text-slate-400">
                      ({item.reviewCount})
                    </span>
                  </td>
                  <td className="px-4 py-3">{item.relationship}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded px-2 py-1 text-xs font-semibold ${tone(item.qualificationStatus)}`}
                    >
                      {item.qualificationStatus}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {item.totalBids}/{item.totalInvitations} bids
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded px-2 py-1 text-xs font-semibold ${tone(item.status)}`}
                    >
                      {item.status}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <Button onClick={() => setSelected(item)}>
                      View Profile
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="border-t px-4 py-3 text-xs text-slate-500">
          Showing {filtered.length} fictional demo companies.
        </p>
      </Card>
      {selected && (
        <ContractorDetail
          company={selected}
          onClose={() => setSelected(null)}
        />
      )}{" "}
      {adding && (
        <AddContractor
          trades={trades}
          onClose={() => setAdding(false)}
          onAdd={(record) => {
            setRecords((v) => [record, ...v]);
            setAdding(false);
          }}
        />
      )}
    </div>
  );
}

function ModalShell({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-slate-950/45"
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div className="h-full w-full max-w-2xl overflow-y-auto bg-white shadow-2xl">
        <header className="sticky top-0 z-10 flex items-center justify-between border-b bg-white p-5">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button
            onClick={onClose}
            aria-label={`Close ${title}`}
            className="rounded p-2 hover:bg-slate-100"
          >
            <X className="h-5 w-5" />
          </button>
        </header>
        {children}
      </div>
    </div>
  );
}
function ContractorDetail({
  company,
  onClose,
}: {
  company: Subcontractor;
  onClose: () => void;
}) {
  const responseRate = Math.round(
    (company.totalBids / company.totalInvitations) * 100,
  );
  return (
    <ModalShell title="Subcontractor Profile" onClose={onClose}>
      <div className="space-y-5 p-5">
        <div>
          <p className="text-xs font-semibold uppercase text-violet-700">
            Fictional demo company
          </p>
          <h3 className="mt-1 text-xl font-semibold">{company.companyName}</h3>
          <p className="text-sm text-slate-500">
            {company.primaryTrade} · {company.city}, {company.province}
          </p>
        </div>
        <Info
          title="Company information"
          rows={[
            [
              "Secondary trades",
              company.secondaryTrades.join(", ") || "None listed",
            ],
            ["Service area", company.serviceAreas.join(", ")],
            ["Years in business", String(company.yearsInBusiness)],
            ["Discovery source", company.source],
          ]}
        />
        <Info
          title="Contact and governance"
          rows={[
            ["Email", company.email],
            ["Phone", company.phone],
            ["Website", company.website],
            ["Contact status", company.contactStatus],
            ["Last verified", company.lastVerifiedAt],
          ]}
        />
        <Info
          title="Qualification"
          rows={[
            ["Overall", company.qualificationStatus],
            ["Insurance", company.qualification.insurance],
            ["Workers compensation", company.qualification.workersComp],
            ["Business license", company.qualification.license],
            ["Commercial experience", company.commercialExperience],
            ["Retail experience", company.retailExperience],
          ]}
        />
        <section>
          <h4 className="font-semibold">Demo bid history</h4>
          <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-5">
            {[
              ["Invitations", company.totalInvitations],
              ["Bids Submitted", company.totalBids],
              ["Awards", company.awardedProjects],
              ["Response Rate", `${responseRate}%`],
              ["Avg. Response", company.averageResponseTime],
            ].map(([label, value]) => (
              <div key={label as string} className="rounded-lg bg-slate-50 p-3">
                <p className="text-lg font-semibold">{value}</p>
                <p className="text-xs text-slate-500">{label}</p>
              </div>
            ))}
          </div>
        </section>
        <Info title="Internal notes" rows={[["Notes", company.notes]]} />
        <p className="text-xs text-slate-500">
          All profile and history information is simulated and does not
          represent a real business.
        </p>
      </div>
    </ModalShell>
  );
}
function Info({
  title,
  rows,
}: {
  title: string;
  rows: Array<[string, string]>;
}) {
  return (
    <section>
      <h4 className="font-semibold">{title}</h4>
      <dl className="mt-2 divide-y rounded-lg border">
        {rows.map(([label, value]) => (
          <div
            key={label}
            className="grid gap-1 px-3 py-2.5 sm:grid-cols-[170px_1fr]"
          >
            <dt className="text-xs font-semibold text-slate-500">{label}</dt>
            <dd className="text-sm">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
function AddContractor({
  trades,
  onClose,
  onAdd,
}: {
  trades: string[];
  onClose: () => void;
  onAdd: (item: Subcontractor) => void;
}) {
  const [form, setForm] = useState({
    companyName: "",
    primaryTrade: trades[0] ?? "Electrical",
    city: "",
    province: "BC",
    email: "",
    phone: "",
    relationship: "New Prospect" as ContractorRelationship,
    qualificationStatus: "Needs Review" as ContractorQualificationStatus,
  });
  const field = (key: keyof typeof form, label: string) => (
    <label>
      <span className="mb-1 block text-sm font-medium">{label}</span>
      <input
        value={form[key]}
        onChange={(e) => setForm((v) => ({ ...v, [key]: e.target.value }))}
        className="h-10 w-full rounded-lg border px-3 text-sm"
        required
      />
    </label>
  );
  return (
    <ModalShell title="Add Demo Subcontractor" onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const slug = `demo-added-${form.companyName.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
          onAdd({
            id: slug,
            ...form,
            secondaryTrades: [],
            serviceAreas: [form.city, "Lower Mainland"],
            website: `https://${slug}.example.com`,
            rating: 0,
            reviewCount: 0,
            status: "Active",
            yearsInBusiness: 0,
            commercialExperience: "Needs review",
            retailExperience: "Needs review",
            qualification: {
              insurance: "Unknown",
              workersComp: "Unknown",
              license: "Needs Review",
              commercialExperience: "Needs Review",
              retailExperience: "Needs Review",
            },
            totalInvitations: 0,
            totalBids: 0,
            awardedProjects: 0,
            averageResponseTime: "No history",
            notes: "Temporarily added demo record.",
            source: "Demo Discovery",
            contactStatus: "Needs Review",
            contactSource: "Demo form",
            lastVerifiedAt: "Not verified",
            isDemo: true,
          });
        }}
        className="space-y-4 p-5"
      >
        <p className="rounded-lg bg-violet-50 p-3 text-xs text-violet-800">
          Demo changes reset when the page is refreshed.
        </p>
        {field("companyName", "Company Name")}
        <label>
          <span className="mb-1 block text-sm font-medium">Primary Trade</span>
          <select
            value={form.primaryTrade}
            onChange={(e) =>
              setForm((v) => ({ ...v, primaryTrade: e.target.value }))
            }
            className="h-10 w-full rounded-lg border px-3"
          >
            {trades.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </label>
        <div className="grid gap-4 sm:grid-cols-2">
          {field("city", "City")}
          {field("province", "Province")}
          {field("email", "Email")}
          {field("phone", "Phone")}
        </div>
        <label>
          <span className="mb-1 block text-sm font-medium">Relationship</span>
          <select
            value={form.relationship}
            onChange={(e) =>
              setForm((v) => ({
                ...v,
                relationship: e.target.value as ContractorRelationship,
              }))
            }
            className="h-10 w-full rounded-lg border px-3"
          >
            {["Preferred", "Existing", "New Prospect", "Do Not Invite"].map(
              (v) => (
                <option key={v}>{v}</option>
              ),
            )}
          </select>
        </label>
        <label>
          <span className="mb-1 block text-sm font-medium">
            Qualification Status
          </span>
          <select
            value={form.qualificationStatus}
            onChange={(e) =>
              setForm((v) => ({
                ...v,
                qualificationStatus: e.target
                  .value as ContractorQualificationStatus,
              }))
            }
            className="h-10 w-full rounded-lg border px-3"
          >
            {[
              "Qualified",
              "Conditionally Qualified",
              "Needs Review",
              "Unqualified",
            ].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </label>
        <div className="flex justify-end gap-2 border-t pt-4">
          <Button onClick={onClose}>Cancel</Button>
          <Button
            type="submit"
            disabled={!form.companyName || !form.city || !form.email}
            className="bg-primary text-white"
          >
            Add Demo Record
          </Button>
        </div>
      </form>
    </ModalShell>
  );
}
