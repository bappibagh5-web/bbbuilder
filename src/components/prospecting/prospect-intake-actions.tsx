"use client";

import { FormEvent, useEffect, useState } from "react";
import { Download } from "lucide-react";
import { Card } from "@/components/ui/card";
import {
  ManualProspectInput,
  ProspectImportPreview,
  prospectingApi,
} from "@/lib/prospecting";

export function ProspectIntakeActions({
  slug,
  listId,
  canManage,
  onComplete,
}: {
  slug: string;
  listId: number;
  canManage: boolean;
  onComplete: () => Promise<void>;
}) {
  const [mode, setMode] = useState<"" | "manual" | "import">("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [trades, setTrades] = useState<{ value: string; label: string }[]>([]);
  const [preview, setPreview] = useState<ProspectImportPreview | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [manual, setManual] = useState<ManualProspectInput>({
    name: "",
    email: "",
    tags: [],
  });

  useEffect(() => {
    if (mode !== "manual") return;
    prospectingApi
      .companyOptions(slug)
      .then((result) => setTrades(result.trades))
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : "Trades could not be loaded."),
      );
  }, [slug, mode]);

  function field(name: keyof ManualProspectInput, label: string, type = "text") {
    return (
      <label className="grid gap-1 text-sm font-medium text-slate-700">
        {label}
        <input
          type={type}
          required={name === "name" || name === "email"}
          value={String(manual[name] ?? "")}
          onChange={(event) => setManual({ ...manual, [name]: event.target.value })}
          className="h-10 rounded-lg border px-3 font-normal"
        />
      </label>
    );
  }

  async function addManual(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await prospectingApi.addManualProspect(slug, listId, manual);
      setNotice(
        response.created
          ? "Prospect added."
          : "Existing company is already on this list; its contact details were reused safely.",
      );
      setManual({ name: "", email: "", tags: [] });
      await onComplete();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The prospect could not be added.");
    } finally {
      setBusy(false);
    }
  }

  async function upload(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      setPreview(await prospectingApi.previewImport(slug, listId, file));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The import could not be previewed.");
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (!preview) return;
    setBusy(true);
    setError("");
    try {
      const result = await prospectingApi.confirmImport(slug, listId, preview.import.id);
      setNotice(
        `${result.import.imported_rows} prospects imported; ${result.import.skipped_rows} rows skipped.`,
      );
      setPreview(null);
      setFile(null);
      await onComplete();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The import could not be completed.");
    } finally {
      setBusy(false);
    }
  }

  async function downloadTemplate() {
    setBusy(true);
    setError("");
    try {
      const blob = await prospectingApi.downloadImportTemplate(slug);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "BB-Builders-Prospect-Import-Template.xlsx";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The Excel template could not be downloaded.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="p-5">
      <div className="flex flex-wrap gap-2">
        {canManage && (
        <button
          type="button"
          onClick={() => {
            setMode(mode === "manual" ? "" : "manual");
            setError("");
          }}
          className="rounded-lg bg-indigo-700 px-4 py-2 text-sm font-semibold text-white"
        >
          Add prospect manually
        </button>
        )}
        {canManage && (
        <button
          type="button"
          onClick={() => {
            setMode(mode === "import" ? "" : "import");
            setError("");
          }}
          className="rounded-lg border px-4 py-2 text-sm font-semibold"
        >
          Import prospects
        </button>
        )}
        <button
          type="button"
          disabled={busy}
          onClick={() => void downloadTemplate()}
          className="inline-flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-semibold disabled:opacity-50"
        >
          <Download className="h-4 w-4" />
          Download Excel template
        </button>
      </div>
      {error && (
        <p role="alert" className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="mt-4 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">
          {notice}
        </p>
      )}
      {mode === "manual" && (
        <form onSubmit={(event) => void addManual(event)} className="mt-5 space-y-5">
          <div>
            <h3 className="font-semibold">Add prospect manually</h3>
            <p className="text-sm text-slate-500">
              Add the person you want to contact. Company and trade details are optional.
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {field("name", "Name")}
            {field("email", "Email", "email")}
            {field("phone", "Phone")}
            {field("company", "Company")}
            <label className="grid gap-1 text-sm font-medium text-slate-700">
              Trade / category
              <select
                value={manual.trade ?? ""}
                onChange={(event) => setManual({ ...manual, trade: event.target.value })}
                className="h-10 rounded-lg border bg-white px-3 font-normal"
              >
                <option value="">No trade selected</option>
                {trades.map((trade) => (
                  <option key={trade.value} value={trade.value}>
                    {trade.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="grid gap-1 text-sm font-medium text-slate-700">
            Tags
            <input
              value={(manual.tags ?? []).join(", ")}
              onChange={(event) =>
                setManual({
                  ...manual,
                  tags: event.target.value
                    .split(",")
                    .map((item) => item.trim())
                    .filter(Boolean),
                })
              }
              className="h-10 rounded-lg border px-3 font-normal"
            />
          </label>
          <label className="grid gap-1 text-sm font-medium text-slate-700">
            Notes
            <textarea
              value={manual.notes ?? ""}
              onChange={(event) => setManual({ ...manual, notes: event.target.value })}
              className="min-h-24 rounded-lg border p-3 font-normal"
            />
          </label>
          <button
            disabled={busy || !manual.name.trim() || !manual.email.trim()}
            className="rounded-lg bg-indigo-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            {busy ? "Saving…" : "Add prospect"}
          </button>
        </form>
      )}
      {mode === "import" && (
        <div className="mt-5 space-y-4">
          <div>
            <h3 className="font-semibold">Import CSV or XLSX</h3>
            <p className="mt-1 text-sm text-slate-600">
              Maximum 2 MB and 1,000 data rows. Preview does not create companies, contacts, or
              list entries. Spreadsheet formulas are ignored.
            </p>
            <p className="mt-2 text-xs text-slate-500">
              Columns: Company Name (required), Website, Company Phone, Company Email, Address,
              City, Province/State, Postal Code/ZIP, Country, Trade/Category, Contact Name,
              Contact Title, Contact Email, Contact Phone, Tags, Notes.
            </p>
          </div>
          <form onSubmit={(event) => void upload(event)} className="flex flex-wrap items-end gap-3">
            <label className="grid gap-1 text-sm font-medium text-slate-700">
              Prospect file
              <input
                type="file"
                accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                onChange={(event) => {
                  setFile(event.target.files?.[0] ?? null);
                  setPreview(null);
                }}
                className="block rounded-lg border p-2 text-sm font-normal"
              />
            </label>
            <button
              disabled={busy || !file}
              className="rounded-lg bg-indigo-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            >
              {busy ? "Reading…" : "Preview import"}
            </button>
          </form>
          {preview && <ImportPreview preview={preview} busy={busy} onConfirm={() => void confirm()} />}
        </div>
      )}
    </Card>
  );
}

function ImportPreview({
  preview,
  busy,
  onConfirm,
}: {
  preview: ProspectImportPreview;
  busy: boolean;
  onConfirm: () => void;
}) {
  const metrics = [
    ["Total rows", preview.summary.total_rows],
    ["Valid", preview.summary.valid_rows],
    ["Warnings", preview.summary.warning_rows],
    ["Invalid", preview.summary.invalid_rows],
    ["Likely duplicates", preview.summary.likely_duplicates],
    ["Existing companies", preview.summary.existing_companies],
    ["Existing contacts", preview.summary.existing_contacts],
    ["Valid contact email", preview.summary.valid_contact_email],
    ["Missing contact email", preview.summary.missing_contact_email],
  ] as const;
  return (
    <div className="rounded-xl border bg-slate-50 p-4">
      <h4 className="font-semibold">Import preview</h4>
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        {metrics.map(([label, value]) => (
          <div key={label} className="rounded-lg bg-white p-3">
            <strong>{value}</strong>
            <p className="text-xs text-slate-500">{label}</p>
          </div>
        ))}
      </div>
      <div className="mt-4 max-h-96 overflow-auto rounded-lg border bg-white">
        <table className="min-w-full text-left text-sm">
          <thead className="sticky top-0 bg-slate-100 text-xs uppercase text-slate-600">
            <tr>
              <th className="p-3">Row</th>
              <th className="p-3">Company / contact</th>
              <th className="p-3">Trade</th>
              <th className="p-3">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {preview.rows.map((row) => (
              <tr key={row.row_number}>
                <td className="p-3 align-top">{row.row_number}</td>
                <td className="p-3 align-top">
                  <strong>{row.values.company_name || "Missing company name"}</strong>
                  <p className="text-xs text-slate-500">
                    {row.values.contact_name || "No contact"}
                    {row.values.contact_email ? ` · ${row.values.contact_email}` : ""}
                  </p>
                </td>
                <td className="p-3 align-top">{row.values.trade_original || "Not provided"}</td>
                <td className="p-3 align-top">
                  <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold capitalize text-slate-700">
                    {row.status}
                  </span>
                  {[...row.errors, ...row.warnings].map((message) => (
                    <p key={message} className="mt-1 max-w-sm text-xs text-slate-600">
                      {message}
                    </p>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button
        type="button"
        disabled={busy || preview.summary.valid_rows + preview.summary.warning_rows === 0}
        onClick={onConfirm}
        className="mt-4 rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
      >
        {busy ? "Importing…" : "Confirm import"}
      </button>
    </div>
  );
}
