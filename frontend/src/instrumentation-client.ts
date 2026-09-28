import { reportBrowserError } from "@/lib/telemetry";
window.addEventListener("error", () => reportBrowserError("unhandled_error"));
window.addEventListener("unhandledrejection", () => reportBrowserError("unhandled_rejection"));
