export async function api<T>(
  path: string,
  init: RequestInit = {},
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    credentials: "same-origin",
    signal,
    headers: {
      "Content-Type": "application/json",
      "X-Workbench-Request": "1",
      ...init.headers,
    },
  });
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401)
      window.dispatchEvent(new Event("wb-session-expired"));
    const detail =
      typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail);
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return data as T;
}

export const dateTime = (value?: string | null) =>
  value
    ? new Date(value).toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
        timeZone: "UTC",
      }) + " UTC"
    : "Unknown time";
export const inputDate = (value: string) =>
  new Date(value).toISOString().slice(0, 16);
