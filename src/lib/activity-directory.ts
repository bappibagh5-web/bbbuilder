import { apiRequest } from "@/lib/api-client";

export type ActivityProject = { id: number; project_number: string; name: string };
export type ActivityItem = { id: number; timestamp: string; actor: string; project: ActivityProject | null; family: string; family_label: string; label: string; target_type: string; target_reference: string | null; route: string | null };
export type ActivityDirectoryResponse = { count: number; next: string | null; previous: string | null; page: number; page_size: number; results: ActivityItem[]; filters: { projects: ActivityProject[]; families: { value: string; label: string }[] } };

export function getOrganizationActivity(slug: string, query: URLSearchParams, signal?: AbortSignal) {
  const suffix = query.toString();
  return apiRequest<ActivityDirectoryResponse>(`/organizations/${encodeURIComponent(slug)}/activity/${suffix ? `?${suffix}` : ""}`, { signal });
}
