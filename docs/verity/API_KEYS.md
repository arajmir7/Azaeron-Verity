# Workspace API keys

Owners/admins manage `/api/v1/api-keys` using their browser session. Creation and
rotation return a secret once with `Cache-Control: no-store`. Listing returns only
metadata. Save the secret securely; if the response is lost, revoke the key shown
in the list and create another. The server cannot recover its secret.

Send `X-API-Key` over HTTPS. Do not send an Authorization header at the same time.
Keys belong to one organization and the issuing account. Revoking that account's
membership disables its keys. A key's scopes never grant additional membership
permissions. Create accepts name, explicit scopes, and an optional timezone-aware
expiry within 365 days. There are at most 50 active keys per workspace.

| Scope | Allowed route family |
| --- | --- |
| `text:analyze` | POST `/text/analyze`; GET `/models` |
| `text:refine` | POST `/text/refine` |
| `text:verify` | POST `/text/verify` |
| `documents:read` | GET `/documents` and subroutes; GET `/jobs` and subroutes |
| `documents:write` | Document mutations; POST `/jobs/{id}/cancel` |
| `usage:read` | GET `/usage` |

Paths have the `/api/v1` prefix. OpenAPI annotates each supported operation with
`x-api-key-scopes`. Text analysis and usage accounting are implemented; granting
a scope does not make an unavailable model operation available.
Unavailable model-backed operations fail explicitly without external AI fallback.

DELETE `/api-keys/{id}` revokes idempotently. POST `/api-keys/{id}/rotate` revokes
and replaces atomically, preserving name/scopes/expiry. Only one concurrent rotation
can succeed. Expired keys cannot rotate. Last-use timestamps are recorded at
successful authentication; they do not imply downstream work completed. Revocation
blocks new authentication; it does not interrupt already admitted work.

Rate limits aggregate all calls at 60/minute/key and 300/minute/organization. A 429
includes `Retry-After`. Production returns 503 when the required limiter is down.
Never put keys in URLs, logs, localStorage or sessionStorage.
