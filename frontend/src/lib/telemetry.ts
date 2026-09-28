/** Report closed metadata only. Never accept an Error, message, stack or URL. */
let lastReportAt = 0;
function routeCategory() {
  const path = window.location.pathname;
  if (/^\/documents\//.test(path)) return "editor";
  if (path === "/documents") return "documents";
  if (path === "/settings") return "settings";
  if (path === "/upload") return "upload";
  if (/^\/(login|signup|verify-email|reset-password)$/.test(path)) return "auth";
  if (path === "/workspace") return "workspace";
  return "other";
}
export function reportBrowserError(kind: "render" | "unhandled_error" | "unhandled_rejection") {
  if (Date.now() - lastReportAt < 10_000) return;
  lastReportAt = Date.now();
  void fetch("/api/v1/telemetry/browser", {
    method: "POST", credentials: "same-origin", keepalive: true,
    headers: { "Content-Type": "application/json", "X-Request-ID": crypto.randomUUID() },
    body: JSON.stringify({ kind, route: routeCategory(), event_id: crypto.randomUUID() }),
  }).catch(() => { /* Reporting must never cause an error loop. */ });
}
