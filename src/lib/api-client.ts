const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly payload?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function cookie(name: string) {
  if (typeof document === "undefined") return undefined;
  const item = document.cookie
    .split(";")
    .map((value) => value.trim())
    .find((value) => value.startsWith(`${name}=`));
  return item ? decodeURIComponent(item.slice(name.length + 1)) : undefined;
}

async function errorPayload(response: Response) {
  try {
    return (await response.json()) as unknown;
  } catch {
    return undefined;
  }
}

function errorMessage(payload: unknown) {
  if (!payload || typeof payload !== "object") return undefined;
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  const nonField = (payload as { non_field_errors?: unknown }).non_field_errors;
  if (Array.isArray(nonField) && typeof nonField[0] === "string") return nonField[0];
  for (const value of Object.values(payload)) {
    if (Array.isArray(value) && typeof value[0] === "string") return value[0];
    if (typeof value === "string") return value;
  }
  return undefined;
}

export async function apiResponse(
  path: string,
  options: RequestInit & { csrfToken?: string; notifyUnauthorized?: boolean } = {},
) {
  const { csrfToken, notifyUnauthorized = true, ...requestOptions } = options;
  const headers = new Headers(requestOptions.headers);
  if (typeof requestOptions.body === "string") headers.set("Content-Type", "application/json");
  const method = requestOptions.method?.toUpperCase() ?? "GET";
  if (!["GET", "HEAD", "OPTIONS", "TRACE"].includes(method)) {
    const token = csrfToken ?? cookie("csrftoken");
    if (token) headers.set("X-CSRFToken", token);
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...requestOptions,
      headers,
      credentials: "include",
    });
  } catch {
    throw new ApiError("The BB Builders service is unavailable. Try again shortly.", 0);
  }

  if (!response.ok) {
    if (response.status === 401 && notifyUnauthorized) {
      window.dispatchEvent(new Event("bb-auth-unauthorized"));
    }
    const payload = await errorPayload(response);
    throw new ApiError(
      errorMessage(payload) ?? "The request could not be completed.",
      response.status,
      payload,
    );
  }
  return response;
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit & { csrfToken?: string; notifyUnauthorized?: boolean } = {},
) {
  const response = await apiResponse(path, options);
  return (await response.json()) as T;
}
