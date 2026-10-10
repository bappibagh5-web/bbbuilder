"use client";

import { useEffect, useState } from "react";
import { prospectingApi } from "@/lib/prospecting";

export function UnsubscribePage({ token }: { token: string }) {
  const [state, setState] = useState("loading");
  useEffect(() => { prospectingApi.publicUnsubscribe(token).then((value) => setState(value.state)).catch(() => setState("invalid")); }, [token]);
  if (state === "loading") return <Panel title="Checking unsubscribe link…" />;
  if (state === "invalid") return <Panel title="This unsubscribe link is invalid or unavailable." />;
  if (state === "unsubscribed" || state === "already_unsubscribed") return <Panel title="You are unsubscribed." detail="No further BB Builders Prospecting messages will be sent to this email unless suppression is explicitly removed and you are enrolled again." />;
  return <Panel title="Unsubscribe from BB Builders Prospecting" detail="This will stop current and future Prospecting sequences for this email address."><button onClick={() => void prospectingApi.publicUnsubscribe(token, true).then((value) => setState(value.state))} className="mt-5 rounded-lg bg-slate-950 px-4 py-2 font-semibold text-white">Confirm unsubscribe</button></Panel>;
}

function Panel({ title, detail, children }: { title: string; detail?: string; children?: React.ReactNode }) { return <main className="grid min-h-screen place-items-center bg-slate-50 p-6"><section className="w-full max-w-lg rounded-2xl border bg-white p-8 shadow-sm"><h1 className="text-xl font-bold">{title}</h1>{detail && <p className="mt-3 text-sm text-slate-600">{detail}</p>}{children}</section></main>; }
