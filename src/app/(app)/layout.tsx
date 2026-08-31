import { AppShell } from "@/components/app-shell";
import { AuthGate } from "@/components/auth/auth-gate";
import { OrganizationProvider } from "@/components/organizations/organization-provider";

export default function ProductLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGate>
      <OrganizationProvider>
        <AppShell>{children}</AppShell>
      </OrganizationProvider>
    </AuthGate>
  );
}
