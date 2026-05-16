/** Base URL for FastAPI (no trailing slash). Set in `frontend/.env.local`. */
export function getApiBaseUrl(): string {
  const raw = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
  return raw.replace(/\/+$/, "");
}
