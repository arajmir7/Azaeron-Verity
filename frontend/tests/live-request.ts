import type { APIRequestContext } from "@playwright/test";

/** Keep live authentication limits enabled and honor their explicit retry window. */
export async function postWithRetryAfter(request: APIRequestContext, path: string, options: Parameters<APIRequestContext["post"]>[1]) {
  for (let attempt = 0; ; attempt++) {
    const response = await request.post(path, options);
    if (response.status() !== 429 || attempt >= 2) return response;
    const seconds = Number(response.headers()["retry-after"]);
    if (!Number.isFinite(seconds) || seconds < 0 || seconds > 120) return response;
    await response.dispose();
    console.info(`Live authentication respected Retry-After: ${seconds}s`);
    await new Promise((resolve) => setTimeout(resolve, (seconds + 1) * 1000));
  }
}
