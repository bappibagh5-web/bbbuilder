import { Info } from "lucide-react";
import { cn } from "@/lib/utils";

export function DemoNotice({
  className,
  detail = "Data, AI findings, communication activity, and pricing shown in this prototype are simulated.",
}: {
  className?: string;
  detail?: string;
}) {
  return (
    <aside
      aria-label="Demo environment notice"
      className={cn(
        "flex gap-3 rounded-xl border border-blue-200 bg-blue-50/70 px-4 py-3 text-blue-950",
        className,
      )}
    >
      <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <div>
        <p className="text-xs font-semibold">Demo Environment</p>
        <p className="mt-0.5 text-xs leading-5 text-blue-800">{detail}</p>
      </div>
    </aside>
  );
}
