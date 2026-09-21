import { apiRequest } from "@/lib/api-client";

export type SettingsOrganization = { id: number; name: string; legal_name: string; slug: string; status: string; status_label: string; default_timezone: string; created_at: string };
export type SettingsAccess = { role: "admin" | "estimator_operator" | "viewer"; role_label: string; can_manage_members: boolean };
export type OrganizationSettingsResponse = { organization: SettingsOrganization; access: SettingsAccess };
export type MembershipRole = "admin" | "estimator_operator" | "viewer";
export type OrganizationMember = { id: number; user_id: number; email: string; first_name: string; last_name: string; display_name: string; role: MembershipRole; role_label: string; is_active: boolean; membership_enabled: boolean; starts_at: string; ends_at: string | null; created_at: string; date_joined: string; last_login: string | null; can_change_role: boolean; can_deactivate: boolean; can_reactivate: boolean };
export type MembershipListResponse = { can_manage_members: boolean; results: OrganizationMember[]; roles: { value: MembershipRole; label: string }[] };

function root(slug: string) { return `/organizations/${encodeURIComponent(slug)}`; }
export const settingsApi = {
  organization(slug: string, signal?: AbortSignal) { return apiRequest<OrganizationSettingsResponse>(`${root(slug)}/settings/`, { signal }); },
  memberships(slug: string, signal?: AbortSignal) { return apiRequest<MembershipListResponse>(`${root(slug)}/memberships/`, { signal }); },
  addMembership(slug: string, email: string, role: MembershipRole) { return apiRequest<OrganizationMember>(`${root(slug)}/memberships/`, { method: "POST", body: JSON.stringify({ email, role }) }); },
  updateMembership(slug: string, id: number, values: { role?: MembershipRole; is_active?: boolean }) { return apiRequest<OrganizationMember>(`${root(slug)}/memberships/${id}/`, { method: "PATCH", body: JSON.stringify(values) }); },
};
