// The only place the frontend talks to the backend. No database access, no secrets.
import type { Application, ApplicationInput, FieldError, Stats, Token, User } from "./types";

const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
const TOKEN_KEY = "jobtracker_token";

/** An error the UI can show as-is. */
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: FieldError[] = [],
  ) {
    super(message);
  }
}

// ----- Token storage (see README: "Token storage trade-off") -----

export function getToken(): string | null {
  return typeof window === "undefined" ? null : sessionStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
}

// ----- Request helper -----

async function send(path: string, options: RequestInit = {}): Promise<Response> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { ...options, headers });
  } catch {
    throw new ApiError(0, "network_error", "Can't reach the server. Check it's running and try again.");
  }
  if (!response.ok) await throwApiError(response);
  return response;
}

async function throwApiError(response: Response): Promise<never> {
  const body = await response.json().catch(() => null);
  const error = body?.error;
  throw new ApiError(
    response.status,
    error?.code ?? "unknown_error",
    error?.message ?? "Something went wrong. Please try again.",
    error?.details ?? [],
  );
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await send(path, options);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

// ----- Endpoints -----

export const api = {
  register: (email: string, password: string) =>
    request<User>("/auth/register", { method: "POST", body: JSON.stringify({ email, password }) }),

  login: (email: string, password: string) =>
    request<Token>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),

  me: () => request<User>("/auth/me"),

  listApplications: () => request<{ items: Application[] }>("/applications"),

  createApplication: (input: ApplicationInput) =>
    request<Application>("/applications", { method: "POST", body: JSON.stringify(input) }),

  updateApplication: (id: number, changes: Partial<ApplicationInput>) =>
    request<Application>(`/applications/${id}`, { method: "PATCH", body: JSON.stringify(changes) }),

  deleteApplication: (id: number) => request<void>(`/applications/${id}`, { method: "DELETE" }),

  getStats: () => request<Stats>("/applications/stats"),

  /** The CSV as a Blob, ready to save. Fetched with the token, so a plain link won't do. */
  exportCsv: async () => (await send("/applications/export")).blob(),

  importCsv: (csv: string) =>
    request<{ imported: number }>("/applications/import", { method: "POST", body: JSON.stringify({ csv }) }),
};
