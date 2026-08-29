import { apiRequest } from "@/lib/api-client";

export type OrganizationMembership = {
  id: number;
  role: "admin" | "estimator_operator" | "viewer";
  organization: { id: number; name: string; slug: string };
};

export type AuthUser = {
  id: number;
  email: string;
  firstName: string;
  lastName: string;
  memberships: OrganizationMembership[];
};

type AuthResponse = { user: AuthUser };

export const authApi = {
  csrf: () => apiRequest<{ csrfToken: string }>("/auth/csrf/", { notifyUnauthorized: false }),
  me: () => apiRequest<AuthResponse>("/auth/me/", { notifyUnauthorized: false }),
  async login(email: string, password: string) {
    const { csrfToken } = await this.csrf();
    return apiRequest<AuthResponse>("/auth/login/", {
      method: "POST",
      body: JSON.stringify({ email, password }),
      csrfToken,
      notifyUnauthorized: false,
    });
  },
  async logout() {
    const { csrfToken } = await this.csrf();
    return apiRequest<{ detail: string }>("/auth/logout/", { method: "POST", csrfToken });
  },
};

export function roleLabel(role?: OrganizationMembership["role"]) {
  if (role === "admin") return "Admin";
  if (role === "estimator_operator") return "Estimator / Operator";
  if (role === "viewer") return "Viewer";
  return "Member";
}
