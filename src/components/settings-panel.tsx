"use client";

import { useEffect, useState } from "react";
import { useOrganization } from "@/components/organizations/organization-provider";
import { Card } from "@/components/ui/card";
import { outreachApi, type OutreachSender, type SMTPSettings } from "@/lib/outreach";

type SMTPForm = {
  host: string; port: number; username: string; password: string; clear_password: boolean;
  security: "starttls" | "ssl" | "none"; timeout_seconds: number; is_enabled: boolean;
};

function formFrom(settings: SMTPSettings): SMTPForm {
  return {
    host: settings.host ?? "", port: settings.port ?? 587,
    username: settings.username ?? "", password: "", clear_password: false,
    security: settings.security ?? "starttls", timeout_seconds: settings.timeout_seconds ?? 20,
    is_enabled: settings.is_enabled ?? false,
  };
}

export function SettingsPanel() {
  const { activeMembership } = useOrganization();
  const slug = activeMembership?.organization.slug;
  const canEdit = activeMembership?.role === "admin";
  const [sender, setSender] = useState<OutreachSender | null>(null);
  const [smtp, setSmtp] = useState<SMTPSettings | null>(null);
  const [smtpForm, setSmtpForm] = useState<SMTPForm | null>(null);
  const [testRecipient, setTestRecipient] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [connectionResult, setConnectionResult] = useState<{ success: boolean; message: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const testEmailBlockers = [
    ...(!smtp?.is_enabled ? ["Enable outreach email delivery"] : []),
    ...(!sender?.is_enabled || !sender.from_address || !sender.reply_to ? ["Configure sender identity"] : []),
    ...(smtp?.provider.state !== "configured" ? ["SMTP configuration not ready"] : []),
    ...(!testRecipient.trim() ? ["Enter a test recipient"] : []),
  ];

  useEffect(() => {
    if (!slug) return;
    const organizationSlug = slug;
    let live = true;
    Promise.all([outreachApi.sender(organizationSlug), outreachApi.smtpSettings(organizationSlug)])
      .then(([senderValue, smtpValue]) => {
        if (!live) return;
        setSender(senderValue); setSmtp(smtpValue); setSmtpForm(formFrom(smtpValue));
      })
      .catch((reason: unknown) => {
        if (live) setError(reason instanceof Error ? reason.message : "Email settings could not be loaded.");
      });
    return () => { live = false; };
  }, [slug]);

  async function act(action: () => Promise<void>) {
    setBusy(true); setError(null); setNotice(null);
    try { await action(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "The action could not be completed."); }
    finally { setBusy(false); }
  }

  async function saveSender() {
    if (!slug || !sender || !canEdit) return;
    await act(async () => {
      const updated = await outreachApi.saveSender(slug, {
        display_name: sender.display_name, from_address: sender.from_address,
        reply_to: sender.reply_to, is_enabled: sender.is_enabled ?? false,
      });
      setSender(updated); setNotice("Sender identity saved.");
    });
  }

  async function saveSMTP() {
    if (!slug || !smtpForm || !canEdit) return;
    const draft = smtpForm;
    await act(async () => {
      const updated = await outreachApi.saveSMTPSettings(slug, draft);
      setSmtp(updated); setSmtpForm(formFrom(updated));
      setNotice("SMTP setup saved. Password is never shown again after saving.");
    });
    setSmtpForm((current) => current ? { ...current, password: "", clear_password: false } : null);
  }

  async function testConnection() {
    if (!slug || !canEdit) return;
    setConnectionResult(null);
    await act(async () => {
      const result = await outreachApi.testSMTPConnection(slug);
      const messages: Record<string, string> = {
        smtp_connected: "Connection successful",
        smtp_authentication: "Authentication failed. Check the SMTP username and password.",
        smtp_connection: "Could not connect to the SMTP server.",
        smtp_unavailable: "Could not connect to the SMTP server.",
        smtp_security: "TLS/SSL error. Check the security mode and server settings.",
        smtp_timeout: "The SMTP connection timed out.",
      };
      setConnectionResult({ success: result.success, message: messages[result.code] ?? result.message });
      setSmtp(await outreachApi.smtpSettings(slug));
    });
  }

  async function sendTestEmail() {
    if (!slug || !canEdit || !testRecipient) return;
    if (!window.confirm(`Send one real SMTP test email to ${testRecipient}? No bid invitation will be sent.`)) return;
    await act(async () => {
      const result = await outreachApi.sendSMTPTestEmail(slug, testRecipient);
      setNotice(result.message);
      setTestRecipient("");
    });
  }

  if (!slug) return <Card className="mt-6 p-6">Select an organization to view its settings.</Card>;
  return <div className="mt-6 grid max-w-4xl gap-5">
    {error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
    {notice && <p role="status" className="rounded-lg bg-blue-50 p-3 text-sm text-blue-800">{notice}</p>}
    <Card className="space-y-4 p-6">
      <div><h2 className="text-lg font-semibold text-slate-900">Email Delivery / SMTP Setup</h2><p className="mt-1 text-sm text-slate-600">Configure your mail server here. Nothing connects or sends until an Admin explicitly tests or sends.</p></div>
      <p className="rounded-lg bg-slate-50 p-3 text-sm text-slate-700">Status: {smtp?.provider.label ?? "Loading…"} · Security: {smtp?.provider.tls_mode ?? "Not set"}. {smtp?.provider.encryption_ready === false ? "A server encryption key must be set before saving a password." : ""}</p>
      {canEdit && smtpForm && <>
        <label className="block text-sm font-medium">Provider<select value="smtp" disabled className="mt-1 block w-full rounded-lg border p-2"><option value="smtp">Custom SMTP</option></select></label>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="text-sm font-medium">SMTP host<input value={smtpForm.host} disabled={busy} onChange={(event) => setSmtpForm({ ...smtpForm, host: event.target.value })} placeholder="smtp.example.com" className="mt-1 block w-full rounded-lg border p-2" /></label>
          <label className="text-sm font-medium">SMTP port<input type="number" min={1} max={65535} value={smtpForm.port} disabled={busy} onChange={(event) => setSmtpForm({ ...smtpForm, port: Number(event.target.value) })} className="mt-1 block w-full rounded-lg border p-2" /></label>
          <label className="text-sm font-medium">Username<input value={smtpForm.username} disabled={busy} onChange={(event) => setSmtpForm({ ...smtpForm, username: event.target.value })} autoComplete="username" className="mt-1 block w-full rounded-lg border p-2" /></label>
          <label className="text-sm font-medium">Password / App Password<input type="password" value={smtpForm.password} disabled={busy || smtpForm.clear_password} onChange={(event) => setSmtpForm({ ...smtpForm, password: event.target.value })} autoComplete="new-password" placeholder={smtp?.password_saved ? "Leave blank to keep saved password" : "Enter password"} className="mt-1 block w-full rounded-lg border p-2" />{smtp?.password_saved && <span className="mt-1 block text-xs text-emerald-700">Password saved securely. It cannot be displayed.</span>}</label>
          <label className="text-sm font-medium">Security<select value={smtpForm.security} disabled={busy} onChange={(event) => setSmtpForm({ ...smtpForm, security: event.target.value as SMTPForm["security"] })} className="mt-1 block w-full rounded-lg border p-2"><option value="starttls">STARTTLS</option><option value="ssl">SSL</option><option value="none">None (cannot enable delivery)</option></select></label>
          <label className="text-sm font-medium">Connection timeout (seconds)<input type="number" min={1} max={120} value={smtpForm.timeout_seconds} disabled={busy} onChange={(event) => setSmtpForm({ ...smtpForm, timeout_seconds: Number(event.target.value) })} className="mt-1 block w-full rounded-lg border p-2" /></label>
        </div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={smtpForm.clear_password} disabled={busy} onChange={(event) => setSmtpForm({ ...smtpForm, clear_password: event.target.checked, password: "", is_enabled: event.target.checked ? false : smtpForm.is_enabled })} />Clear saved password (also disables delivery)</label>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={smtpForm.is_enabled} disabled={busy} onChange={(event) => setSmtpForm({ ...smtpForm, is_enabled: event.target.checked })} />Enable outreach email delivery</label>
        <div className="flex flex-wrap gap-2"><button type="button" disabled={busy} onClick={() => void saveSMTP()} className="rounded-lg bg-[#173f5f] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Save SMTP setup</button><button type="button" disabled={busy || !smtp?.password_saved} onClick={() => void testConnection()} className="rounded-lg border px-4 py-2 text-sm font-semibold disabled:opacity-50">Test SMTP Connection</button></div>
        {connectionResult && <p role="status" className={`rounded-lg p-3 text-sm ${connectionResult.success ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-900"}`}>{connectionResult.message}</p>}
        <div className="rounded-lg border p-4"><h3 className="font-semibold">Send Test Email</h3><p className="mt-1 text-sm text-slate-600">Enter your controlled test mailbox. Contractor contact addresses cannot be used. This sends one real test message, not an invitation.</p><div className="mt-3 flex flex-wrap gap-2"><input type="email" aria-label="Controlled test recipient email" value={testRecipient} disabled={busy} onChange={(event) => setTestRecipient(event.target.value)} placeholder="your-test-mailbox@example.com" className="min-w-64 flex-1 rounded-lg border p-2 text-sm" /><button type="button" disabled={busy || testEmailBlockers.length > 0} onClick={() => void sendTestEmail()} className="rounded-lg border border-blue-300 px-4 py-2 text-sm font-semibold text-blue-800 disabled:opacity-50">Send Test Email</button></div>{testEmailBlockers.length > 0 && <div className="mt-2 text-sm text-amber-800"><p>Before sending a test email:</p><ul className="ml-5 list-disc">{testEmailBlockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul></div>}</div>
      </>}
    </Card>
    <Card className="space-y-4 p-6"><div><h2 className="text-lg font-semibold">Outreach sender identity</h2><p className="mt-1 text-sm text-slate-600">The From and Reply-To addresses are frozen into each prepared invitation. SMTP credentials are stored separately and never shown here.</p></div>{sender ? <>{([ ["Sender display name", "display_name"], ["From email", "from_address"], ["Reply-To email", "reply_to"] ] as const).map(([label, field]) => <label key={field} className="block text-sm font-medium">{label}<input type={field === "display_name" ? "text" : "email"} value={sender[field]} disabled={!canEdit || busy} onChange={(event) => setSender({ ...sender, [field]: event.target.value })} className="mt-1 block w-full rounded-lg border p-2 disabled:bg-slate-50" /></label>)}<label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={sender.is_enabled ?? false} disabled={!canEdit || busy} onChange={(event) => setSender({ ...sender, is_enabled: event.target.checked })} />Enable this sender for outreach</label>{canEdit && <button type="button" disabled={busy} onClick={() => void saveSender()} className="rounded-lg bg-[#173f5f] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Save sender settings</button>}</> : <p className="text-sm text-slate-500">Loading sender settings…</p>}</Card>
  </div>;
}
