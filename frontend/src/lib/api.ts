/** AZAERON API client */
import type { Organization, ProductRole, User } from "@/lib/store";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

export interface AuthResponse {
  access_token: string | null;
  refresh_token: string | null;
  token_type: "bearer";
  expires_in: number;
  user: User;
}

export interface UserProfile extends User {
  organizations: Array<{
    id: string;
    organization_id: string;
    organization_name: string;
    organization_slug: string;
    role: string;
    is_active: boolean;
    joined_at: string;
  }>;
  active_organization_id: string | null;
}

export class ApiError extends Error {
  constructor(public readonly status: number, public readonly code?: string, message = "Request failed") {
    super(message);
    this.name = "ApiError";
  }
}

export interface DocumentRecord {
  id: string;
  organization_id?: string;
  owner_id?: string;
  title: string | null;
  original_filename: string;
  file_size: number;
  status: string;
  created_at: string;
  updated_at?: string;
  uploaded_at?: string;
  processed_at?: string | null;
  error_message?: string | null;
  word_count?: number | null;
  language?: string | null;
  mime_type?: string;
  extension?: string;
  sha256_fingerprint?: string;
}

export interface DocumentList {
  items: DocumentRecord[];
  total: number;
  page: number;
  page_size: number;
}

export interface DocumentContent {
  parser_version: string;
  normalized_content_hash: string | null;
  structure_fingerprint: string | null;
  document_id: string;
  document_version_id: string;
  content: string;
  paragraphs: Array<Record<string, unknown>>;
  sentences: Array<Record<string, unknown>>;
  pipeline_version: string;
  model_version: string | null;
  extracted_at: string | null;
}

export interface SimilarityMatch {
  id: string;
  source_document_id: string | null;
  target_document_id: string;
  evidence_id: string | null;
  match_type: string;
  document_span_start: number;
  document_span_end: number;
  source_span_start: number | null;
  source_span_end: number | null;
  similarity_score: number;
  retrieval_score: number | null;
  lexical_score: number | null;
  ngram_score: number | null;
  semantic_score: number | null;
  structural_score: number | null;
  verification_score: number | null;
  confidence: number;
  confidence_reliability: string;
  matched_text: string | null;
  source_text: string | null;
  retrieval_methods: string[] | null;
  verification_methods: string[] | null;
  metadata_json: Record<string, unknown> | null;
  pipeline_version: string;
  model_version: string | null;
  created_at: string;
}

export interface SimilarityMatchList {
  matches: SimilarityMatch[];
  total: number;
  similarity_is_not_plagiarism: boolean;
  limitations: string[];
}

export interface CitationFinding {
  id: string;
  claim_id: string | null;
  citation_id: string | null;
  reference_id: string | null;
  source_id: string | null;
  evidence_id: string | null;
  finding_type: string;
  support_status: "SUPPORTED" | "PARTIALLY_SUPPORTED" | "NOT_SUPPORTED" | "UNVERIFIABLE";
  message: string;
  evidence_json: Record<string, unknown> | null;
  created_at: string;
}

export interface CitationAnalysis {
  findings: CitationFinding[];
  citations: Array<{ id: string; raw_text: string; support_status: string; source_id: string | null; evidence_id: string | null }>;
  references: Array<{ id: string; title: string | null; doi: string | null; url: string | null; source_id: string | null }>;
  sources: Array<{ id: string; title: string | null; publisher: string | null; doi: string | null; url: string | null; retrieval_status: string; retrieval_timestamp: string | null }>;
  limitations: string[];
}

export interface AuthorshipSignal {
  id: string;
  document_id: string;
  profile_id: string | null;
  verdict: "CONSISTENT" | "DEVIATION" | "STRONG_DEVIATION" | "INSUFFICIENT_DATA";
  baseline_quality: string | null;
  consistency_score: number | null;
  confidence: number | null;
  confidence_type: string | null;
  stylistic_deviation: Record<string, unknown> | null;
  ai_writing_signal: Record<string, unknown> | null;
  feature_data: Record<string, unknown> | null;
  evidence_id: string | null;
  explanation: string | null;
  limitations: string | null;
  pipeline_version: string;
  model_version: string | null;
  document_version_id: string;
  created_at: string;
}

export interface ProvenanceTimeline {
  schema_version: string;
  document: { id: string; organization_id: string; status: string; content_hash: string; storage_object: string; created_at: string | null; uploaded_at: string | null };
  versions: Array<{ id: string; version_number: number; content_hash: string; sha256_fingerprint: string; created_by_id: string; uploaded_by_id: string | null; created_at: string | null; uploaded_at: string | null; storage_object: string; previous_version_id: string | null; lifecycle_state: string; change_summary: string | null; edit_type: string | null }>;
  analysis_runs: Array<{ id: string; document_version_id: string; model_id: string; model_version: string; pipeline_version: string; status: string; abstained: boolean; input_fingerprint: string | null; started_at: string | null; completed_at: string | null; metadata: Record<string, unknown> }>;
  provenance_events: Array<{ id: string; event_type: string; document_version_id: string; analysis_run_id: string | null; user_id: string | null; event_timestamp: string | null; description: string | null; sha256_before: string | null; sha256_after: string | null; metadata: Record<string, unknown>; pipeline_version: string; model_version: string | null }>;
  limitations: string[];
}

export interface AegisChange {
  id: string;
  edit_type?: string;
  dimension: string;
  original: string;
  revision: string;
  change_reason: string;
  span_start: number;
  span_end: number;
  applied: boolean;
  ai_generated?: boolean;
  document_id?: string;
  document_version_id?: string;
  preserve_voice?: boolean;
  engine_version?: string;
  created_at?: string;
}

export interface AegisRefineResult {
  document_id: string;
  document_version_id: string;
  original_text: string;
  revised_text: string;
  changes: AegisChange[];
  disclaimer: string;
}

export interface EvidenceGraph {
  schema_version: string;
  document_id: string | null;
  document_version_id: string | null;
  complete: boolean;
  orphan_finding_node_ids: string[];
  nodes: Array<{
    id: string;
    node_id: string;
    canonical_type: string;
    entity_id: string;
    entity_type: string;
    document_id: string;
    organization_id: string | null;
    document_version_id: string | null;
    finding_type: string;
    source_id: string | null;
    model_id: string | null;
    model_version: string | null;
    pipeline_version: string | null;
    title: string;
    description: string | null;
    span_start: number | null;
    span_end: number | null;
    span_text: string | null;
    confidence: number;
    metadata_json: Record<string, unknown> | null;
  }>;
  edges: Array<{
    organization_id: string | null;
    source_node_id: string;
    target_node_id: string;
    edge_type: string;
    weight: number;
    description: string | null;
    metadata_json: Record<string, unknown> | null;
  }>;
  limitations: string[];
}

export interface EvidenceFirstReport {
  schema_version: string;
  report_status: "PRODUCTION" | "EXPERIMENTAL" | "INSUFFICIENT_EVIDENCE" | string;
  document_id: string;
  document_version_id: string | null;
  generated_at: string;
  dimensions: Array<{
    key: string;
    label: string;
    status: "PRODUCTION" | "EXPERIMENTAL" | "INSUFFICIENT_EVIDENCE" | string;
    summary: string;
    confidence: number | null;
    confidence_reliability: string;
    evidence: Array<{
      evidence_node_id: string;
      canonical_type: string;
      title: string;
      explanation: string;
      span_start: number | null;
      span_end: number | null;
      span_text: string | null;
      confidence: number | null;
      confidence_reliability: string;
      source_ids: string[];
      source_titles: string[];
      claim_ids: string[];
      citation_ids: string[];
    }>;
    limitations: string[];
    recommended_action: string;
  }>;
  highlights: Array<{
    evidence_node_id: string;
    canonical_type: string;
    title: string;
    explanation: string;
    span_start: number | null;
    span_end: number | null;
    span_text: string | null;
    confidence: number | null;
    confidence_reliability: string;
    source_ids: string[];
    source_titles: string[];
    claim_ids: string[];
    citation_ids: string[];
    dimension: string;
    segment_type: string;
    status: string;
  }>;
  limitations: string[];
  graph: EvidenceGraph;
}

export type DetectionVerdict = "human" | "ai_generated" | "ai" | "mixed" | "ai_assisted" | "uncertain" | "insufficient_evidence";

export interface DetectionSegment {
  segment_type: string;
  segment_index: number;
  text: string;
  span_start: number;
  span_end: number;
  verdict: DetectionVerdict;
  confidence: number | null;
  feature_scores: Record<string, number | null> | null;
  explanation: string | null;
}

export interface DetectionResult {
  id: string;
  document_id: string;
  model_version: string;
  pipeline_version: string;
  document_version_id: string | null;
  release_status: string;
  abstained: boolean;
  overall_verdict: DetectionVerdict;
  confidence: number | null;
  calibration_score: number | null;
  explanation: string | null;
  limitations: string | null;
  feature_version: string;
  calibrator_version: string | null;
  uncertainty_method: string | null;
  confidence_reliability: string;
  inference_id: string;
  abstention_reason: string | null;
  segments: DetectionSegment[];
  created_at: string;
}

export interface DetectionExplainability {
  what_this_means: string;
  how_this_was_calculated: string;
  evidence_used: string[];
  what_this_does_not_prove: string;
  confidence_interval: string | null;
  known_limitations: string[];
}

export interface UploadRequest {
  upload_id: string;
  upload_url: string;
  storage_key: string;
  expires_at: string;
}

export interface UsageSummary {
  period: string;
  unit: "operations";
  billing_enabled: boolean;
  limits: { task: string; limit: number; reserved: number; committed: number }[];
}

export type ApiKeyScope = "text:analyze" | "text:refine" | "text:verify" | "documents:read" | "documents:write" | "usage:read" | "ai:chat";
export interface ApiKeyMetadata {
  id: string; name: string; key_prefix: string; scopes: ApiKeyScope[];
  user_id: string; organization_id: string; created_at: string;
  expires_at: string | null; last_used_at: string | null;
  revoked_at: string | null; is_active: boolean; rotated_from_id: string | null;
}
export interface CreatedApiKey { key: ApiKeyMetadata; secret: string; }
export type ErasureScope = "document" | "organization" | "account";
export interface ErasureStatus { id: string; scope: ErasureScope; status: string; created_at: string; completed_at: string | null; last_error: string | null; }

export class ApiClient {
  private baseUrl: string;
  private refreshInFlight: Promise<AuthResponse> | null = null;
  constructor(baseUrl: string = API_BASE) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(endpoint: string, options: RequestInit = {}, allowRefresh = true): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...((options.headers as Record<string, string>) || {}),
    };
    const response = await fetch(url, { ...options, headers, credentials: "include" });
    const canRefresh = allowRefresh && ![
      "/api/v1/auth/login",
      "/api/v1/auth/register",
      "/api/v1/auth/refresh",
      "/api/v1/auth/logout",
    ].includes(endpoint);
    if (response.status === 401 && canRefresh) {
      try {
        // Rotate once when parallel document requests encounter an expired
        // cookie. Reusing the same refresh token would revoke the session.
        if (!this.refreshInFlight) {
          this.refreshInFlight = this.request<AuthResponse>("/api/v1/auth/refresh", { method: "POST", body: "{}" }, false)
            .finally(() => { this.refreshInFlight = null; });
        }
        await this.refreshInFlight;
        return this.request<T>(endpoint, options, false);
      } catch {
        // The original 401 remains the authoritative result when the session
        // cannot be refreshed. The shell will route the user to sign-in.
      }
    }
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Unknown error" }));
      const detail = error.detail;
      const message = typeof detail === "string" ? detail : detail?.message || `HTTP ${response.status}`;
      throw new ApiError(response.status, typeof detail === "object" ? detail?.code : undefined, message);
    }
    if (response.status === 204) return undefined as T;
    return response.json();
  }

  async login(email: string, password: string, mfaCode?: string) {
    return this.request<AuthResponse>("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ email, password, mfa_code: mfaCode }) });
  }
  async register(email: string, password: string, firstName?: string, lastName?: string) {
    return this.request<User>("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, first_name: firstName, last_name: lastName }),
    });
  }
  async completeOnboarding(productRole: ProductRole, workspaceName?: string) {
    return this.request<UserProfile>("/api/v1/auth/onboarding", { method: "POST", body: JSON.stringify({ product_role: productRole, workspace_name: workspaceName }) });
  }
  async acceptInvitation(token: string) {
    return this.request<Organization>("/api/v1/organizations/invitations/accept", { method: "POST", body: JSON.stringify({ token }) });
  }
  async logout() {
    return this.request("/api/v1/auth/logout", { method: "POST" });
  }
  async getMe() {
    return this.request<UserProfile>("/api/v1/auth/me");
  }
  async refreshToken(refreshToken: string) {
    return this.request<AuthResponse>("/api/v1/auth/refresh", { method: "POST", body: JSON.stringify({ refresh_token: refreshToken }) });
  }
  async requestPasswordReset(email: string) {
    return this.request<{ message: string }>("/api/v1/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }) }, false);
  }
  async resetPassword(token: string, newPassword: string) {
    return this.request<{ message: string }>("/api/v1/auth/reset-password", { method: "POST", body: JSON.stringify({ token, new_password: newPassword }) }, false);
  }
  async confirmEmail(token: string) {
    return this.request<{ message: string }>("/api/v1/auth/verification/confirm", { method: "POST", body: JSON.stringify({ token }) }, false);
  }
  async requestVerification() {
    return this.request<{ message: string }>("/api/v1/auth/verification/request", { method: "POST" });
  }
  async enrollMfa(currentPassword: string) {
    return this.request<{ secret: string; provisioning_uri: string; expires_at: string }>("/api/v1/auth/mfa/enroll", { method: "POST", body: JSON.stringify({ current_password: currentPassword }) });
  }
  async confirmMfa(code: string) {
    return this.request<{ recovery_codes: string[]; message: string }>("/api/v1/auth/mfa/confirm", { method: "POST", body: JSON.stringify({ code }) });
  }
  async manageMfa(action: "disable" | "recovery", currentPassword: string, mfaCode: string) {
    return this.request<{ recovery_codes?: string[]; message?: string }>(`/api/v1/auth/mfa/${action}`, { method: "POST", body: JSON.stringify({ current_password: currentPassword, mfa_code: mfaCode }) });
  }
  async changePassword(currentPassword: string, newPassword: string, mfaCode?: string) {
    return this.request<{ message: string }>("/api/v1/auth/change-password", { method: "POST", body: JSON.stringify({ current_password: currentPassword, new_password: newPassword, mfa_code: mfaCode }) });
  }
  async getSessions() {
    return this.request<Array<{ id: string; current: boolean; created_at: string; expires_at: string; ip_address: string | null; user_agent: string | null }>>("/api/v1/auth/sessions");
  }
  async revokeSession(id: string) {
    return this.request<void>(`/api/v1/auth/sessions/${encodeURIComponent(id)}`, { method: "DELETE" });
  }
  async requestErasure(data: { scope: ErasureScope; target_id: string; current_password: string; mfa_code?: string; confirmation: "ERASE" }) {
    return this.request<{ id: string; status: string; receipt: string | null; message: string }>("/api/v1/privacy/erasures", { method: "POST", body: JSON.stringify(data) });
  }
  async getErasureStatus(id: string, receipt: string) {
    return this.request<ErasureStatus>(`/api/v1/privacy/erasures/${encodeURIComponent(id)}`, { headers: { "X-Erasure-Receipt": receipt } }, false);
  }
  async getApiKeys(offset = 0) {
    return this.request<ApiKeyMetadata[]>(`/api/v1/api-keys?offset=${offset}&limit=50`);
  }
  async createApiKey(data: { name: string; scopes: ApiKeyScope[]; expires_at: string | null }) {
    return this.request<CreatedApiKey>("/api/v1/api-keys", { method: "POST", body: JSON.stringify(data) });
  }
  async rotateApiKey(id: string) {
    return this.request<CreatedApiKey>(`/api/v1/api-keys/${encodeURIComponent(id)}/rotate`, { method: "POST" });
  }
  async revokeApiKey(id: string) {
    return this.request<void>(`/api/v1/api-keys/${encodeURIComponent(id)}`, { method: "DELETE" });
  }
  async getOrganizations() {
    return this.request<Organization[]>("/api/v1/organizations");
  }
  async agent<T>(path: string, options: RequestInit = {}): Promise<T> {
    return this.request<T>(`/api/v1/ai${path}`, options);
  }
  async getConversations() {
    return this.agent<{ items: Array<{ id: string; title: string }> }>("/conversations");
  }
  async getModels() {
    return this.request<{ status: string; models: Array<{ id: string; family: string; tasks: string[] }> }>("/api/v1/models");
  }
  async createOrganization(name: string, description?: string) {
    return this.request<Organization>("/api/v1/organizations", { method: "POST", body: JSON.stringify({ name, description }) });
  }
  async selectOrganization(orgId: string) {
    return this.request<Organization>(`/api/v1/organizations/${orgId}/select`, { method: "POST" });
  }
  async getDocuments(page: number = 1) {
    return this.request<DocumentList>(`/api/v1/documents?page=${page}`);
  }
  async getDocument(docId: string) {
    return this.request<DocumentRecord>(`/api/v1/documents/${docId}`);
  }
  async renameDocument(docId: string, title: string, expectedTitle: string | null) {
    return this.request<DocumentRecord>(`/api/v1/documents/${docId}`, { method: "PATCH", body: JSON.stringify({ title, expected_title: expectedTitle }) });
  }
  async getDocumentDownload(docId: string, documentVersionId?: string) {
    const query = documentVersionId ? `?document_version_id=${encodeURIComponent(documentVersionId)}` : "";
    return this.request<{ download_url: string; expires_at: string }>(`/api/v1/documents/${docId}/download${query}`);
  }
  async getDocumentContent(docId: string, documentVersionId?: string) {
    const query = documentVersionId ? `?document_version_id=${encodeURIComponent(documentVersionId)}` : "";
    return this.request<DocumentContent>(`/api/v1/documents/${docId}/content${query}`);
  }
  async saveEditorRevision(docId: string, payload: { operation_id: string; base_version_id: string; text: string; edit_ids: string[] }) {
    return this.request<{ id: string; version_number: number }>(`/api/v1/documents/${docId}/revisions`, { method: "POST", body: JSON.stringify(payload) });
  }
  async restoreDocumentVersion(docId: string, versionId: string, payload: { operation_id: string; base_version_id: string }) {
    return this.request<{ id: string; version_number: number }>(`/api/v1/documents/${docId}/versions/${versionId}/restore`, { method: "POST", body: JSON.stringify(payload) });
  }
  async getSimilarityWorkflow(docId: string, query: string) {
    return this.request<SimilarityWorkflow>(`/api/v1/similarity/documents/${docId}/analysis?${query}`);
  }
  async runSimilarity(docId: string, versionId: string) {
    return this.request<SimilarityWorkflow>(`/api/v1/similarity/documents/${docId}/analysis?document_version_id=${encodeURIComponent(versionId)}`, { method: "POST" });
  }
  async getSimilarityEvidence(docId: string, matchId: string, query: string) {
    return this.request<SimilarityEvidence>(`/api/v1/similarity/documents/${docId}/matches/${matchId}?${query}`);
  }
  async getSimilarityMatches(docId: string, documentVersionId?: string) {
    const query = documentVersionId ? `?document_version_id=${encodeURIComponent(documentVersionId)}` : "";
    return this.request<SimilarityMatchList>(`/api/v1/similarity/documents/${docId}/matches${query}`);
  }
  async getCitationAnalysis(docId: string, documentVersionId?: string) {
    const query = documentVersionId ? `?document_version_id=${encodeURIComponent(documentVersionId)}` : "";
    return this.request<CitationAnalysis>(`/api/v1/citations/documents/${docId}/analysis${query}`);
  }
  async getAuthorshipAnalysis(docId: string, documentVersionId?: string) {
    const query = documentVersionId ? `?document_version_id=${encodeURIComponent(documentVersionId)}` : "";
    return this.request<AuthorshipSignal>(`/api/v1/authorship/documents/${docId}/analysis${query}`);
  }
  async getProvenanceTimeline(docId: string) {
    return this.request<ProvenanceTimeline>(`/api/v1/provenance/documents/${docId}/timeline`);
  }
  async getUsage() { return this.request<UsageSummary>("/api/v1/usage"); }
  async refineDraft(payload: { operation_id?: string; document_id: string; document_version_id: string; text: string; preserve_voice: boolean; edit_types?: string[] }) {
    return this.request<AegisRefineResult>('/api/v1/aegiswrite/refine', { method: 'POST', body: JSON.stringify(payload) });
  }
  async suggestEdits(payload: { operation_id?: string; document_id: string; document_version_id: string; text: string; span_start?: number; span_end?: number; preserve_voice: boolean; edit_types?: string[] }) {
    return this.request<AegisChange[]>('/api/v1/aegiswrite/suggest', { method: 'POST', body: JSON.stringify(payload) });
  }
  async applyEdit(editId: string, apply: boolean) {
    return this.request<AegisChange>('/api/v1/aegiswrite/apply', { method: 'POST', body: JSON.stringify({ edit_id: editId, apply }) });
  }
  async getWriteHistory(docId: string, versionId?: string) {
    const query = versionId ? `?document_version_id=${encodeURIComponent(versionId)}` : '';
    return this.request<{ document_id: string; document_version_id: string | null; items: AegisChange[] }>(`/api/v1/aegiswrite/history/${docId}${query}`);
  }
  async exportProvenance(docId: string) {
    const response = await fetch(`${this.baseUrl}/api/v1/provenance/documents/${docId}/export`, { method: "POST", credentials: "include" });
    if (!response.ok) throw new ApiError(response.status, undefined, "Unable to export provenance history");
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${docId}-provenance.json`;
    anchor.click();
    URL.revokeObjectURL(url);
    return response.headers.get("X-Provenance-Export-Hash");
  }
  async requestUpload(filename: string, contentType: string, fileSize: number) {
    return this.request<UploadRequest>("/api/v1/documents/upload-request", {
      method: "POST", body: JSON.stringify({ filename, content_type: contentType, file_size: fileSize }),
    });
  }
  async confirmUpload(uploadId: string, storageKey: string, sha256Fingerprint: string, originalFilename?: string) {
    return this.request<DocumentRecord>("/api/v1/documents/upload-confirm", {
      method: "POST",
      body: JSON.stringify({ upload_id: uploadId, storage_key: storageKey, sha256_fingerprint: sha256Fingerprint, original_filename: originalFilename }),
    });
  }
  async deleteDocument(docId: string) {
    return this.request(`/api/v1/documents/${docId}`, { method: "DELETE" });
  }
  async getJobs() {
    return this.request("/api/v1/jobs");
  }
  async getJob(jobId: string) {
    return this.request(`/api/v1/jobs/${jobId}`);
  }
  async cancelJob(jobId: string) {
    return this.request(`/api/v1/jobs/${jobId}/cancel`, { method: "POST" });
  }
  async getDetectionResult(docId: string, documentVersionId?: string) {
    const query = documentVersionId ? `?document_version_id=${encodeURIComponent(documentVersionId)}` : "";
    return this.request<DetectionResult>(`/api/v1/detection/documents/${docId}${query}`);
  }
  async getDetectionExplain(docId: string) {
    return this.request<DetectionExplainability>(`/api/v1/detection/documents/${docId}/explain`);
  }
  async getEvidenceGraph(docId: string, documentVersionId?: string) {
    const query = documentVersionId ? `?document_version_id=${encodeURIComponent(documentVersionId)}` : "";
    return this.request<EvidenceGraph>(`/api/v1/evidence/documents/${docId}/graph${query}`);
  }
  async getEvidenceFirstReport(docId: string, documentVersionId?: string) {
    const query = documentVersionId ? `?document_version_id=${encodeURIComponent(documentVersionId)}` : "";
    return this.request<EvidenceFirstReport>(`/api/v1/reports/documents/${docId}${query}`);
  }
}

export const api = new ApiClient();

export interface SimilarityEvidence {
  id: string; evidence_id: string | null; evidence_node_id: string | null;
  document_version_id: string; source_document_id: string; source_document_version_id: string;
  source_title: string; source_category: string; corpus_state: string;
  source_content_hash: string; source_text_hash: string; target_content_hash: string; target_text_hash: string;
  retrieved_at: string; source_uploaded_at: string; match_type: string;
  document_span_start: number; document_span_end: number; source_span_start: number; source_span_end: number;
  matched_text: string; source_text: string; context_before: string; context_after: string;
  source_context_before: string; source_context_after: string;
  quotation_status: string; citation_status: string; group: string;
  flags: Array<{ code: string; explanation: string }>;
  matched_words: number; included_words: number; excluded: boolean; exclusion_reasons: string[];
}
export interface SimilarityWorkflow {
  document_id: string; document_version_id: string; version_number: number;
  analysis_id: string | null; analysis_state: string; analyzed_at: string | null;
  pipeline_version: string; text_hash: string; content_hash: string; text_basis: string;
  corpus: Array<{ category: string; label: string; state: string; indexed_versions?: number; searched: boolean; note?: string }>;
  summary: { total_words: number; eligible_words: number; excluded_words: number; matched_words: number; percentage: number | null; included_match_count: number; recorded_match_count: number };
  groups: Array<{ key: string; label: string; matches: number; matched_words: number; percentage: number | null }>;
  flags: Array<{ code: string; match_count: number }>;
  exclusions: { exclude_quotes: boolean; exclude_cited: boolean; exclude_bibliography: boolean; min_match_words: number; excluded_source_version_ids: string[]; rules_version: string };
  exclusions_hash: string;
  matches: { items: SimilarityEvidence[]; total: number; page: number; page_size: number };
  sources: { items: Array<{ source_document_id: string; source_document_version_id: string; title: string; category: string; corpus_state: string; content_hash: string; retrieved_at: string; match_count: number; matched_words: number; percentage: number | null; excluded: boolean; rank: number }>; total: number; page: number; page_size: number };
  interpretation: string; calculation: string; limitations: string[];
}
