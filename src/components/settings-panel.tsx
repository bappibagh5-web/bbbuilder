"use client";

import { RotateCcw } from "lucide-react";
import { DemoNotice } from "./demo-notice";
import { Card } from "./ui/card";
import { Button } from "./ui/button";

const sections = [
  [
    "Organization",
    [
      ["Company", "BB Builders"],
      ["Default Region", "British Columbia"],
      ["Default Currency", "CAD"],
    ],
  ],
  [
    "Bid Invitation Defaults",
    [
      ["Questions deadline", "6 days before bid deadline"],
      ["Reminder schedule", "3 days and 1 day before deadline"],
      ["Delivery", "Simulated — no emails are sent"],
    ],
  ],
  [
    "Proposal Defaults",
    [
      ["Contingency", "3%"],
      ["GC overhead and profit", "10%"],
      ["Warranty", "1 year from substantial completion"],
    ],
  ],
] as const;

export function SettingsPanel() {
  return (
    <div className="mt-6 grid gap-5 xl:grid-cols-3">
      {sections.map(([title, rows]) => (
        <Card key={title} className="p-5">
          <h2 className="font-semibold text-slate-900">{title}</h2>
          <dl className="mt-4 divide-y">
            {rows.map(([label, value]) => (
              <div
                key={label}
                className="flex items-start justify-between gap-4 py-3 first:pt-0 last:pb-0"
              >
                <dt className="text-sm text-slate-500">{label}</dt>
                <dd className="text-right text-sm font-medium text-slate-800">
                  {value}
                </dd>
              </div>
            ))}
          </dl>
        </Card>
      ))}
      <Card className="p-5 xl:col-span-3">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="font-semibold text-slate-900">Demo Environment</h2>
            <p className="mt-1 text-sm text-slate-500">
              Settings and interactions are temporary and reset when the
              application reloads.
            </p>
          </div>
          <Button onClick={() => window.location.reload()}>
            <RotateCcw className="h-4 w-4" />
            Reload Demo State
          </Button>
        </div>
        <DemoNotice className="mt-4" />
      </Card>
    </div>
  );
}
