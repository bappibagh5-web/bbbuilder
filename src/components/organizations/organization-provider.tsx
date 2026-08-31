"use client";

import { createContext, useContext, useMemo, useState } from "react";
import type { OrganizationMembership } from "@/lib/auth";
import { useAuth } from "@/components/auth/auth-provider";

type OrganizationContextValue = {
  memberships: OrganizationMembership[];
  activeMembership: OrganizationMembership | null;
  selectOrganization: (slug: string) => void;
};

const OrganizationContext = createContext<OrganizationContextValue | null>(null);
const noMemberships: OrganizationMembership[] = [];

export function OrganizationProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const memberships = user?.memberships ?? noMemberships;
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);

  const value = useMemo<OrganizationContextValue>(
    () => ({
      memberships,
      activeMembership: memberships.length === 1
        ? memberships[0]
        : memberships.find((item) => item.organization.slug === selectedSlug) ?? null,
      selectOrganization(slug) {
        if (memberships.some((item) => item.organization.slug === slug)) setSelectedSlug(slug);
      },
    }),
    [memberships, selectedSlug],
  );

  return <OrganizationContext.Provider value={value}>{children}</OrganizationContext.Provider>;
}

export function useOrganization() {
  const context = useContext(OrganizationContext);
  if (!context) throw new Error("useOrganization must be used within OrganizationProvider.");
  return context;
}

export function canEditProjects(membership: OrganizationMembership | null) {
  return membership?.role === "admin" || membership?.role === "estimator_operator";
}
