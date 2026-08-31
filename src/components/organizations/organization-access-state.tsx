import { Building2 } from "lucide-react";
import { Card } from "@/components/ui/card";

export function OrganizationAccessState({ multiple }: { multiple: boolean }) {
  return (
    <Card className="mx-auto flex min-h-64 max-w-2xl flex-col items-center justify-center p-8 text-center">
      <span className="rounded-xl bg-slate-100 p-3 text-slate-500"><Building2 className="h-6 w-6" /></span>
      <h2 className="mt-4 text-lg font-semibold text-slate-900">{multiple ? "Select an organization" : "No active organization access"}</h2>
      <p className="mt-2 max-w-md text-sm leading-6 text-slate-500">{multiple ? "Choose the organization you want to work in using the organization control above." : "Your account does not currently have an active organization membership. Contact an administrator for access."}</p>
    </Card>
  );
}
