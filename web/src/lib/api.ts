// Centralized API base URL.
// Defaults to localhost:8000 (FastAPI dev server) but can be overridden
// via NEXT_PUBLIC_API_URL for deployed / remote backends.
export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
