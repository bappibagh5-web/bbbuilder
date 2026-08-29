const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
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

async function detail(response: Response) {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail;
  } catch {
    return undefined;
  }
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit & { csrfToken?: string; notifyUnauthorized?: boolean } = {},
) {
  const { csrfToken, notifyUnauthorized = true, ...requestOptions } = options;
  const headers = new Headers(requestOptions.headers);
  if (requestOptions.body) headers.set("Content-Type", "application/json");
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
    throw new ApiError((await detail(response)) ?? "The request could not be completed.", response.status);
  }
  return (await response.json()) as T;
}
