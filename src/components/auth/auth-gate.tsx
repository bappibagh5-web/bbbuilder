"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { Building2 } from "lucide-react";
import { useAuth } from "./auth-provider";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const { status } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [pathname, router, status]);

  if (status !== "authenticated") {
    return (
      <div className="grid min-h-screen place-items-center bg-slate-100">
        <div className="flex items-center gap-3 text-sm font-medium text-slate-600">
          <Building2 className="h-5 w-5 animate-pulse text-[#163451]" />
          Verifying secure session…
        </div>
      </div>
    );
  }
  return children;
}
