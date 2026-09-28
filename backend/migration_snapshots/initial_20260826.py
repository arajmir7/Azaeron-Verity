"""Frozen table definitions for revision 20260826_0001.

This schema must never import current application models. Later revisions own
all subsequent schema changes. Reconstructed from the deployed schema and the
explicit reverse operations of revisions 0002 through 0020.
"""

import sqlalchemy as sa


metadata = sa.MetaData()

sa.Table(
    "aegis_edits",
    metadata,
    sa.Column("document_id", sa.String(length=36), nullable=False),
    sa.Column("user_id", sa.String(length=36), nullable=False),
    sa.Column(
        "edit_type",
        sa.Enum(
            "GRAMMAR",
            "CLARITY",
            "CONCISION",
            "TONE",
            "STRUCTURE",
            "CITATION",
            "VOCABULARY",
            "COHERENCE",
            name="edittype",
        ),
        nullable=False,
    ),
    sa.Column("original_text", sa.Text(), nullable=False),
    sa.Column("suggested_text", sa.Text(), nullable=False),
    sa.Column("explanation", sa.Text(), nullable=False),
    sa.Column("span_start", sa.Integer(), nullable=False),
    sa.Column("span_end", sa.Integer(), nullable=False),
    sa.Column("applied", sa.Boolean(), nullable=False),
    sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("ai_generated", sa.Boolean(), nullable=False),
    sa.Column("metadata_json", sa.JSON(), nullable=True),
    sa.Column("id", sa.String(length=36), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.ForeignKeyConstraint(
        ["document_id"],
        ["documents.id"],
        name="aegis_edits_document_id_fkey",
        ondelete="CASCADE",
    ),
    sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="aegis_edits_user_id_fkey"),
    sa.PrimaryKeyConstraint("id", name="aegis_edits_pkey"),
)
sa.Index(
    "ix_aegis_edits_document_id",
    metadata.tables["aegis_edits"].c["document_id"],
    unique=False,
)
sa.Index(
    "ix_aegis_edits_user_id", metadata.tables["aegis_edits"].c["user_id"], unique=False
)

sa.Table(
    "api_keys",
    metadata,
    sa.Column("user_id", sa.String(length=36), nullable=False),
    sa.Column("organization_id", sa.String(length=36), nullable=False),
    sa.Column("name", sa.String(length=100), nullable=False),
    sa.Column("key_prefix", sa.String(length=8), nullable=False),
    sa.Column("hashed_key", sa.String(length=255), nullable=False),
    sa.Column("scopes", sa.Text(), nullable=True),
    sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("is_active", sa.Boolean(), nullable=False),
    sa.Column("id", sa.String(length=36), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.ForeignKeyConstraint(
        ["organization_id"],
        ["organizations.id"],
        name="api_keys_organization_id_fkey",
        ondelete="CASCADE",
    ),
    sa.ForeignKeyConstraint(
        ["user_id"], ["users.id"], name="api_keys_user_id_fkey", ondelete="CASCADE"
    ),
    sa.PrimaryKeyConstraint("id", name="api_keys_pkey"),
)
sa.Index(
    "ix_api_keys_organization_id",
    metadata.tables["api_keys"].c["organization_id"],
    unique=False,
)
sa.Index("ix_api_keys_user_id", metadata.tables["api_keys"].c["user_id"], unique=False)

sa.Table(
    "assignments",
    metadata,
    sa.Column("organization_id", sa.String(length=36), nullable=False),
    sa.Column("created_by_id", sa.String(length=36), nullable=False),
    sa.Column("title", sa.String(length=500), nullable=False),
    sa.Column("description", sa.Text(), nullable=True),
    sa.Column("instructions", sa.Text(), nullable=True),
    sa.Column(
        "status",
        sa.Enum("DRAFT", "PUBLISHED", "CLOSED", "ARCHIVED", name="assignmentstatus"),
        nullable=False,
    ),
    sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
    sa.Column("max_file_size_mb", sa.Integer(), nullable=False),
    sa.Column("allowed_extensions", sa.JSON(), nullable=False),
    sa.Column("rubric", sa.JSON(), nullable=True),
    sa.Column("settings", sa.JSON(), nullable=True),
    sa.Column("id", sa.String(length=36), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.ForeignKeyConstraint(
        ["created_by_id"], ["users.id"], name="assignments_created_by_id_fkey"
    ),
    sa.ForeignKeyConstraint(
        ["organization_id"],
        ["organizations.id"],
        name="assignments_organization_id_fkey",
        ondelete="CASCADE",
    ),
    sa.PrimaryKeyConstraint("id", name="assignments_pkey"),
)
sa.Index(
    "ix_assignments_organization_id",
    metadata.tables["assignments"].c["organization_id"],
    unique=False,
)

sa.Table(
    "audit_logs",
    metadata,
    sa.Column("organization_id", sa.String(length=36), nullable=True),
    sa.Column("user_id", sa.String(length=36), nullable=True),
    sa.Column(
        "action",
        sa.Enum(
            "USER_LOGIN",
            "USER_LOGOUT",
            "USER_REGISTERED",
            "USER_UPDATED",
            "ORG_CREATED",
            "ORG_UPDATED",
            "ORG_MEMBER_INVITED",
            "ORG_MEMBER_JOINED",
            "DOCUMENT_UPLOADED",
            "DOCUMENT_DELETED",
            "DOCUMENT_PROCESSED",
            "JOB_CREATED",
            "JOB_COMPLETED",
            "JOB_FAILED",
            "SETTINGS_CHANGED",
            "API_KEY_CREATED",
            "API_KEY_REVOKED",
            "EXPORT_REQUESTED",
            "DATA_DELETED",
            "ASSIGNMENT_CREATED",
            "SUBMISSION_CREATED",
            "GRADE_ASSIGNED",
            "REPORT_VIEWED",
            "DETECTION_RUN",
            name="auditaction",
        ),
        nullable=False,
    ),
    sa.Column("resource_type", sa.String(length=50), nullable=False),
    sa.Column("resource_id", sa.String(length=36), nullable=True),
    sa.Column("details", sa.JSON(), nullable=True),
    sa.Column("ip_address", sa.String(length=45), nullable=True),
    sa.Column("user_agent", sa.Text(), nullable=True),
    sa.Column("request_id", sa.String(length=36), nullable=True),
    sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
    sa.Column("id", sa.String(length=36), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.ForeignKeyConstraint(
        ["organization_id"],
        ["organizations.id"],
        name="audit_logs_organization_id_fkey",
        ondelete="SET NULL",
    ),
    sa.ForeignKeyConstraint(
        ["user_id"], ["users.id"], name="audit_logs_user_id_fkey", ondelete="SET NULL"
    ),
    sa.PrimaryKeyConstraint("id", name="audit_logs_pkey"),
)
sa.Index(
    "ix_audit_logs_action", metadata.tables["audit_logs"].c["action"], unique=False
)
sa.Index(
    "ix_audit_logs_organization_id",
    metadata.tables["audit_logs"].c["organization_id"],
    unique=False,
)
sa.Index(
    "ix_audit_logs_request_id",
    metadata.tables["audit_logs"].c["request_id"],
    unique=False,
)
sa.Index(
    "ix_audit_logs_user_id", metadata.tables["audit_logs"].c["user_id"], unique=False
)

sa.Table(
    "authorship_profiles",
    metadata,
    sa.Column("user_id", sa.String(length=36), nullable=False),
    sa.Column("name", sa.String(length=100), nullable=False),
    sa.Column("description", sa.Text(), nullable=True),
    sa.Column("baseline_document_ids", sa.JSON(), nullable=True),
    sa.Column("stylometric_features", sa.JSON(), nullable=True),
    sa.Column("vocabulary_distribution", sa.JSON(), nullable=True),
    sa.Column("punctuation_patterns", sa.JSON(), nullable=True),
    sa.Column("syntax_patterns", sa.JSON(), nullable=True),
    sa.Column("id", sa.String(length=36), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.ForeignKeyConstraint(
        ["user_id"],
        ["users.id"],
        name="authorship_profiles_user_id_fkey",
        ondelete="CASCADE",
    ),
    sa.PrimaryKeyConstraint("id", name="authorship_profiles_pkey"),
)
sa.Index(
    "ix_authorship_profiles_user_id",
    metadata.tables["authorship_profiles"].c["user_id"],
    unique=False,
)

sa.Table(
    "authorship_signals",
    metadata,
    sa.Column("document_id", sa.String(length=36), nullable=False),
    sa.Column("profile_id", sa.String(length=36), nullable=True),
    sa.Column("consistency_score", sa.Float(), nullable=False),
    sa.Column("confidence", sa.Float(), nullable=False),
    sa.Column("stylistic_drift_score", sa.Float(), nullable=True),
    sa.Column("unusual_segments", sa.JSON(), nullable=True),
    sa.Column("explanation", sa.Text(), nullable=True),
    sa.Column("limitations", sa.Text(), nullable=True),
    sa.Column("id", sa.String(length=36), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.ForeignKeyConstraint(
        ["document_id"],
        ["documents.id"],
        name="authorship_signals_document_id_fkey",
        ondelete="CASCADE",
    ),
    sa.ForeignKeyConstraint(
        ["profile_id"],
        ["authorship_profiles.id"],
        name="authorship_signals_profile_id_fkey",
        ondelete="CASCADE",
    ),
    sa.PrimaryKeyConstraint("id", name="authorship_signals_pkey"),
)
sa.Index(
    "ix_authorship_signals_document_id",
    metadata.tables["authorship_signals"].c["document_id"],
    unique=False,
)
sa.Index(
    "ix_authorship_signals_profile_id",
    metadata.tables["authorship_signals"].c["profile_id"],
    unique=False,
)

sa.Table(
    "billing_events",
    metadata,
    sa.Column("organization_id", sa.String(length=36), nullable=False),
    sa.Column("event_type", sa.String(length=50), nullable=False),
    sa.Column("quantity", sa.Integer(), nullable=False),
    sa.Column("unit_cost", sa.Float(), nullable=True),
    sa.Column("total_cost", sa.Float(), nullable=True),
    sa.Column("description", sa.Text(), nullable=True),
    sa.Column("metadata_json", sa.JSON(), nullable=True),
    sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
    sa.Column("id", sa.String(length=36), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.ForeignKeyConstraint(
        ["organization_id"],
        ["organizations.id"],
        name="billing_events_organization_id_fkey",
        ondelete="CASCADE",
    ),
    sa.PrimaryKeyConstraint("id", name="billing_events_pkey"),
)
sa.Index(
    "ix_billing_events_organization_id",
    metadata.tables["billing_events"].c["organization_id"],
    unique=False,
)

sa.Table(
    "citations",
    metadata,
    sa.Column("document_id", sa.String(length=36), nullable=False),
    sa.Column("claim_id", sa.String(length=36), nullable=True),
    sa.Column("raw_text", sa.Text(), nullable=False),
    sa.Column("citation_type", sa.String(length=50), nullable=True),
    sa.Column("authors", sa.JSON(), nullable=True),
    sa.Column("title", sa.Text(), nullable=True),
    sa.Column("year", sa.Integer(), nullable=True),
    sa.Column("doi", sa.String(length=255), nullable=True),
    sa.Column("url", sa.Text(), nullable=True),
    sa.Column("journal", sa.Text(), nullable=True),
    sa.Column("publisher", sa.Text(), nullable=True),
    sa.Column(
        "status",
        sa.Enum(
            "VALID",
            "BROKEN",
            "SUSPICIOUS",
            "UNVERIFIED",
            "FABRICATED",
            name="citationstatus",
        ),
        nullable=False,
    ),
    sa.Column("verification_data", sa.JSON(), nullable=True),
    sa.Column("span_start", sa.Integer(), nullable=False),
    sa.Column("span_end", sa.Integer(), nullable=False),
    sa.Column("id", sa.String(length=36), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.ForeignKeyConstraint(
        ["claim_id"], ["claims.id"], name="citations_claim_id_fkey", ondelete="SET NULL"
    ),
    sa.ForeignKeyConstraint(
        ["document_id"],
        ["documents.id"],
        name="citations_document_id_fkey",
        ondelete="CASCADE",
    ),
    sa.PrimaryKeyConstraint("id", name="citations_pkey"),
)
sa.Index(
    "ix_citations_document_id",
    metadata.tables["citations"].c["document_id"],
    unique=False,
)

sa.Table(
    "claims",
    metadata,
    sa.Column("document_id", sa.String(length=36), nullable=False),
    sa.Column("text", sa.Text(), nullable=False),
    sa.Column("claim_type", sa.String(length=50), nullable=True),
    sa.Column("span_start", sa.Integer(), nullable=False),
    sa.Column("span_end", sa.Integer(), nullable=False),
    sa.Column("has_citation", sa.Boolean(), nullable=False),
    sa.Column("citation_supports_claim", sa.Boolean(), nullable=True),
    sa.Column("confidence", sa.Float(), nullable=False),
    sa.Column("id", sa.String(length=36), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.ForeignKeyConstraint(
        ["document_id"],
        ["documents.id"],
        name="claims_document_id_fkey",
        ondelete="CASCADE",
    ),
    sa.PrimaryKeyConstraint("id", name="claims_pkey"),
)
sa.Index(
    "ix_claims_document_id", metadata.tables["claims"].c["document_id"], unique=False
)

sa.Table(
    "compliance_reports",
    metadata,
    sa.Column("organization_id", sa.String(length=36), nullable=False),
    sa.Column("report_type", sa.String(length=50), nullable=False),
    sa.Column("generated_by_id", sa.String(length=36), nullable=False),
    sa.Column("report_data", sa.JSON(), nullable=False),
    sa.Column("download_url", sa.Text(), nullable=True),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("id", sa.String(length=36), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.ForeignKeyConstraint(
        ["generated_by_id"],
        ["users.id"],
        name="compliance_reports_generated_by_id_fkey",
    ),
    sa.ForeignKeyConstraint(
        ["organization_id"],
        ["organizations.id"],
        name="compliance_reports_organization_id_fkey",
        ondelete="CASCADE",
    ),
    sa.PrimaryKeyConstraint("id", name="compliance_reports_pkey"),
)
sa.Index(
    "ix_compliance_reports_organization_id",
    metadata.tables["compliance_reports"].c["organization_id"],
    unique=False,
)

sa.Table(
    "detection_results",
    metadata,
    sa.Column("document_id", sa.String(length=36), nullable=False),
    sa.Column("job_id", sa.String(length=36), nullable=False),
    sa.Column("model_version", sa.String(length=50), nullable=False),
    sa.Column("pipeline_version", sa.String(length=50), nullable=True),
    sa.Column(
        "overall_verdict",
        sa.Enum(
            "HUMAN",
            "AI",
            "MIXED",
            "AI_ASSISTED",
            "UNCERTAIN",
            "INSUFFICIENT_EVIDENCE",
            name="detectionverdict",
        ),
        nullable=False,
    ),
    sa.Column("confidence", sa.Float(), nullable=False),
    sa.Column("calibration_score", sa.Float(), nullable=True),
    sa.Column("human_probability", sa.Float(), nullable=False),
    sa.Column("ai_probability", sa.Float(), nullable=False),
    sa.Column("mixed_probability", sa.Float(), nullable=False),
    sa.Column("uncertain_probability", sa.Float(), nullable=False),
    sa.Column("explanation", sa.Text(), nullable=True),
    sa.Column("limitations", sa.Text(), nullable=True),
    sa.Column("feature_data", sa.JSON(), nullable=True),
    sa.Column("id", sa.String(length=36), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.ForeignKeyConstraint(
        ["document_id"],
        ["documents.id"],
        name="detection_results_document_id_fkey",
        ondelete="CASCADE",
    ),
    sa.ForeignKeyConstraint(
        ["job_id"],
        ["jobs.id"],
        name="detection_results_job_id_fkey",
        ondelete="CASCADE",
    ),
    sa.PrimaryKeyConstraint("id", name="detection_results_pkey"),
)
sa.Index(
    "ix_detection_results_document_id",
    metadata.tables["detection_results"].c["document_id"],
    unique=False,
)
sa.Index(
    "ix_detection_results_job_id",
    metadata.tables["detection_results"].c["job_id"],
    unique=False,
)

sa.Table(
    "detection_segments",
    metadata,
    sa.Column("detection_result_id", sa.String(length=36), nullable=False),
    sa.Column("segment_type", sa.String(length=20), nullable=False),
    sa.Column("segment_index", sa.Integer(), nullable=False),
    sa.Column("text", sa.Text(), nullable=False),
    sa.Column("span_start", sa.Integer(), nullable=False),
    sa.Column("span_end", sa.Integer(), nullable=False),
    sa.Column(
        "verdict",
        sa.Enum(
            "HUMAN",
            "AI",
            "MIXED",
            "AI_ASSISTED",
            "UNCERTAIN",
            "INSUFFICIENT_EVIDENCE",
            name="detectionverdict",
        ),
        nullable=False,
    ),
    sa.Column("confidence", sa.Float(), nullable=False),
    sa.Column("perplexity", sa.Float(), nullable=True),
    sa.Column("burstiness", sa.Float(), nullable=True),
    sa.Column("feature_scores", sa.JSON(), nullable=True),
    sa.Column("explanation", sa.Text(), nullable=True),
    sa.Column("id", sa.String(length=36), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.ForeignKeyConstraint(
        ["detection_result_id"],
        ["detection_results.id"],
        name="detection_segments_detection_result_id_fkey",
        ondelete="CASCADE",
    ),
    sa.PrimaryKeyConstraint("id", name="detection_segments_pkey"),
)
sa.Index(
    "ix_detection_segments_detection_result_id",
    metadata.tables["detection_segments"].c["detection_result_id"],
    unique=False,
)

sa.Table(
    "document_chunks",
    metadata,
    sa.Column("document_id", sa.String(length=36), nullable=False),
    sa.Column("chunk_index", sa.Integer(), nullable=False),
    sa.Column("text", sa.Text(), nullable=False),
    sa.Column("start_char", sa.Integer(), nullable=False),
    sa.Column("end_char", sa.Integer(), nullable=False),
    sa.Column("embedding", sa.JSON(), nullable=True),
    sa.Column("token_count", sa.Integer(), nullable=False),
    sa.Column("id", sa.String(length=36), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.ForeignKeyConstraint(
        ["document_id"],
        ["documents.id"],
        name="document_chunks_document_id_fkey",
        ondelete="CASCADE",
    ),
    sa.PrimaryKeyConstraint("id", name="document_chunks_pkey"),
)
sa.Index(
    "ix_document_chunks_document_id",
    metadata.tables["document_chunks"].c["document_id"],
    unique=False,
)

sa.Table(
    "document_versions",
    metadata,
    sa.Column("document_id", sa.String(length=36), nullable=False),
    sa.Column("version_number", sa.Integer(), nullable=False),
    sa.Column("storage_path", sa.String(length=500), nullable=False),
    sa.Column("sha256_fingerprint", sa.String(length=64), nullable=False),
    sa.Column("created_by_id", sa.String(length=36), nullable=False),
    sa.Column("change_summary", sa.Text(), nullable=True),
    sa.Column("edit_type", sa.String(length=50), nullable=True),
    sa.Column("id", sa.String(length=36), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.ForeignKeyConstraint(
        ["created_by_id"], ["users.id"], name="document_versions_created_by_id_fkey"
    ),
    sa.ForeignKeyConstraint(
        ["document_id"],
        ["documents.id"],
        name="document_versions_document_id_fkey",
        ondelete="CASCADE",
    ),
    sa.PrimaryKeyConstraint("id", name="document_versions_pkey"),
)
sa.Index(
    "ix_document_versions_document_id",
    metadata.tables["document_versions"].c["document_id"],
    unique=False,
)

sa.Table(
    "documents",
    metadata,
    sa.Column("organization_id", sa.String(length=36), nullable=False),
    sa.Column("owner_id", sa.String(length=36), nullable=False),
    sa.Column("assignment_id", sa.String(length=36), nullable=True),
    sa.Column("submission_id", sa.String(length=36), nullable=True),
    sa.Column("title", sa.String(length=500), nullable=True),
    sa.Column("filename", sa.String(length=255), nullable=False),
    sa.Column("original_filename", sa.String(length=255), nullable=False),
    sa.Column("file_size", sa.Integer(), nullable=False),
    sa.Column("mime_type", sa.String(length=100), nullable=False),
    sa.Column("extension", sa.String(length=20), nullable=False),
    sa.Column("sha256_fingerprint", sa.String(length=64), nullable=False),
    sa.Column("storage_path", sa.String(length=500), nullable=False),
    sa.Column(
        "status",
        sa.Enum(
            "PENDING",
            "VALIDATING",
            "QUEUED",
            "PROCESSING",
            "COMPLETED",
            "FAILED",
            "ARCHIVED",
            name="documentstatus",
        ),
        nullable=False,
    ),
    sa.Column("metadata_json", sa.Text(), nullable=True),
    sa.Column("error_message", sa.Text(), nullable=True),
    sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("word_count", sa.Integer(), nullable=True),
    sa.Column("language", sa.String(length=10), nullable=True),
    sa.Column("id", sa.String(length=36), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.ForeignKeyConstraint(
        ["assignment_id"],
        ["assignments.id"],
        name="documents_assignment_id_fkey",
        ondelete="SET NULL",
    ),
    sa.ForeignKeyConstraint(
        ["organization_id"],
        ["organizations.id"],
        name="documents_organization_id_fkey",
        ondelete="CASCADE",
    ),
    sa.ForeignKeyConstraint(
        ["owner_id"], ["users.id"], name="documents_owner_id_fkey", ondelete="CASCADE"
    ),
    sa.ForeignKeyConstraint(
        ["submission_id"],
        ["submissions.id"],
        name="documents_submission_id_fkey",
        ondelete="SET NULL",
    ),
    sa.PrimaryKeyConstraint("id", name="documents_pkey"),
)
sa.Index(
    "ix_documents_assignment_id",
    metadata.tables["documents"].c["assignment_id"],
    unique=False,
)
sa.Index(
    "ix_documents_organization_id",
    metadata.tables["documents"].c["organization_id"],
    unique=False,
)
sa.Index(
    "ix_documents_owner_id", metadata.tables["documents"].c["owner_id"], unique=False
)
sa.Index(
    "ix_documents_sha256_fingerprint",
    metadata.tables["documents"].c["sha256_fingerprint"],
    unique=False,
)
sa.Index(
    "ix_documents_submission_id",
    metadata.tables["documents"].c["submission_id"],
    unique=False,
)

sa.Table(
    "evidence_edges",
    metadata,
    sa.Column("source_node_id", sa.String(length=36), nullable=False),
    sa.Column("target_node_id", sa.String(length=36), nullable=False),
    sa.Column("edge_type", sa.String(length=50), nullable=False),
    sa.Column("weight", sa.Float(), nullable=False),
    sa.Column("description", sa.Text(), nullable=True),
    sa.Column("metadata_json", sa.JSON(), nullable=True),
    sa.Column("id", sa.String(length=36), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.PrimaryKeyConstraint("id", name="evidence_edges_pkey"),
)
sa.Index(
    "ix_evidence_edges_source_node_id",
    metadata.tables["evidence_edges"].c["source_node_id"],
    unique=False,
)
sa.Index(
    "ix_evidence_edges_target_node_id",
    metadata.tables["evidence_edges"].c["target_node_id"],
    unique=False,
)

sa.Table(
    "evidence_nodes",
    metadata,
    sa.Column("document_id", sa.String(length=36), nullable=False),
    sa.Column(
        "node_type",
        sa.Enum(
            "DOCUMENT",
            "CLAIM",
            "CITATION",
            "SOURCE",
            "SIMILARITY",
            "AUTHORSHIP",
            "PROVENANCE",
            "DETECTION",
            "REVISION",
            name="evidencenodetype",
        ),
        nullable=False,
    ),
    sa.Column("node_id", sa.String(length=36), nullable=False),
    sa.Column("title", sa.Text(), nullable=False),
    sa.Column("description", sa.Text(), nullable=True),
    sa.Column("span_start", sa.Integer(), nullable=True),
    sa.Column("span_end", sa.Integer(), nullable=True),
    sa.Column("confidence", sa.Float(), nullable=False),
    sa.Column("severity", sa.String(length=20), nullable=True),
    sa.Column("metadata_json", sa.JSON(), nullable=True),
    sa.Column("id", sa.String(length=36), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.ForeignKeyConstraint(
        ["document_id"],
        ["documents.id"],
        name="evidence_nodes_document_id_fkey",
        ondelete="CASCADE",
    ),
    sa.PrimaryKeyConstraint("id", name="evidence_nodes_pkey"),
)
sa.Index(
    "ix_evidence_nodes_document_id",
    metadata.tables["evidence_nodes"].c["document_id"],
    unique=False,
)

sa.Table(
    "integrity_reports",
    metadata,
    sa.Column("document_id", sa.String(length=36), nullable=False),
    sa.Column(
        "status",
        sa.Enum("PENDING", "GENERATING", "COMPLETED", "FAILED", name="reportstatus"),
        nullable=False,
    ),
    sa.Column("originality_score", sa.Float(), nullable=True),
    sa.Column("originality_confidence", sa.String(length=20), nullable=True),
    sa.Column("ai_signal_score", sa.Float(), nullable=True),
    sa.Column("ai_signal_confidence", sa.String(length=20), nullable=True),
    sa.Column("ai_signal_verdict", sa.String(length=50), nullable=True),
    sa.Column("authorship_consistency_score", sa.Float(), nullable=True),
    sa.Column("authorship_confidence", sa.String(length=20), nullable=True),
    sa.Column("citation_integrity_score", sa.Float(), nullable=True),
    sa.Column("source_quality_score", sa.Float(), nullable=True),
    sa.Column("provenance_strength", sa.String(length=20), nullable=True),
    sa.Column("writing_quality_score", sa.Float(), nullable=True),
    sa.Column("priority_issues", sa.JSON(), nullable=True),
    sa.Column("report_data", sa.JSON(), nullable=True),
    sa.Column("id", sa.String(length=36), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.ForeignKeyConstraint(
        ["document_id"],
        ["documents.id"],
        name="integrity_reports_document_id_fkey",
        ondelete="CASCADE",
    ),
    sa.PrimaryKeyConstraint("id", name="integrity_reports_pkey"),
)
sa.Index(
    "ix_integrity_reports_document_id",
    metadata.tables["integrity_reports"].c["document_id"],
    unique=True,
)

sa.Table(
    "jobs",
    metadata,
    sa.Column("organization_id", sa.String(length=36), nullable=False),
    sa.Column("document_id", sa.String(length=36), nullable=True),
    sa.Column(
        "job_type",
        sa.Enum(
            "DOCUMENT_PROCESSING",
            "SIMILARITY_ANALYSIS",
            "CITATION_ANALYSIS",
            "AI_DETECTION",
            "AUTHORSHIP_ANALYSIS",
            "PROVENANCE_ANALYSIS",
            "REPORT_GENERATION",
            "EXPORT",
            name="jobtype",
        ),
        nullable=False,
    ),
    sa.Column(
        "status",
        sa.Enum(
            "PENDING",
            "RUNNING",
            "COMPLETED",
            "FAILED",
            "CANCELLED",
            "RETRYING",
            name="jobstatus",
        ),
        nullable=False,
    ),
    sa.Column("priority", sa.Integer(), nullable=False),
    sa.Column("progress_percent", sa.Integer(), nullable=False),
    sa.Column("input_data", sa.JSON(), nullable=True),
    sa.Column("result_data", sa.JSON(), nullable=True),
    sa.Column("error_message", sa.Text(), nullable=True),
    sa.Column("retry_count", sa.Integer(), nullable=False),
    sa.Column("max_retries", sa.Integer(), nullable=False),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("celery_task_id", sa.String(length=255), nullable=True),
    sa.Column("id", sa.String(length=36), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.ForeignKeyConstraint(
        ["document_id"],
        ["documents.id"],
        name="jobs_document_id_fkey",
        ondelete="SET NULL",
    ),
    sa.ForeignKeyConstraint(
        ["organization_id"],
        ["organizations.id"],
        name="jobs_organization_id_fkey",
        ondelete="CASCADE",
    ),
    sa.PrimaryKeyConstraint("id", name="jobs_pkey"),
)
sa.Index(
    "ix_jobs_celery_task_id", metadata.tables["jobs"].c["celery_task_id"], unique=False
)
sa.Index("ix_jobs_document_id", metadata.tables["jobs"].c["document_id"], unique=False)
sa.Index(
    "ix_jobs_organization_id",
    metadata.tables["jobs"].c["organization_id"],
    unique=False,
)

sa.Table(
    "memberships",
    metadata,
    sa.Column("user_id", sa.String(length=36), nullable=False),
    sa.Column("organization_id", sa.String(length=36), nullable=False),
    sa.Column(
        "role",
        sa.Enum(
            "OWNER",
            "ADMIN",
            "FACULTY",
            "RESEARCHER",
            "STUDENT",
            "REVIEWER",
            "AUDITOR",
            name="organizationrole",
        ),
        nullable=False,
    ),
    sa.Column("is_active", sa.Boolean(), nullable=False),
    sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("invited_by_id", sa.String(length=36), nullable=True),
    sa.Column("id", sa.String(length=36), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.ForeignKeyConstraint(
        ["invited_by_id"], ["users.id"], name="memberships_invited_by_id_fkey"
    ),
    sa.ForeignKeyConstraint(
        ["organization_id"],
        ["organizations.id"],
        name="memberships_organization_id_fkey",
        ondelete="CASCADE",
    ),
    sa.ForeignKeyConstraint(
        ["user_id"], ["users.id"], name="memberships_user_id_fkey", ondelete="CASCADE"
    ),
    sa.PrimaryKeyConstraint("id", name="memberships_pkey"),
)
sa.Index(
    "ix_memberships_organization_id",
    metadata.tables["memberships"].c["organization_id"],
    unique=False,
)
sa.Index(
    "ix_memberships_user_id", metadata.tables["memberships"].c["user_id"], unique=False
)

sa.Table(
    "organizations",
    metadata,
    sa.Column("name", sa.String(length=255), nullable=False),
    sa.Column("slug", sa.String(length=255), nullable=False),
    sa.Column("description", sa.Text(), nullable=True),
    sa.Column("is_active", sa.Boolean(), nullable=False),
    sa.Column("settings", sa.Text(), nullable=True),
    sa.Column(
        "subscription_tier",
        sa.Enum(
            "FREE",
            "STUDENT",
            "PRO",
            "FACULTY",
            "INSTITUTION",
            "ENTERPRISE",
            name="subscriptiontier",
        ),
        nullable=False,
    ),
    sa.Column("subscription_expires_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("usage_documents_month", sa.Integer(), nullable=False),
    sa.Column("usage_storage_mb", sa.Integer(), nullable=False),
    sa.Column("usage_api_calls", sa.Integer(), nullable=False),
    sa.Column("id", sa.String(length=36), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.PrimaryKeyConstraint("id", name="organizations_pkey"),
)
sa.Index(
    "ix_organizations_slug", metadata.tables["organizations"].c["slug"], unique=True
)

sa.Table(
    "processed_documents",
    metadata,
    sa.Column("document_id", sa.String(length=36), nullable=False),
    sa.Column("raw_text", sa.Text(), nullable=True),
    sa.Column("cleaned_text", sa.Text(), nullable=True),
    sa.Column("paragraphs", sa.JSON(), nullable=True),
    sa.Column("sentences", sa.JSON(), nullable=True),
    sa.Column("sections", sa.JSON(), nullable=True),
    sa.Column("language", sa.String(length=10), nullable=True),
    sa.Column("word_count", sa.Integer(), nullable=False),
    sa.Column("sentence_count", sa.Integer(), nullable=False),
    sa.Column("paragraph_count", sa.Integer(), nullable=False),
    sa.Column("avg_sentence_length", sa.Float(), nullable=True),
    sa.Column("avg_word_length", sa.Float(), nullable=True),
    sa.Column("readability_flesch", sa.Float(), nullable=True),
    sa.Column("readability_flesch_kincaid", sa.Float(), nullable=True),
    sa.Column("lexical_diversity", sa.Float(), nullable=True),
    sa.Column("id", sa.String(length=36), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.ForeignKeyConstraint(
        ["document_id"],
        ["documents.id"],
        name="processed_documents_document_id_fkey",
        ondelete="CASCADE",
    ),
    sa.PrimaryKeyConstraint("id", name="processed_documents_pkey"),
)
sa.Index(
    "ix_processed_documents_document_id",
    metadata.tables["processed_documents"].c["document_id"],
    unique=True,
)

sa.Table(
    "provenance_events",
    metadata,
    sa.Column("document_id", sa.String(length=36), nullable=False),
    sa.Column(
        "event_type",
        sa.Enum(
            "CREATED",
            "UPLOADED",
            "EDITED",
            "AI_ASSISTED",
            "CITATION_ADDED",
            "REVISION",
            "EXPORTED",
            "SIGNED",
            name="provenanceeventtype",
        ),
        nullable=False,
    ),
    sa.Column("user_id", sa.String(length=36), nullable=True),
    sa.Column("event_timestamp", sa.DateTime(timezone=True), nullable=False),
    sa.Column("description", sa.Text(), nullable=True),
    sa.Column("sha256_before", sa.String(length=64), nullable=True),
    sa.Column("sha256_after", sa.String(length=64), nullable=True),
    sa.Column("metadata_json", sa.JSON(), nullable=True),
    sa.Column("id", sa.String(length=36), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.ForeignKeyConstraint(
        ["document_id"],
        ["documents.id"],
        name="provenance_events_document_id_fkey",
        ondelete="CASCADE",
    ),
    sa.ForeignKeyConstraint(
        ["user_id"],
        ["users.id"],
        name="provenance_events_user_id_fkey",
        ondelete="SET NULL",
    ),
    sa.PrimaryKeyConstraint("id", name="provenance_events_pkey"),
)
sa.Index(
    "ix_provenance_events_document_id",
    metadata.tables["provenance_events"].c["document_id"],
    unique=False,
)

sa.Table(
    "provenance_reports",
    metadata,
    sa.Column("document_id", sa.String(length=36), nullable=False),
    sa.Column("report_hash", sa.String(length=64), nullable=False),
    sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("signed_by_id", sa.String(length=36), nullable=True),
    sa.Column("report_data", sa.JSON(), nullable=False),
    sa.Column("id", sa.String(length=36), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.ForeignKeyConstraint(
        ["document_id"],
        ["documents.id"],
        name="provenance_reports_document_id_fkey",
        ondelete="CASCADE",
    ),
    sa.ForeignKeyConstraint(
        ["signed_by_id"], ["users.id"], name="provenance_reports_signed_by_id_fkey"
    ),
    sa.PrimaryKeyConstraint("id", name="provenance_reports_pkey"),
    sa.UniqueConstraint("document_id", name="provenance_reports_document_id_key"),
)

sa.Table(
    "refresh_tokens",
    metadata,
    sa.Column("user_id", sa.String(length=36), nullable=False),
    sa.Column("jti", sa.String(length=128), nullable=False),
    sa.Column("hashed_token", sa.String(length=255), nullable=False),
    sa.Column("token_family", sa.String(length=128), nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("replaced_by_jti", sa.String(length=128), nullable=True),
    sa.Column("ip_address", sa.String(length=45), nullable=True),
    sa.Column("user_agent", sa.Text(), nullable=True),
    sa.Column("id", sa.String(length=36), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.ForeignKeyConstraint(
        ["user_id"],
        ["users.id"],
        name="refresh_tokens_user_id_fkey",
        ondelete="CASCADE",
    ),
    sa.PrimaryKeyConstraint("id", name="refresh_tokens_pkey"),
)
sa.Index(
    "ix_refresh_tokens_jti", metadata.tables["refresh_tokens"].c["jti"], unique=True
)
sa.Index(
    "ix_refresh_tokens_token_family",
    metadata.tables["refresh_tokens"].c["token_family"],
    unique=False,
)
sa.Index(
    "ix_refresh_tokens_user_id",
    metadata.tables["refresh_tokens"].c["user_id"],
    unique=False,
)

sa.Table(
    "similarity_matches",
    metadata,
    sa.Column("document_id", sa.String(length=36), nullable=False),
    sa.Column("source_document_id", sa.String(length=36), nullable=True),
    sa.Column("external_source_id", sa.String(length=36), nullable=True),
    sa.Column(
        "match_type",
        sa.Enum(
            "EXACT",
            "NEAR_DUPLICATE",
            "LEXICAL",
            "SEMANTIC",
            "STRUCTURAL",
            "PROBABLE_PARAPHRASE",
            "PARAPHRASE",
            name="similaritytype",
        ),
        nullable=False,
    ),
    sa.Column("document_span_start", sa.Integer(), nullable=False),
    sa.Column("document_span_end", sa.Integer(), nullable=False),
    sa.Column("source_span_start", sa.Integer(), nullable=True),
    sa.Column("source_span_end", sa.Integer(), nullable=True),
    sa.Column("similarity_score", sa.Float(), nullable=False),
    sa.Column("semantic_score", sa.Float(), nullable=True),
    sa.Column("confidence", sa.Float(), nullable=False),
    sa.Column("matched_text", sa.Text(), nullable=True),
    sa.Column("source_text", sa.Text(), nullable=True),
    sa.Column("context_before", sa.Text(), nullable=True),
    sa.Column("context_after", sa.Text(), nullable=True),
    sa.Column("metadata_json", sa.JSON(), nullable=True),
    sa.Column("id", sa.String(length=36), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.ForeignKeyConstraint(
        ["document_id"],
        ["documents.id"],
        name="similarity_matches_document_id_fkey",
        ondelete="CASCADE",
    ),
    sa.ForeignKeyConstraint(
        ["source_document_id"],
        ["documents.id"],
        name="similarity_matches_source_document_id_fkey",
        ondelete="SET NULL",
    ),
    sa.PrimaryKeyConstraint("id", name="similarity_matches_pkey"),
)
sa.Index(
    "ix_similarity_matches_document_id",
    metadata.tables["similarity_matches"].c["document_id"],
    unique=False,
)
sa.Index(
    "ix_similarity_matches_external_source_id",
    metadata.tables["similarity_matches"].c["external_source_id"],
    unique=False,
)

sa.Table(
    "submissions",
    metadata,
    sa.Column("assignment_id", sa.String(length=36), nullable=False),
    sa.Column("student_id", sa.String(length=36), nullable=False),
    sa.Column("document_id", sa.String(length=36), nullable=True),
    sa.Column(
        "status",
        sa.Enum(
            "DRAFT",
            "SUBMITTED",
            "PROCESSING",
            "REVIEWED",
            "GRADED",
            "RETURNED",
            name="submissionstatus",
        ),
        nullable=False,
    ),
    sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("late_submission", sa.Boolean(), nullable=False),
    sa.Column("grade", sa.Float(), nullable=True),
    sa.Column("feedback", sa.Text(), nullable=True),
    sa.Column("graded_by_id", sa.String(length=36), nullable=True),
    sa.Column("graded_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("id", sa.String(length=36), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.ForeignKeyConstraint(
        ["assignment_id"],
        ["assignments.id"],
        name="submissions_assignment_id_fkey",
        ondelete="CASCADE",
    ),
    sa.ForeignKeyConstraint(
        ["document_id"],
        ["documents.id"],
        name="submissions_document_id_fkey",
        ondelete="SET NULL",
    ),
    sa.ForeignKeyConstraint(
        ["graded_by_id"], ["users.id"], name="submissions_graded_by_id_fkey"
    ),
    sa.ForeignKeyConstraint(
        ["student_id"], ["users.id"], name="submissions_student_id_fkey"
    ),
    sa.PrimaryKeyConstraint("id", name="submissions_pkey"),
)
sa.Index(
    "ix_submissions_assignment_id",
    metadata.tables["submissions"].c["assignment_id"],
    unique=False,
)
sa.Index(
    "ix_submissions_student_id",
    metadata.tables["submissions"].c["student_id"],
    unique=False,
)

sa.Table(
    "users",
    metadata,
    sa.Column("email", sa.String(length=255), nullable=False),
    sa.Column("hashed_password", sa.String(length=255), nullable=False),
    sa.Column("first_name", sa.String(length=100), nullable=True),
    sa.Column("last_name", sa.String(length=100), nullable=True),
    sa.Column("is_active", sa.Boolean(), nullable=False),
    sa.Column("is_verified", sa.Boolean(), nullable=False),
    sa.Column("is_superuser", sa.Boolean(), nullable=False),
    sa.Column("mfa_enabled", sa.Boolean(), nullable=False),
    sa.Column("mfa_secret", sa.String(length=255), nullable=True),
    sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("id", sa.String(length=36), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.PrimaryKeyConstraint("id", name="users_pkey"),
)
sa.Index("ix_users_email", metadata.tables["users"].c["email"], unique=True)
