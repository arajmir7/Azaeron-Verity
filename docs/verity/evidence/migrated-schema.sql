--
-- PostgreSQL database dump
--

\restrict KRpyhOxorLyMmwjmn6pcfbQKTdkjhyJf2D7ogjOjgv3lC1hVhLjmUSZevN7V7om

-- Dumped from database version 16.15 (Debian 16.15-1.pgdg12+2)
-- Dumped by pg_dump version 16.15 (Debian 16.15-1.pgdg12+2)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: app; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA app;


--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


--
-- Name: assignmentstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.assignmentstatus AS ENUM (
    'DRAFT',
    'PUBLISHED',
    'CLOSED',
    'ARCHIVED'
);


--
-- Name: auditaction; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.auditaction AS ENUM (
    'USER_LOGIN',
    'USER_LOGOUT',
    'USER_REGISTERED',
    'USER_UPDATED',
    'ORG_CREATED',
    'ORG_UPDATED',
    'ORG_MEMBER_INVITED',
    'ORG_MEMBER_JOINED',
    'DOCUMENT_UPLOADED',
    'DOCUMENT_DELETED',
    'DOCUMENT_PROCESSED',
    'JOB_CREATED',
    'JOB_COMPLETED',
    'JOB_FAILED',
    'SETTINGS_CHANGED',
    'API_KEY_CREATED',
    'API_KEY_REVOKED',
    'EXPORT_REQUESTED',
    'DATA_DELETED',
    'ASSIGNMENT_CREATED',
    'SUBMISSION_CREATED',
    'GRADE_ASSIGNED',
    'REPORT_VIEWED',
    'DETECTION_RUN',
    'WRITING_SUGGESTIONS',
    'WRITING_REFINEMENT',
    'WRITING_EDIT_APPLIED',
    'WRITING_EDIT_REJECTED'
);


--
-- Name: citationstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.citationstatus AS ENUM (
    'VALID',
    'BROKEN',
    'SUSPICIOUS',
    'UNVERIFIED',
    'FABRICATED'
);


--
-- Name: detectionverdict; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.detectionverdict AS ENUM (
    'HUMAN',
    'AI',
    'MIXED',
    'AI_ASSISTED',
    'UNCERTAIN',
    'INSUFFICIENT_EVIDENCE',
    'AI_GENERATED'
);


--
-- Name: documentstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.documentstatus AS ENUM (
    'PENDING',
    'VALIDATING',
    'QUEUED',
    'PROCESSING',
    'COMPLETED',
    'FAILED',
    'ARCHIVED'
);


--
-- Name: edittype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.edittype AS ENUM (
    'GRAMMAR',
    'CLARITY',
    'CONCISION',
    'TONE',
    'STRUCTURE',
    'CITATION',
    'VOCABULARY',
    'COHERENCE'
);


--
-- Name: evidencenodetype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.evidencenodetype AS ENUM (
    'DOCUMENT',
    'CLAIM',
    'CITATION',
    'SOURCE',
    'SIMILARITY',
    'AUTHORSHIP',
    'PROVENANCE',
    'DETECTION',
    'REVISION'
);


--
-- Name: jobstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.jobstatus AS ENUM (
    'PENDING',
    'RUNNING',
    'COMPLETED',
    'FAILED',
    'CANCELLED',
    'RETRYING'
);


--
-- Name: jobtype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.jobtype AS ENUM (
    'DOCUMENT_PROCESSING',
    'SIMILARITY_ANALYSIS',
    'CITATION_ANALYSIS',
    'AI_DETECTION',
    'AUTHORSHIP_ANALYSIS',
    'PROVENANCE_ANALYSIS',
    'REPORT_GENERATION',
    'EXPORT'
);


--
-- Name: organizationrole; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.organizationrole AS ENUM (
    'OWNER',
    'ADMIN',
    'FACULTY',
    'RESEARCHER',
    'STUDENT',
    'REVIEWER',
    'AUDITOR'
);


--
-- Name: provenanceeventtype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.provenanceeventtype AS ENUM (
    'CREATED',
    'UPLOADED',
    'EDITED',
    'AI_ASSISTED',
    'CITATION_ADDED',
    'REVISION',
    'EXPORTED',
    'SIGNED',
    'analysis_run',
    'ANALYSIS_RUN'
);


--
-- Name: reportstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.reportstatus AS ENUM (
    'PENDING',
    'GENERATING',
    'COMPLETED',
    'FAILED'
);


--
-- Name: similaritytype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.similaritytype AS ENUM (
    'EXACT',
    'NEAR_DUPLICATE',
    'LEXICAL',
    'SEMANTIC',
    'STRUCTURAL',
    'PROBABLE_PARAPHRASE',
    'PARAPHRASE'
);


--
-- Name: submissionstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.submissionstatus AS ENUM (
    'DRAFT',
    'SUBMITTED',
    'PROCESSING',
    'REVIEWED',
    'GRADED',
    'RETURNED'
);


--
-- Name: subscriptiontier; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.subscriptiontier AS ENUM (
    'FREE',
    'STUDENT',
    'PRO',
    'FACULTY',
    'INSTITUTION',
    'ENTERPRISE'
);


--
-- Name: supportstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.supportstatus AS ENUM (
    'SUPPORTED',
    'PARTIALLY_SUPPORTED',
    'NOT_SUPPORTED',
    'UNVERIFIABLE'
);


--
-- Name: current_organization_id(); Type: FUNCTION; Schema: app; Owner: -
--

CREATE FUNCTION app.current_organization_id() RETURNS text
    LANGUAGE sql STABLE
    AS $$ SELECT NULLIF(current_setting('app.current_organization_id', true), '') $$;


--
-- Name: current_user_id(); Type: FUNCTION; Schema: app; Owner: -
--

CREATE FUNCTION app.current_user_id() RETURNS text
    LANGUAGE sql STABLE
    AS $$ SELECT NULLIF(current_setting('app.current_user_id', true), '') $$;


--
-- Name: enforce_analysis_target(); Type: FUNCTION; Schema: app; Owner: -
--

CREATE FUNCTION app.enforce_analysis_target() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    DECLARE row_doc text; row_org text; payload jsonb;
    BEGIN
      SELECT v.document_id, d.organization_id INTO row_doc, row_org
        FROM document_versions v JOIN documents d ON d.id=v.document_id WHERE v.id=NEW.document_version_id;
      IF row_doc IS NULL OR row_doc IS DISTINCT FROM NEW.document_id OR row_org IS DISTINCT FROM NEW.organization_id THEN
        RAISE EXCEPTION 'analysis organization/document/version target mismatch';
      END IF;
      IF TG_OP='UPDATE' AND (OLD.document_id IS DISTINCT FROM NEW.document_id OR OLD.organization_id IS DISTINCT FROM NEW.organization_id
          OR OLD.document_version_id IS DISTINCT FROM NEW.document_version_id) THEN
        RAISE EXCEPTION 'analysis target lineage is immutable';
      END IF;
      IF TG_TABLE_NAME='processed_documents' AND TG_OP='INSERT' THEN
        payload := to_jsonb(NEW);
        IF payload->>'parser_version' IS NULL OR payload->>'parser_version'='legacy-unstructured'
          OR payload->>'normalized_content_hash' IS DISTINCT FROM encode(digest(convert_to(COALESCE(payload->>'cleaned_text',''), 'UTF8'), 'sha256'), 'hex')
          OR payload->'structure_json'->>'id' IS DISTINCT FROM NEW.id
          OR payload->'structure_json'->>'organization_id' IS DISTINCT FROM NEW.organization_id
          OR payload->'structure_json'->>'document_id' IS DISTINCT FROM NEW.document_id
          OR payload->'structure_json'->>'document_version_id' IS DISTINCT FROM NEW.document_version_id
          OR payload->'structure_json'->>'normalized_content_hash' IS DISTINCT FROM payload->>'normalized_content_hash'
          OR payload->'structure_json'->>'fingerprint' IS DISTINCT FROM payload->>'structure_fingerprint' THEN
          RAISE EXCEPTION 'normalized parser output must carry its exact target and content fingerprint';
        END IF;
      END IF;
      RETURN NEW;
    END $$;


--
-- Name: enforce_edge_target(); Type: FUNCTION; Schema: app; Owner: -
--

CREATE FUNCTION app.enforce_edge_target() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM evidence_nodes s, evidence_nodes t WHERE s.node_id=NEW.source_node_id AND t.node_id=NEW.target_node_id
        AND s.organization_id=NEW.organization_id AND t.organization_id=NEW.organization_id
        AND s.document_id=NEW.document_id AND t.document_id=NEW.document_id
        AND s.document_version_id=NEW.document_version_id AND t.document_version_id=NEW.document_version_id) THEN
        RAISE EXCEPTION 'evidence edge endpoints must share the analysis target';
      END IF;
      RETURN NEW;
    END $$;


--
-- Name: enforce_related_analysis_target(); Type: FUNCTION; Schema: app; Owner: -
--

CREATE FUNCTION app.enforce_related_analysis_target() RETURNS trigger
    LANGUAGE plpgsql
    AS $_$
    DECLARE parent jsonb; child jsonb; ref text; i integer;
    BEGIN
      child := to_jsonb(NEW); i := 0;
      WHILE i < TG_NARGS LOOP
        ref := child->>TG_ARGV[i];
        IF ref IS NOT NULL THEN
          EXECUTE format('SELECT to_jsonb(p) FROM %I p WHERE id=$1', TG_ARGV[i+1]) INTO parent USING ref;
          IF parent IS NULL OR parent->>'organization_id' IS DISTINCT FROM NEW.organization_id
            OR parent->>'document_id' IS DISTINCT FROM NEW.document_id OR parent->>'document_version_id' IS DISTINCT FROM NEW.document_version_id THEN
            RAISE EXCEPTION 'related analysis records must share one immutable target';
          END IF;
        END IF;
        i := i + 2;
      END LOOP;
      RETURN NEW;
    END $_$;


--
-- Name: freeze_document_operation(); Type: FUNCTION; Schema: app; Owner: -
--

CREATE FUNCTION app.freeze_document_operation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    BEGIN
      IF OLD.operation_id IS DISTINCT FROM NEW.operation_id
        OR OLD.operation_fingerprint IS DISTINCT FROM NEW.operation_fingerprint THEN
        RAISE EXCEPTION 'document operation identity is immutable';
      END IF;
      RETURN NEW;
    END $$;


--
-- Name: freeze_processed_document(); Type: FUNCTION; Schema: app; Owner: -
--

CREATE FUNCTION app.freeze_processed_document() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'parsed document history is immutable'; END IF;
      IF (to_jsonb(OLD) - 'updated_at') IS DISTINCT FROM (to_jsonb(NEW) - 'updated_at') THEN
        RAISE EXCEPTION 'parsed text, structure and parser identity are immutable';
      END IF;
      RETURN NEW;
    END $$;


--
-- Name: freeze_similarity_snapshot(); Type: FUNCTION; Schema: app; Owner: -
--

CREATE FUNCTION app.freeze_similarity_snapshot() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    BEGIN
      IF OLD.sealed AND (TG_OP='DELETE' OR to_jsonb(OLD) IS DISTINCT FROM to_jsonb(NEW)) THEN
        RAISE EXCEPTION 'completed similarity snapshots are immutable';
      END IF;
      IF TG_OP='DELETE' THEN RETURN OLD; END IF;
      RETURN NEW;
    END $$;


--
-- Name: prevent_document_version_mutation(); Type: FUNCTION; Schema: app; Owner: -
--

CREATE FUNCTION app.prevent_document_version_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        DECLARE old_rank integer; new_rank integer;
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'document versions are append-only';
          END IF;
          IF OLD.document_id IS DISTINCT FROM NEW.document_id
             OR OLD.version_number IS DISTINCT FROM NEW.version_number
             OR OLD.storage_path IS DISTINCT FROM NEW.storage_path
             OR OLD.content_hash IS DISTINCT FROM NEW.content_hash
             OR OLD.sha256_fingerprint IS DISTINCT FROM NEW.sha256_fingerprint
             OR OLD.created_by_id IS DISTINCT FROM NEW.created_by_id
             OR OLD.uploaded_by_id IS DISTINCT FROM NEW.uploaded_by_id
             OR OLD.uploaded_at IS DISTINCT FROM NEW.uploaded_at
             OR OLD.previous_version_id IS DISTINCT FROM NEW.previous_version_id
             OR OLD.change_summary IS DISTINCT FROM NEW.change_summary
             OR OLD.edit_type IS DISTINCT FROM NEW.edit_type THEN
            RAISE EXCEPTION 'historical document version content and lineage are immutable';
          END IF;
          old_rank := CASE OLD.lifecycle_state WHEN 'DRAFT' THEN 0 WHEN 'REVISION' THEN 1 WHEN 'FINAL' THEN 2 ELSE -1 END;
          new_rank := CASE NEW.lifecycle_state WHEN 'DRAFT' THEN 0 WHEN 'REVISION' THEN 1 WHEN 'FINAL' THEN 2 ELSE -1 END;
          IF new_rank < old_rank OR new_rank > old_rank + 1 THEN
            RAISE EXCEPTION 'document lifecycle transitions must be monotonic and sequential';
          END IF;
          RETURN NEW;
        END;
        $$;


--
-- Name: prevent_frozen_evaluation_dataset_mutation(); Type: FUNCTION; Schema: app; Owner: -
--

CREATE FUNCTION app.prevent_frozen_evaluation_dataset_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
            IF TG_TABLE_NAME = 'evaluation_datasets' THEN
                IF OLD.immutable OR OLD.status IN ('FROZEN', 'RETIRED') THEN
                    RAISE EXCEPTION 'evaluation dataset version % is immutable', OLD.id;
                END IF;
                IF TG_OP = 'DELETE' THEN
                    RETURN OLD;
                END IF;
                RETURN NEW;
            END IF;

            IF EXISTS (
                SELECT 1 FROM evaluation_datasets
                 WHERE id = COALESCE(NEW.dataset_id, OLD.dataset_id)
                   AND (immutable OR status IN ('FROZEN', 'RETIRED'))
            ) THEN
                RAISE EXCEPTION 'evaluation examples for a frozen dataset are immutable';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$;


--
-- Name: prevent_provenance_events_mutation(); Type: FUNCTION; Schema: app; Owner: -
--

CREATE FUNCTION app.prevent_provenance_events_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
            BEGIN
              RAISE EXCEPTION 'provenance_events are append-only';
            END;
            $$;


--
-- Name: prevent_provenance_exports_mutation(); Type: FUNCTION; Schema: app; Owner: -
--

CREATE FUNCTION app.prevent_provenance_exports_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
            BEGIN
              RAISE EXCEPTION 'provenance_exports are append-only';
            END;
            $$;


--
-- Name: prevent_provenance_reports_mutation(); Type: FUNCTION; Schema: app; Owner: -
--

CREATE FUNCTION app.prevent_provenance_reports_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
            BEGIN
              RAISE EXCEPTION 'provenance_reports are append-only';
            END;
            $$;


--
-- Name: validate_similarity_evidence(); Type: FUNCTION; Schema: app; Owner: -
--

CREATE FUNCTION app.validate_similarity_evidence() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    DECLARE snapshot_id text; target_text text; source_text text;
    BEGIN
      IF TG_OP='DELETE' THEN snapshot_id=OLD.analysis_id; ELSE snapshot_id=NEW.analysis_id; END IF;
      IF EXISTS (SELECT 1 FROM similarity_analyses WHERE id=snapshot_id AND sealed) THEN
        IF TG_OP<>'UPDATE' OR to_jsonb(OLD) IS DISTINCT FROM to_jsonb(NEW) THEN
          RAISE EXCEPTION 'completed similarity evidence is immutable';
        END IF;
      END IF;
      IF TG_OP='DELETE' THEN RETURN OLD; END IF;
      IF NEW.pipeline_version='similarity-engine-v2' THEN
        SELECT p.cleaned_text INTO target_text FROM processed_documents p WHERE p.document_version_id=NEW.document_version_id AND p.organization_id=NEW.organization_id;
        SELECT p.cleaned_text INTO source_text FROM processed_documents p JOIN document_versions v ON v.id=p.document_version_id
          WHERE v.id=NEW.source_document_version_id AND v.document_id=NEW.source_document_id AND p.organization_id=NEW.organization_id;
        IF target_text IS NULL OR source_text IS NULL OR NEW.target_document_id IS DISTINCT FROM NEW.document_id
          OR NEW.analysis_id IS NULL OR NEW.group_id IS NULL
          OR NEW.document_span_end>length(target_text) OR NEW.source_span_start<0 OR NEW.source_span_end>length(source_text)
          OR NEW.matched_text IS DISTINCT FROM substring(target_text FROM NEW.document_span_start+1 FOR NEW.document_span_end-NEW.document_span_start)
          OR NEW.source_text IS DISTINCT FROM substring(source_text FROM NEW.source_span_start+1 FOR NEW.source_span_end-NEW.source_span_start) THEN
          RAISE EXCEPTION 'similarity evidence must resolve to exact tenant/version source and target spans';
        END IF;
      END IF;
      RETURN NEW;
    END $$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: aegis_edits; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.aegis_edits (
    document_id character varying(36) NOT NULL,
    user_id character varying(36) NOT NULL,
    edit_type public.edittype NOT NULL,
    original_text text NOT NULL,
    suggested_text text NOT NULL,
    explanation text NOT NULL,
    span_start integer NOT NULL,
    span_end integer NOT NULL,
    applied boolean NOT NULL,
    applied_at timestamp with time zone,
    ai_generated boolean NOT NULL,
    metadata_json json,
    id character varying(36) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    organization_id character varying(36) NOT NULL,
    document_version_id character varying(36) NOT NULL,
    parent_edit_id character varying(36),
    dimension character varying(50) NOT NULL,
    preserve_voice boolean NOT NULL,
    engine_version character varying(80) NOT NULL,
    source_text_hash character varying(64)
);

ALTER TABLE ONLY public.aegis_edits FORCE ROW LEVEL SECURITY;


--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: analysis_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.analysis_runs (
    id character varying(36) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    organization_id character varying(36) NOT NULL,
    document_id character varying(36) NOT NULL,
    document_version_id character varying(36) NOT NULL,
    job_id character varying(36),
    model_id character varying(120) NOT NULL,
    model_version character varying(80) NOT NULL,
    pipeline_version character varying(80) NOT NULL,
    dataset_version character varying(120),
    status character varying(20) DEFAULT 'STARTED'::character varying NOT NULL,
    abstained boolean DEFAULT false NOT NULL,
    input_fingerprint character varying(64),
    metadata_json json,
    started_at timestamp with time zone,
    completed_at timestamp with time zone
);

ALTER TABLE ONLY public.analysis_runs FORCE ROW LEVEL SECURITY;


--
-- Name: api_keys; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.api_keys (
    user_id character varying(36) NOT NULL,
    organization_id character varying(36) NOT NULL,
    name character varying(100) NOT NULL,
    key_prefix character varying(8) NOT NULL,
    hashed_key character varying(255) NOT NULL,
    scopes text,
    last_used_at timestamp with time zone,
    expires_at timestamp with time zone,
    is_active boolean NOT NULL,
    id character varying(36) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);

ALTER TABLE ONLY public.api_keys FORCE ROW LEVEL SECURITY;


--
-- Name: assignments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.assignments (
    organization_id character varying(36) NOT NULL,
    created_by_id character varying(36) NOT NULL,
    title character varying(500) NOT NULL,
    description text,
    instructions text,
    status public.assignmentstatus NOT NULL,
    due_date timestamp with time zone,
    max_file_size_mb integer NOT NULL,
    allowed_extensions json NOT NULL,
    rubric json,
    settings json,
    id character varying(36) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);

ALTER TABLE ONLY public.assignments FORCE ROW LEVEL SECURITY;


--
-- Name: audit_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_logs (
    organization_id character varying(36),
    user_id character varying(36),
    action public.auditaction NOT NULL,
    resource_type character varying(50) NOT NULL,
    resource_id character varying(36),
    details json,
    ip_address character varying(45),
    user_agent text,
    request_id character varying(36),
    "timestamp" timestamp with time zone NOT NULL,
    id character varying(36) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);

ALTER TABLE ONLY public.audit_logs FORCE ROW LEVEL SECURITY;


--
-- Name: authorship_profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.authorship_profiles (
    user_id character varying(36) NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    baseline_document_ids json,
    stylometric_features json,
    vocabulary_distribution json,
    punctuation_patterns json,
    syntax_patterns json,
    id character varying(36) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    organization_id character varying(36)
);

ALTER TABLE ONLY public.authorship_profiles FORCE ROW LEVEL SECURITY;


--
-- Name: authorship_signals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.authorship_signals (
    document_id character varying(36) NOT NULL,
    profile_id character varying(36),
    consistency_score double precision,
    confidence double precision,
    stylistic_drift_score double precision,
    unusual_segments json,
    explanation text,
    limitations text,
    id character varying(36) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    verdict character varying(40) DEFAULT 'INSUFFICIENT_DATA'::character varying NOT NULL,
    baseline_quality character varying(40),
    model_version character varying(80) DEFAULT 'authorship-unavailable-v1'::character varying NOT NULL,
    pipeline_version character varying(80) DEFAULT 'authorship-pipeline-v1'::character varying NOT NULL,
    feature_data json,
    organization_id character varying(36) NOT NULL,
    document_version_id character varying(36) NOT NULL,
    stylistic_deviation json,
    ai_writing_signal json,
    confidence_type character varying(80),
    evidence_id character varying(36)
);

ALTER TABLE ONLY public.authorship_signals FORCE ROW LEVEL SECURITY;


--
-- Name: billing_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.billing_events (
    organization_id character varying(36) NOT NULL,
    event_type character varying(50) NOT NULL,
    quantity integer NOT NULL,
    unit_cost double precision,
    total_cost double precision,
    description text,
    metadata_json json,
    "timestamp" timestamp with time zone NOT NULL,
    id character varying(36) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);

ALTER TABLE ONLY public.billing_events FORCE ROW LEVEL SECURITY;


--
-- Name: citation_findings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.citation_findings (
    id character varying(36) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    organization_id character varying(36) NOT NULL,
    document_version_id character varying(36) NOT NULL,
    pipeline_version character varying(80) NOT NULL,
    model_version character varying(80),
    document_id character varying(36) NOT NULL,
    claim_id character varying(36),
    citation_id character varying(36),
    reference_id character varying(36),
    source_id character varying(36),
    evidence_id character varying(36),
    finding_type character varying(60) NOT NULL,
    support_status public.supportstatus NOT NULL,
    message text NOT NULL,
    evidence_json json,
    confidence double precision DEFAULT '0'::double precision NOT NULL,
    CONSTRAINT ck_citation_findings_confidence CHECK (((confidence >= (0)::double precision) AND (confidence <= (1)::double precision)))
);

ALTER TABLE ONLY public.citation_findings FORCE ROW LEVEL SECURITY;


--
-- Name: citation_references; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.citation_references (
    id character varying(36) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    organization_id character varying(36) NOT NULL,
    document_version_id character varying(36) NOT NULL,
    pipeline_version character varying(80) NOT NULL,
    model_version character varying(80),
    document_id character varying(36) NOT NULL,
    source_id character varying(36),
    reference_key character varying(180) NOT NULL,
    raw_text text NOT NULL,
    authors json,
    title text,
    year integer,
    doi character varying(255),
    url text,
    journal text,
    publisher text,
    metadata_json json
);

ALTER TABLE ONLY public.citation_references FORCE ROW LEVEL SECURITY;


--
-- Name: citation_sources; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.citation_sources (
    id character varying(36) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    organization_id character varying(36) NOT NULL,
    document_version_id character varying(36) NOT NULL,
    pipeline_version character varying(80) NOT NULL,
    model_version character varying(80),
    source_key character varying(180) NOT NULL,
    title text,
    authors json,
    publisher text,
    doi character varying(255),
    url text,
    retrieval_timestamp timestamp with time zone,
    retrieval_status character varying(30) DEFAULT 'NOT_ATTEMPTED'::character varying NOT NULL,
    abstract_text text,
    retrieved_payload_hash character varying(64),
    metadata_json json,
    document_id character varying(36) NOT NULL
);

ALTER TABLE ONLY public.citation_sources FORCE ROW LEVEL SECURITY;


--
-- Name: citations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.citations (
    document_id character varying(36) NOT NULL,
    claim_id character varying(36),
    raw_text text NOT NULL,
    citation_type character varying(50),
    authors json,
    title text,
    year integer,
    doi character varying(255),
    url text,
    journal text,
    publisher text,
    status public.citationstatus NOT NULL,
    verification_data json,
    span_start integer NOT NULL,
    span_end integer NOT NULL,
    id character varying(36) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    organization_id character varying(36) NOT NULL,
    document_version_id character varying(36) NOT NULL,
    pipeline_version character varying(80) NOT NULL,
    model_version character varying(80),
    reference_id character varying(36),
    source_id character varying(36),
    evidence_id character varying(36),
    citation_key character varying(180),
    support_status public.supportstatus NOT NULL,
    retrieval_timestamp timestamp with time zone
);

ALTER TABLE ONLY public.citations FORCE ROW LEVEL SECURITY;


--
-- Name: claims; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.claims (
    document_id character varying(36) NOT NULL,
    text text NOT NULL,
    claim_type character varying(50),
    span_start integer NOT NULL,
    span_end integer NOT NULL,
    has_citation boolean NOT NULL,
    citation_supports_claim boolean,
    confidence double precision NOT NULL,
    id character varying(36) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    organization_id character varying(36) NOT NULL,
    document_version_id character varying(36) NOT NULL,
    pipeline_version character varying(80) NOT NULL,
    model_version character varying(80),
    support_status public.supportstatus NOT NULL,
    evidence_id character varying(36)
);

ALTER TABLE ONLY public.claims FORCE ROW LEVEL SECURITY;


--
-- Name: compliance_reports; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.compliance_reports (
    organization_id character varying(36) NOT NULL,
    report_type character varying(50) NOT NULL,
    generated_by_id character varying(36) NOT NULL,
    report_data json NOT NULL,
    download_url text,
    expires_at timestamp with time zone,
    id character varying(36) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);

ALTER TABLE ONLY public.compliance_reports FORCE ROW LEVEL SECURITY;


--
-- Name: detection_results; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.detection_results (
    document_id character varying(36) NOT NULL,
    job_id character varying(36) NOT NULL,
    model_version character varying(50) NOT NULL,
    pipeline_version character varying(50) NOT NULL,
    overall_verdict public.detectionverdict NOT NULL,
    confidence double precision,
    calibration_score double precision,
    human_probability double precision,
    ai_probability double precision,
    mixed_probability double precision,
    uncertain_probability double precision,
    explanation text,
    limitations text,
    feature_data json,
    id character varying(36) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    document_version_id character varying(36) NOT NULL,
    analysis_run_id character varying(36),
    release_status character varying(20) DEFAULT 'EXPERIMENTAL'::character varying NOT NULL,
    abstained boolean DEFAULT true NOT NULL,
    organization_id character varying(36) NOT NULL,
    feature_version character varying(80) NOT NULL,
    calibrator_version character varying(80),
    uncertainty_method character varying(120),
    confidence_reliability character varying(40) DEFAULT 'UNAVAILABLE'::character varying NOT NULL,
    inference_id character varying(36) NOT NULL,
    inference_metadata_json json,
    evidence_json json DEFAULT '[]'::json NOT NULL,
    abstention_reason text,
    CONSTRAINT ck_detection_results_ai_probability_range CHECK (((ai_probability >= (0)::double precision) AND (ai_probability <= (1)::double precision))),
    CONSTRAINT ck_detection_results_confidence_range CHECK (((confidence >= (0)::double precision) AND (confidence <= (1)::double precision))),
    CONSTRAINT ck_detection_results_human_probability_range CHECK (((human_probability >= (0)::double precision) AND (human_probability <= (1)::double precision))),
    CONSTRAINT ck_detection_results_mixed_probability_range CHECK (((mixed_probability >= (0)::double precision) AND (mixed_probability <= (1)::double precision))),
    CONSTRAINT ck_detection_results_uncertain_probability_range CHECK (((uncertain_probability >= (0)::double precision) AND (uncertain_probability <= (1)::double precision)))
);

ALTER TABLE ONLY public.detection_results FORCE ROW LEVEL SECURITY;


--
-- Name: detection_segments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.detection_segments (
    detection_result_id character varying(36) NOT NULL,
    segment_type character varying(20) NOT NULL,
    segment_index integer NOT NULL,
    text text NOT NULL,
    span_start integer NOT NULL,
    span_end integer NOT NULL,
    verdict public.detectionverdict NOT NULL,
    confidence double precision NOT NULL,
    perplexity double precision,
    burstiness double precision,
    feature_scores json,
    explanation text,
    id character varying(36) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    organization_id character varying(36) NOT NULL,
    document_id character varying(36) NOT NULL,
    document_version_id character varying(36) NOT NULL,
    CONSTRAINT ck_detection_segments_confidence_range CHECK (((confidence >= (0)::double precision) AND (confidence <= (1)::double precision))),
    CONSTRAINT ck_detection_segments_span CHECK (((span_start >= 0) AND (span_end >= span_start)))
);

ALTER TABLE ONLY public.detection_segments FORCE ROW LEVEL SECURITY;


--
-- Name: document_chunks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.document_chunks (
    document_id character varying(36) NOT NULL,
    chunk_index integer NOT NULL,
    text text NOT NULL,
    start_char integer NOT NULL,
    end_char integer NOT NULL,
    embedding json,
    token_count integer NOT NULL,
    id character varying(36) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    organization_id character varying(36) NOT NULL,
    document_version_id character varying(36) NOT NULL,
    pipeline_version character varying(80) NOT NULL,
    model_version character varying(80),
    normalized_text text,
    content_hash character varying(64),
    index_version character varying(80) NOT NULL,
    index_status character varying(20) NOT NULL,
    indexed_at timestamp with time zone,
    structure_json json,
    embedding_vector public.vector(384),
    embedding_model character varying(180),
    CONSTRAINT ck_document_chunks_index_nonnegative CHECK ((chunk_index >= 0)),
    CONSTRAINT ck_document_chunks_span CHECK (((start_char >= 0) AND (end_char >= start_char)))
);

ALTER TABLE ONLY public.document_chunks FORCE ROW LEVEL SECURITY;


--
-- Name: document_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.document_versions (
    document_id character varying(36) NOT NULL,
    version_number integer NOT NULL,
    storage_path character varying(500) NOT NULL,
    sha256_fingerprint character varying(64) NOT NULL,
    created_by_id character varying(36) NOT NULL,
    change_summary text,
    edit_type character varying(50),
    id character varying(36) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    uploaded_at timestamp with time zone NOT NULL,
    uploaded_by_id character varying(36),
    content_hash character varying(64) NOT NULL,
    previous_version_id character varying(36),
    lifecycle_state character varying(20) DEFAULT 'DRAFT'::character varying NOT NULL,
    operation_id character varying(36),
    operation_fingerprint character varying(64),
    CONSTRAINT ck_document_versions_content_hash_length CHECK ((length((content_hash)::text) = 64)),
    CONSTRAINT ck_document_versions_lifecycle_state CHECK (((lifecycle_state)::text = ANY ((ARRAY['DRAFT'::character varying, 'REVISION'::character varying, 'FINAL'::character varying])::text[]))),
    CONSTRAINT ck_document_versions_number_positive CHECK ((version_number > 0)),
    CONSTRAINT ck_document_versions_operation CHECK ((((operation_id IS NULL) AND (operation_fingerprint IS NULL)) OR ((operation_id IS NOT NULL) AND (operation_fingerprint IS NOT NULL) AND (length((operation_fingerprint)::text) = 64))))
);

ALTER TABLE ONLY public.document_versions FORCE ROW LEVEL SECURITY;


--
-- Name: documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.documents (
    organization_id character varying(36) NOT NULL,
    owner_id character varying(36) NOT NULL,
    assignment_id character varying(36),
    submission_id character varying(36),
    title character varying(500),
    filename character varying(255) NOT NULL,
    original_filename character varying(255) NOT NULL,
    file_size integer NOT NULL,
    mime_type character varying(100) NOT NULL,
    extension character varying(20) NOT NULL,
    sha256_fingerprint character varying(64) NOT NULL,
    storage_path character varying(500) NOT NULL,
    status public.documentstatus NOT NULL,
    metadata_json text,
    error_message text,
    processed_at timestamp with time zone,
    word_count integer,
    language character varying(10),
    id character varying(36) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    uploaded_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_documents_file_size_positive CHECK ((file_size > 0)),
    CONSTRAINT ck_documents_sha256_length CHECK ((length((sha256_fingerprint)::text) = 64))
);

ALTER TABLE ONLY public.documents FORCE ROW LEVEL SECURITY;


--
-- Name: evaluation_datasets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.evaluation_datasets (
    id character varying(36) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    dataset_id character varying(120) NOT NULL,
    version character varying(80) NOT NULL,
    description text NOT NULL,
    status character varying(20) DEFAULT 'DRAFT'::character varying NOT NULL,
    schema_json json,
    manifest_sha256 character varying(64),
    row_count integer DEFAULT 0 NOT NULL,
    leakage_checks json,
    provenance_json json NOT NULL,
    immutable boolean DEFAULT false NOT NULL,
    frozen_at timestamp with time zone
);


--
-- Name: evaluation_examples; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.evaluation_examples (
    id character varying(36) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    dataset_id character varying(36) NOT NULL,
    example_key character varying(180) NOT NULL,
    split character varying(30) NOT NULL,
    label character varying(80) NOT NULL,
    text_sha256 character varying(64) NOT NULL,
    author_key_hash character varying(128),
    domain character varying(120),
    genre character varying(120),
    language character varying(20),
    generation_source character varying(120),
    editing_intensity character varying(80),
    metadata_json json,
    document_key_hash character varying(128),
    source_document_hash character varying(128),
    document_length integer,
    writing_proficiency character varying(80)
);


--
-- Name: evidence_edges; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.evidence_edges (
    source_node_id character varying(36) NOT NULL,
    target_node_id character varying(36) NOT NULL,
    edge_type character varying(50) NOT NULL,
    weight double precision NOT NULL,
    description text,
    metadata_json json,
    id character varying(36) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    organization_id character varying(36) NOT NULL,
    document_id character varying(36) NOT NULL,
    document_version_id character varying(36) NOT NULL,
    CONSTRAINT ck_evidence_edges_type CHECK (((edge_type)::text = ANY ((ARRAY['CONTAINS'::character varying, 'VERSION_OF'::character varying, 'CITES'::character varying, 'SUPPORTED_BY'::character varying, 'SIMILAR_TO'::character varying, 'HAS_SIGNAL'::character varying, 'DERIVED_FROM'::character varying, 'GENERATED_FINDING'::character varying])::text[])))
);

ALTER TABLE ONLY public.evidence_edges FORCE ROW LEVEL SECURITY;


--
-- Name: evidence_nodes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.evidence_nodes (
    document_id character varying(36) NOT NULL,
    node_type public.evidencenodetype NOT NULL,
    node_id character varying(36) NOT NULL,
    title text NOT NULL,
    description text,
    span_start integer,
    span_end integer,
    confidence double precision NOT NULL,
    severity character varying(20),
    metadata_json json,
    id character varying(36) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    organization_id character varying(36) NOT NULL,
    document_version_id character varying(36) NOT NULL,
    finding_type character varying(80) DEFAULT 'evidence'::character varying NOT NULL,
    source_id character varying(180),
    model_id character varying(120),
    model_version character varying(80),
    pipeline_version character varying(80) NOT NULL,
    canonical_type character varying(40) NOT NULL,
    entity_id character varying(180) NOT NULL,
    entity_type character varying(60) NOT NULL,
    span_text text,
    CONSTRAINT ck_evidence_nodes_canonical_type CHECK (((canonical_type)::text = ANY ((ARRAY['DOCUMENT'::character varying, 'DOCUMENT_VERSION'::character varying, 'CLAIM'::character varying, 'CITATION'::character varying, 'SOURCE'::character varying, 'SIMILARITY_MATCH'::character varying, 'AI_SIGNAL'::character varying, 'AUTHORSHIP_SIGNAL'::character varying, 'PROVENANCE_EVENT'::character varying, 'FINDING'::character varying, 'REPORT'::character varying])::text[]))),
    CONSTRAINT ck_evidence_nodes_confidence_range CHECK (((confidence >= (0)::double precision) AND (confidence <= (1)::double precision))),
    CONSTRAINT ck_evidence_nodes_entity_id_nonempty CHECK ((length((entity_id)::text) > 0)),
    CONSTRAINT ck_evidence_nodes_node_id_nonempty CHECK ((length((node_id)::text) > 0)),
    CONSTRAINT ck_evidence_nodes_span CHECK (((span_start IS NULL) OR ((span_start >= 0) AND (span_end >= span_start))))
);

ALTER TABLE ONLY public.evidence_nodes FORCE ROW LEVEL SECURITY;


--
-- Name: integrity_reports; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.integrity_reports (
    document_id character varying(36) NOT NULL,
    status public.reportstatus NOT NULL,
    originality_score double precision,
    originality_confidence character varying(20),
    ai_signal_score double precision,
    ai_signal_confidence character varying(20),
    ai_signal_verdict character varying(50),
    authorship_consistency_score double precision,
    authorship_confidence character varying(20),
    citation_integrity_score double precision,
    source_quality_score double precision,
    provenance_strength character varying(20),
    writing_quality_score double precision,
    priority_issues json,
    report_data json,
    id character varying(36) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    organization_id character varying(36) NOT NULL,
    document_version_id character varying(36) NOT NULL,
    pipeline_version character varying(80) NOT NULL,
    model_version character varying(80)
);

ALTER TABLE ONLY public.integrity_reports FORCE ROW LEVEL SECURITY;


--
-- Name: jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.jobs (
    organization_id character varying(36) NOT NULL,
    document_id character varying(36) NOT NULL,
    job_type public.jobtype NOT NULL,
    status public.jobstatus NOT NULL,
    priority integer NOT NULL,
    progress_percent integer NOT NULL,
    input_data json,
    result_data json,
    error_message text,
    retry_count integer NOT NULL,
    max_retries integer NOT NULL,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    celery_task_id character varying(255),
    id character varying(36) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    document_version_id character varying(36) NOT NULL,
    CONSTRAINT ck_jobs_max_retries_nonnegative CHECK ((max_retries >= 0)),
    CONSTRAINT ck_jobs_progress_range CHECK (((progress_percent >= 0) AND (progress_percent <= 100))),
    CONSTRAINT ck_jobs_retry_count_nonnegative CHECK ((retry_count >= 0))
);

ALTER TABLE ONLY public.jobs FORCE ROW LEVEL SECURITY;


--
-- Name: memberships; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.memberships (
    user_id character varying(36) NOT NULL,
    organization_id character varying(36) NOT NULL,
    role public.organizationrole NOT NULL,
    is_active boolean NOT NULL,
    joined_at timestamp with time zone NOT NULL,
    invited_by_id character varying(36),
    id character varying(36) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: model_registry; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.model_registry (
    id character varying(36) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    model_id character varying(120) NOT NULL,
    model_version character varying(80) NOT NULL,
    pipeline_version character varying(80) NOT NULL,
    dataset_version character varying(120),
    lifecycle_status character varying(20) DEFAULT 'EXPERIMENTAL'::character varying NOT NULL,
    metrics json,
    limitations json,
    provenance json,
    promoted_at timestamp with time zone
);


--
-- Name: organizations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.organizations (
    name character varying(255) NOT NULL,
    slug character varying(255) NOT NULL,
    description text,
    is_active boolean NOT NULL,
    settings text,
    subscription_tier public.subscriptiontier DEFAULT 'FREE'::public.subscriptiontier NOT NULL,
    subscription_expires_at timestamp with time zone,
    usage_documents_month integer NOT NULL,
    usage_storage_mb integer NOT NULL,
    usage_api_calls integer NOT NULL,
    id character varying(36) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: processed_documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.processed_documents (
    document_id character varying(36) NOT NULL,
    raw_text text,
    cleaned_text text,
    paragraphs json,
    sentences json,
    sections json,
    language character varying(10),
    word_count integer NOT NULL,
    sentence_count integer NOT NULL,
    paragraph_count integer NOT NULL,
    avg_sentence_length double precision,
    avg_word_length double precision,
    readability_flesch double precision,
    readability_flesch_kincaid double precision,
    lexical_diversity double precision,
    id character varying(36) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    document_version_id character varying(36) NOT NULL,
    organization_id character varying(36) NOT NULL,
    pipeline_version character varying(80) NOT NULL,
    model_version character varying(80),
    parser_version character varying(80) DEFAULT 'legacy-unstructured'::character varying NOT NULL,
    normalized_content_hash character varying(64),
    structure_fingerprint character varying(64),
    structure_json json
);

ALTER TABLE ONLY public.processed_documents FORCE ROW LEVEL SECURITY;


--
-- Name: provenance_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.provenance_events (
    document_id character varying(36) NOT NULL,
    event_type public.provenanceeventtype NOT NULL,
    user_id character varying(36),
    event_timestamp timestamp with time zone NOT NULL,
    description text,
    sha256_before character varying(64),
    sha256_after character varying(64),
    metadata_json json,
    id character varying(36) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    organization_id character varying(36) NOT NULL,
    document_version_id character varying(36) NOT NULL,
    pipeline_version character varying(80) NOT NULL,
    model_version character varying(80),
    analysis_run_id character varying(36)
);

ALTER TABLE ONLY public.provenance_events FORCE ROW LEVEL SECURITY;


--
-- Name: provenance_exports; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.provenance_exports (
    id character varying(36) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    organization_id character varying(36) NOT NULL,
    document_version_id character varying(36) NOT NULL,
    pipeline_version character varying(80) NOT NULL,
    model_version character varying(80),
    document_id character varying(36) NOT NULL,
    exported_by_id character varying(36) NOT NULL,
    exported_at timestamp with time zone NOT NULL,
    export_format character varying(20) DEFAULT 'json'::character varying NOT NULL,
    export_hash character varying(64) NOT NULL,
    payload json NOT NULL
);

ALTER TABLE ONLY public.provenance_exports FORCE ROW LEVEL SECURITY;


--
-- Name: provenance_reports; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.provenance_reports (
    document_id character varying(36) NOT NULL,
    report_hash character varying(64) NOT NULL,
    signed_at timestamp with time zone,
    signed_by_id character varying(36),
    report_data json NOT NULL,
    id character varying(36) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    organization_id character varying(36) NOT NULL,
    document_version_id character varying(36) NOT NULL,
    pipeline_version character varying(80) NOT NULL,
    model_version character varying(80)
);

ALTER TABLE ONLY public.provenance_reports FORCE ROW LEVEL SECURITY;


--
-- Name: refresh_tokens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.refresh_tokens (
    user_id character varying(36) NOT NULL,
    jti character varying(128) NOT NULL,
    hashed_token character varying(255) NOT NULL,
    token_family character varying(128) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    replaced_by_jti character varying(128),
    ip_address character varying(45),
    user_agent text,
    id character varying(36) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: similarity_analyses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.similarity_analyses (
    id character varying(36) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    organization_id character varying(36) NOT NULL,
    document_id character varying(36) NOT NULL,
    document_version_id character varying(36) NOT NULL,
    pipeline_version character varying(80) NOT NULL,
    model_version character varying(80),
    text_hash character varying(64) NOT NULL,
    corpus_state character varying(30) NOT NULL,
    corpus_version_count integer NOT NULL,
    index_version character varying(80) NOT NULL,
    completed_at timestamp with time zone NOT NULL,
    truncated boolean NOT NULL,
    metadata_json json NOT NULL,
    analysis_run_id character varying(36),
    run_key character varying(80) DEFAULT 'default'::character varying NOT NULL,
    snapshot_fingerprint character varying(64),
    sealed boolean DEFAULT false NOT NULL
);

ALTER TABLE ONLY public.similarity_analyses FORCE ROW LEVEL SECURITY;


--
-- Name: similarity_index_entries; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.similarity_index_entries (
    id character varying(36) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    organization_id character varying(36) NOT NULL,
    document_version_id character varying(36) NOT NULL,
    pipeline_version character varying(80) NOT NULL,
    model_version character varying(80),
    chunk_id character varying(36) NOT NULL,
    document_id character varying(36) NOT NULL,
    term character varying(300) NOT NULL,
    term_type character varying(20) NOT NULL,
    term_frequency double precision DEFAULT '1'::double precision NOT NULL,
    positions json,
    index_version character varying(80) NOT NULL,
    CONSTRAINT ck_similarity_index_term_frequency CHECK ((term_frequency > (0)::double precision)),
    CONSTRAINT ck_similarity_index_term_type CHECK (((term_type)::text = ANY ((ARRAY['token'::character varying, 'ngram'::character varying, 'fingerprint'::character varying])::text[])))
);

ALTER TABLE ONLY public.similarity_index_entries FORCE ROW LEVEL SECURITY;


--
-- Name: similarity_matches; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.similarity_matches (
    document_id character varying(36) NOT NULL,
    source_document_id character varying(36),
    external_source_id character varying(36),
    match_type public.similaritytype NOT NULL,
    document_span_start integer NOT NULL,
    document_span_end integer NOT NULL,
    source_span_start integer,
    source_span_end integer,
    similarity_score double precision NOT NULL,
    semantic_score double precision,
    confidence double precision NOT NULL,
    matched_text text,
    source_text text,
    context_before text,
    context_after text,
    metadata_json json,
    id character varying(36) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    organization_id character varying(36) NOT NULL,
    document_version_id character varying(36) NOT NULL,
    pipeline_version character varying(80) NOT NULL,
    model_version character varying(80),
    target_document_id character varying(36) NOT NULL,
    evidence_id character varying(36),
    retrieval_score double precision,
    lexical_score double precision,
    ngram_score double precision,
    structural_score double precision,
    verification_score double precision,
    confidence_reliability character varying(40) NOT NULL,
    candidate_rank integer,
    retrieval_methods json,
    verification_methods json,
    source_document_version_id character varying(36),
    analysis_id character varying(36),
    group_id character varying(36),
    CONSTRAINT ck_similarity_matches_confidence_range CHECK (((confidence >= (0)::double precision) AND (confidence <= (1)::double precision))),
    CONSTRAINT ck_similarity_matches_document_span CHECK (((document_span_start >= 0) AND (document_span_end >= document_span_start))),
    CONSTRAINT ck_similarity_matches_score_range CHECK (((similarity_score >= (0)::double precision) AND (similarity_score <= (1)::double precision)))
);

ALTER TABLE ONLY public.similarity_matches FORCE ROW LEVEL SECURITY;


--
-- Name: submissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.submissions (
    assignment_id character varying(36) NOT NULL,
    student_id character varying(36) NOT NULL,
    document_id character varying(36),
    status public.submissionstatus NOT NULL,
    submitted_at timestamp with time zone,
    late_submission boolean NOT NULL,
    grade double precision,
    feedback text,
    graded_by_id character varying(36),
    graded_at timestamp with time zone,
    id character varying(36) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);

ALTER TABLE ONLY public.submissions FORCE ROW LEVEL SECURITY;


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    email character varying(255) NOT NULL,
    hashed_password character varying(255) NOT NULL,
    first_name character varying(100),
    last_name character varying(100),
    is_active boolean NOT NULL,
    is_verified boolean NOT NULL,
    is_superuser boolean NOT NULL,
    mfa_enabled boolean NOT NULL,
    mfa_secret character varying(255),
    last_login_at timestamp with time zone,
    id character varying(36) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    product_role character varying(30),
    onboarding_completed boolean DEFAULT false NOT NULL,
    personal_organization_id character varying(36),
    last_active_organization_id character varying(36),
    session_version integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_users_product_role CHECK (((product_role IS NULL) OR ((product_role)::text = ANY ((ARRAY['student'::character varying, 'teacher'::character varying, 'professor'::character varying, 'researcher'::character varying, 'reviewer'::character varying, 'institution'::character varying])::text[])))),
    CONSTRAINT ck_users_session_version CHECK ((session_version >= 0))
);


--
-- Name: aegis_edits aegis_edits_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.aegis_edits
    ADD CONSTRAINT aegis_edits_pkey PRIMARY KEY (id);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: analysis_runs analysis_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analysis_runs
    ADD CONSTRAINT analysis_runs_pkey PRIMARY KEY (id);


--
-- Name: api_keys api_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT api_keys_pkey PRIMARY KEY (id);


--
-- Name: assignments assignments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assignments
    ADD CONSTRAINT assignments_pkey PRIMARY KEY (id);


--
-- Name: audit_logs audit_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_pkey PRIMARY KEY (id);


--
-- Name: authorship_profiles authorship_profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.authorship_profiles
    ADD CONSTRAINT authorship_profiles_pkey PRIMARY KEY (id);


--
-- Name: authorship_signals authorship_signals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.authorship_signals
    ADD CONSTRAINT authorship_signals_pkey PRIMARY KEY (id);


--
-- Name: billing_events billing_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.billing_events
    ADD CONSTRAINT billing_events_pkey PRIMARY KEY (id);


--
-- Name: citation_findings citation_findings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citation_findings
    ADD CONSTRAINT citation_findings_pkey PRIMARY KEY (id);


--
-- Name: citation_references citation_references_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citation_references
    ADD CONSTRAINT citation_references_pkey PRIMARY KEY (id);


--
-- Name: citation_sources citation_sources_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citation_sources
    ADD CONSTRAINT citation_sources_pkey PRIMARY KEY (id);


--
-- Name: citations citations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citations
    ADD CONSTRAINT citations_pkey PRIMARY KEY (id);


--
-- Name: claims claims_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.claims
    ADD CONSTRAINT claims_pkey PRIMARY KEY (id);


--
-- Name: compliance_reports compliance_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.compliance_reports
    ADD CONSTRAINT compliance_reports_pkey PRIMARY KEY (id);


--
-- Name: detection_results detection_results_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.detection_results
    ADD CONSTRAINT detection_results_pkey PRIMARY KEY (id);


--
-- Name: detection_segments detection_segments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.detection_segments
    ADD CONSTRAINT detection_segments_pkey PRIMARY KEY (id);


--
-- Name: document_chunks document_chunks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_chunks
    ADD CONSTRAINT document_chunks_pkey PRIMARY KEY (id);


--
-- Name: document_versions document_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_versions
    ADD CONSTRAINT document_versions_pkey PRIMARY KEY (id);


--
-- Name: documents documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_pkey PRIMARY KEY (id);


--
-- Name: evaluation_datasets evaluation_datasets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evaluation_datasets
    ADD CONSTRAINT evaluation_datasets_pkey PRIMARY KEY (id);


--
-- Name: evaluation_examples evaluation_examples_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evaluation_examples
    ADD CONSTRAINT evaluation_examples_pkey PRIMARY KEY (id);


--
-- Name: evidence_edges evidence_edges_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evidence_edges
    ADD CONSTRAINT evidence_edges_pkey PRIMARY KEY (id);


--
-- Name: evidence_nodes evidence_nodes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evidence_nodes
    ADD CONSTRAINT evidence_nodes_pkey PRIMARY KEY (id);


--
-- Name: integrity_reports integrity_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.integrity_reports
    ADD CONSTRAINT integrity_reports_pkey PRIMARY KEY (id);


--
-- Name: jobs jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT jobs_pkey PRIMARY KEY (id);


--
-- Name: memberships memberships_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memberships
    ADD CONSTRAINT memberships_pkey PRIMARY KEY (id);


--
-- Name: model_registry model_registry_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.model_registry
    ADD CONSTRAINT model_registry_pkey PRIMARY KEY (id);


--
-- Name: organizations organizations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT organizations_pkey PRIMARY KEY (id);


--
-- Name: processed_documents processed_documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.processed_documents
    ADD CONSTRAINT processed_documents_pkey PRIMARY KEY (id);


--
-- Name: provenance_events provenance_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provenance_events
    ADD CONSTRAINT provenance_events_pkey PRIMARY KEY (id);


--
-- Name: provenance_exports provenance_exports_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provenance_exports
    ADD CONSTRAINT provenance_exports_pkey PRIMARY KEY (id);


--
-- Name: provenance_reports provenance_reports_document_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provenance_reports
    ADD CONSTRAINT provenance_reports_document_id_key UNIQUE (document_id);


--
-- Name: provenance_reports provenance_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provenance_reports
    ADD CONSTRAINT provenance_reports_pkey PRIMARY KEY (id);


--
-- Name: refresh_tokens refresh_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refresh_tokens
    ADD CONSTRAINT refresh_tokens_pkey PRIMARY KEY (id);


--
-- Name: similarity_analyses similarity_analyses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.similarity_analyses
    ADD CONSTRAINT similarity_analyses_pkey PRIMARY KEY (id);


--
-- Name: similarity_index_entries similarity_index_entries_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.similarity_index_entries
    ADD CONSTRAINT similarity_index_entries_pkey PRIMARY KEY (id);


--
-- Name: similarity_matches similarity_matches_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.similarity_matches
    ADD CONSTRAINT similarity_matches_pkey PRIMARY KEY (id);


--
-- Name: submissions submissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT submissions_pkey PRIMARY KEY (id);


--
-- Name: detection_results uq_detection_results_document_job; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.detection_results
    ADD CONSTRAINT uq_detection_results_document_job UNIQUE (document_id, job_id);


--
-- Name: detection_segments uq_detection_segments_result_segment; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.detection_segments
    ADD CONSTRAINT uq_detection_segments_result_segment UNIQUE (detection_result_id, segment_type, segment_index);


--
-- Name: document_chunks uq_document_chunks_version_index; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_chunks
    ADD CONSTRAINT uq_document_chunks_version_index UNIQUE (document_id, document_version_id, index_version, chunk_index);


--
-- Name: document_versions uq_document_versions_document_number; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_versions
    ADD CONSTRAINT uq_document_versions_document_number UNIQUE (document_id, version_number);


--
-- Name: document_versions uq_document_versions_operation; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_versions
    ADD CONSTRAINT uq_document_versions_operation UNIQUE (document_id, operation_id);


--
-- Name: documents uq_documents_storage_path; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT uq_documents_storage_path UNIQUE (storage_path);


--
-- Name: evaluation_datasets uq_evaluation_dataset_identity; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evaluation_datasets
    ADD CONSTRAINT uq_evaluation_dataset_identity UNIQUE (dataset_id, version);


--
-- Name: evaluation_examples uq_evaluation_example_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evaluation_examples
    ADD CONSTRAINT uq_evaluation_example_key UNIQUE (dataset_id, example_key);


--
-- Name: evidence_nodes uq_evidence_nodes_node_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evidence_nodes
    ADD CONSTRAINT uq_evidence_nodes_node_id UNIQUE (node_id);


--
-- Name: model_registry uq_model_registry_identity; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.model_registry
    ADD CONSTRAINT uq_model_registry_identity UNIQUE (model_id, model_version);


--
-- Name: processed_documents uq_processed_documents_version; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.processed_documents
    ADD CONSTRAINT uq_processed_documents_version UNIQUE (document_version_id);


--
-- Name: provenance_exports uq_provenance_exports_hash; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provenance_exports
    ADD CONSTRAINT uq_provenance_exports_hash UNIQUE (export_hash);


--
-- Name: similarity_analyses uq_similarity_analysis_version_pipeline; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.similarity_analyses
    ADD CONSTRAINT uq_similarity_analysis_version_pipeline UNIQUE (document_version_id, pipeline_version, run_key);


--
-- Name: similarity_index_entries uq_similarity_index_chunk_term; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.similarity_index_entries
    ADD CONSTRAINT uq_similarity_index_chunk_term UNIQUE (chunk_id, index_version, term_type, term);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: ix_aegis_edits_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_aegis_edits_document_id ON public.aegis_edits USING btree (document_id);


--
-- Name: ix_aegis_edits_document_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_aegis_edits_document_version_id ON public.aegis_edits USING btree (document_version_id);


--
-- Name: ix_aegis_edits_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_aegis_edits_organization_id ON public.aegis_edits USING btree (organization_id);


--
-- Name: ix_aegis_edits_parent_edit_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_aegis_edits_parent_edit_id ON public.aegis_edits USING btree (parent_edit_id);


--
-- Name: ix_aegis_edits_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_aegis_edits_user_id ON public.aegis_edits USING btree (user_id);


--
-- Name: ix_analysis_runs_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_analysis_runs_document_id ON public.analysis_runs USING btree (document_id);


--
-- Name: ix_analysis_runs_document_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_analysis_runs_document_version_id ON public.analysis_runs USING btree (document_version_id);


--
-- Name: ix_analysis_runs_job_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_analysis_runs_job_id ON public.analysis_runs USING btree (job_id);


--
-- Name: ix_analysis_runs_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_analysis_runs_organization_id ON public.analysis_runs USING btree (organization_id);


--
-- Name: ix_api_keys_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_api_keys_organization_id ON public.api_keys USING btree (organization_id);


--
-- Name: ix_api_keys_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_api_keys_user_id ON public.api_keys USING btree (user_id);


--
-- Name: ix_assignments_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_assignments_organization_id ON public.assignments USING btree (organization_id);


--
-- Name: ix_audit_logs_action; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_action ON public.audit_logs USING btree (action);


--
-- Name: ix_audit_logs_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_organization_id ON public.audit_logs USING btree (organization_id);


--
-- Name: ix_audit_logs_request_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_request_id ON public.audit_logs USING btree (request_id);


--
-- Name: ix_audit_logs_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_user_id ON public.audit_logs USING btree (user_id);


--
-- Name: ix_authorship_profiles_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_authorship_profiles_organization_id ON public.authorship_profiles USING btree (organization_id);


--
-- Name: ix_authorship_profiles_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_authorship_profiles_user_id ON public.authorship_profiles USING btree (user_id);


--
-- Name: ix_authorship_signals_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_authorship_signals_document_id ON public.authorship_signals USING btree (document_id);


--
-- Name: ix_authorship_signals_document_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_authorship_signals_document_version_id ON public.authorship_signals USING btree (document_version_id);


--
-- Name: ix_authorship_signals_evidence_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_authorship_signals_evidence_id ON public.authorship_signals USING btree (evidence_id);


--
-- Name: ix_authorship_signals_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_authorship_signals_organization_id ON public.authorship_signals USING btree (organization_id);


--
-- Name: ix_authorship_signals_profile_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_authorship_signals_profile_id ON public.authorship_signals USING btree (profile_id);


--
-- Name: ix_billing_events_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_billing_events_organization_id ON public.billing_events USING btree (organization_id);


--
-- Name: ix_citation_findings_citation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_citation_findings_citation_id ON public.citation_findings USING btree (citation_id);


--
-- Name: ix_citation_findings_claim_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_citation_findings_claim_id ON public.citation_findings USING btree (claim_id);


--
-- Name: ix_citation_findings_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_citation_findings_document_id ON public.citation_findings USING btree (document_id);


--
-- Name: ix_citation_findings_evidence_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_citation_findings_evidence_id ON public.citation_findings USING btree (evidence_id);


--
-- Name: ix_citation_findings_finding_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_citation_findings_finding_type ON public.citation_findings USING btree (finding_type);


--
-- Name: ix_citation_findings_reference_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_citation_findings_reference_id ON public.citation_findings USING btree (reference_id);


--
-- Name: ix_citation_findings_source_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_citation_findings_source_id ON public.citation_findings USING btree (source_id);


--
-- Name: ix_citation_references_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_citation_references_document_id ON public.citation_references USING btree (document_id);


--
-- Name: ix_citation_references_reference_key; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_citation_references_reference_key ON public.citation_references USING btree (reference_key);


--
-- Name: ix_citation_sources_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_citation_sources_document_id ON public.citation_sources USING btree (document_id);


--
-- Name: ix_citation_sources_doi; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_citation_sources_doi ON public.citation_sources USING btree (doi);


--
-- Name: ix_citation_sources_org_key; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_citation_sources_org_key ON public.citation_sources USING btree (organization_id, source_key);


--
-- Name: ix_citations_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_citations_document_id ON public.citations USING btree (document_id);


--
-- Name: ix_citations_document_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_citations_document_version_id ON public.citations USING btree (document_version_id);


--
-- Name: ix_citations_evidence_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_citations_evidence_id ON public.citations USING btree (evidence_id);


--
-- Name: ix_citations_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_citations_organization_id ON public.citations USING btree (organization_id);


--
-- Name: ix_citations_reference_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_citations_reference_id ON public.citations USING btree (reference_id);


--
-- Name: ix_citations_source_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_citations_source_id ON public.citations USING btree (source_id);


--
-- Name: ix_claims_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_claims_document_id ON public.claims USING btree (document_id);


--
-- Name: ix_claims_document_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_claims_document_version_id ON public.claims USING btree (document_version_id);


--
-- Name: ix_claims_evidence_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_claims_evidence_id ON public.claims USING btree (evidence_id);


--
-- Name: ix_claims_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_claims_organization_id ON public.claims USING btree (organization_id);


--
-- Name: ix_compliance_reports_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_compliance_reports_organization_id ON public.compliance_reports USING btree (organization_id);


--
-- Name: ix_detection_results_analysis_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_detection_results_analysis_run_id ON public.detection_results USING btree (analysis_run_id);


--
-- Name: ix_detection_results_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_detection_results_document_id ON public.detection_results USING btree (document_id);


--
-- Name: ix_detection_results_document_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_detection_results_document_version_id ON public.detection_results USING btree (document_version_id);


--
-- Name: ix_detection_results_inference_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_detection_results_inference_id ON public.detection_results USING btree (inference_id);


--
-- Name: ix_detection_results_job_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_detection_results_job_id ON public.detection_results USING btree (job_id);


--
-- Name: ix_detection_results_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_detection_results_organization_id ON public.detection_results USING btree (organization_id);


--
-- Name: ix_detection_segments_detection_result_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_detection_segments_detection_result_id ON public.detection_segments USING btree (detection_result_id);


--
-- Name: ix_detection_segments_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_detection_segments_document_id ON public.detection_segments USING btree (document_id);


--
-- Name: ix_detection_segments_document_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_detection_segments_document_version_id ON public.detection_segments USING btree (document_version_id);


--
-- Name: ix_detection_segments_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_detection_segments_organization_id ON public.detection_segments USING btree (organization_id);


--
-- Name: ix_document_chunks_content_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_chunks_content_hash ON public.document_chunks USING btree (content_hash);


--
-- Name: ix_document_chunks_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_chunks_document_id ON public.document_chunks USING btree (document_id);


--
-- Name: ix_document_chunks_document_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_chunks_document_version_id ON public.document_chunks USING btree (document_version_id);


--
-- Name: ix_document_chunks_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_chunks_organization_id ON public.document_chunks USING btree (organization_id);


--
-- Name: ix_document_versions_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_versions_document_id ON public.document_versions USING btree (document_id);


--
-- Name: ix_document_versions_previous_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_versions_previous_version_id ON public.document_versions USING btree (previous_version_id);


--
-- Name: ix_document_versions_uploaded_by_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_versions_uploaded_by_id ON public.document_versions USING btree (uploaded_by_id);


--
-- Name: ix_documents_assignment_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_documents_assignment_id ON public.documents USING btree (assignment_id);


--
-- Name: ix_documents_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_documents_organization_id ON public.documents USING btree (organization_id);


--
-- Name: ix_documents_owner_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_documents_owner_id ON public.documents USING btree (owner_id);


--
-- Name: ix_documents_sha256_fingerprint; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_documents_sha256_fingerprint ON public.documents USING btree (sha256_fingerprint);


--
-- Name: ix_documents_submission_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_documents_submission_id ON public.documents USING btree (submission_id);


--
-- Name: ix_evaluation_datasets_dataset_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_evaluation_datasets_dataset_id ON public.evaluation_datasets USING btree (dataset_id);


--
-- Name: ix_evaluation_examples_author_key_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_evaluation_examples_author_key_hash ON public.evaluation_examples USING btree (author_key_hash);


--
-- Name: ix_evaluation_examples_dataset_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_evaluation_examples_dataset_id ON public.evaluation_examples USING btree (dataset_id);


--
-- Name: ix_evaluation_examples_document_key_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_evaluation_examples_document_key_hash ON public.evaluation_examples USING btree (document_key_hash);


--
-- Name: ix_evaluation_examples_source_document_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_evaluation_examples_source_document_hash ON public.evaluation_examples USING btree (source_document_hash);


--
-- Name: ix_evaluation_examples_text_sha256; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_evaluation_examples_text_sha256 ON public.evaluation_examples USING btree (text_sha256);


--
-- Name: ix_evidence_edges_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_evidence_edges_document_id ON public.evidence_edges USING btree (document_id);


--
-- Name: ix_evidence_edges_document_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_evidence_edges_document_version_id ON public.evidence_edges USING btree (document_version_id);


--
-- Name: ix_evidence_edges_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_evidence_edges_organization_id ON public.evidence_edges USING btree (organization_id);


--
-- Name: ix_evidence_edges_source_node_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_evidence_edges_source_node_id ON public.evidence_edges USING btree (source_node_id);


--
-- Name: ix_evidence_edges_target_node_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_evidence_edges_target_node_id ON public.evidence_edges USING btree (target_node_id);


--
-- Name: ix_evidence_nodes_canonical_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_evidence_nodes_canonical_type ON public.evidence_nodes USING btree (canonical_type);


--
-- Name: ix_evidence_nodes_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_evidence_nodes_document_id ON public.evidence_nodes USING btree (document_id);


--
-- Name: ix_evidence_nodes_document_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_evidence_nodes_document_version_id ON public.evidence_nodes USING btree (document_version_id);


--
-- Name: ix_evidence_nodes_entity_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_evidence_nodes_entity_id ON public.evidence_nodes USING btree (entity_id);


--
-- Name: ix_evidence_nodes_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_evidence_nodes_organization_id ON public.evidence_nodes USING btree (organization_id);


--
-- Name: ix_integrity_reports_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_integrity_reports_document_id ON public.integrity_reports USING btree (document_id);


--
-- Name: ix_integrity_reports_document_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_integrity_reports_document_version_id ON public.integrity_reports USING btree (document_version_id);


--
-- Name: ix_integrity_reports_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_integrity_reports_organization_id ON public.integrity_reports USING btree (organization_id);


--
-- Name: ix_jobs_celery_task_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jobs_celery_task_id ON public.jobs USING btree (celery_task_id);


--
-- Name: ix_jobs_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jobs_document_id ON public.jobs USING btree (document_id);


--
-- Name: ix_jobs_document_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jobs_document_version_id ON public.jobs USING btree (document_version_id);


--
-- Name: ix_jobs_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_jobs_organization_id ON public.jobs USING btree (organization_id);


--
-- Name: ix_memberships_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_memberships_organization_id ON public.memberships USING btree (organization_id);


--
-- Name: ix_memberships_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_memberships_user_id ON public.memberships USING btree (user_id);


--
-- Name: ix_model_registry_model_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_model_registry_model_id ON public.model_registry USING btree (model_id);


--
-- Name: ix_organizations_slug; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_organizations_slug ON public.organizations USING btree (slug);


--
-- Name: ix_processed_documents_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_processed_documents_document_id ON public.processed_documents USING btree (document_id);


--
-- Name: ix_processed_documents_document_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_processed_documents_document_version_id ON public.processed_documents USING btree (document_version_id);


--
-- Name: ix_processed_documents_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_processed_documents_organization_id ON public.processed_documents USING btree (organization_id);


--
-- Name: ix_provenance_events_analysis_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_provenance_events_analysis_run_id ON public.provenance_events USING btree (analysis_run_id);


--
-- Name: ix_provenance_events_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_provenance_events_document_id ON public.provenance_events USING btree (document_id);


--
-- Name: ix_provenance_events_document_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_provenance_events_document_version_id ON public.provenance_events USING btree (document_version_id);


--
-- Name: ix_provenance_events_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_provenance_events_organization_id ON public.provenance_events USING btree (organization_id);


--
-- Name: ix_provenance_exports_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_provenance_exports_document_id ON public.provenance_exports USING btree (document_id);


--
-- Name: ix_provenance_exports_document_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_provenance_exports_document_version_id ON public.provenance_exports USING btree (document_version_id);


--
-- Name: ix_provenance_exports_exported_by_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_provenance_exports_exported_by_id ON public.provenance_exports USING btree (exported_by_id);


--
-- Name: ix_provenance_exports_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_provenance_exports_organization_id ON public.provenance_exports USING btree (organization_id);


--
-- Name: ix_provenance_reports_document_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_provenance_reports_document_version_id ON public.provenance_reports USING btree (document_version_id);


--
-- Name: ix_provenance_reports_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_provenance_reports_organization_id ON public.provenance_reports USING btree (organization_id);


--
-- Name: ix_refresh_tokens_jti; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_refresh_tokens_jti ON public.refresh_tokens USING btree (jti);


--
-- Name: ix_refresh_tokens_token_family; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_refresh_tokens_token_family ON public.refresh_tokens USING btree (token_family);


--
-- Name: ix_refresh_tokens_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_refresh_tokens_user_id ON public.refresh_tokens USING btree (user_id);


--
-- Name: ix_similarity_analyses_analysis_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_similarity_analyses_analysis_run_id ON public.similarity_analyses USING btree (analysis_run_id);


--
-- Name: ix_similarity_analyses_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_similarity_analyses_document_id ON public.similarity_analyses USING btree (document_id);


--
-- Name: ix_similarity_analyses_document_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_similarity_analyses_document_version_id ON public.similarity_analyses USING btree (document_version_id);


--
-- Name: ix_similarity_analyses_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_similarity_analyses_organization_id ON public.similarity_analyses USING btree (organization_id);


--
-- Name: ix_similarity_chunk_scope; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_similarity_chunk_scope ON public.document_chunks USING btree (organization_id, index_version, index_status);


--
-- Name: ix_similarity_chunks_vector; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_similarity_chunks_vector ON public.document_chunks USING hnsw (embedding_vector public.vector_cosine_ops) WHERE (embedding_vector IS NOT NULL);


--
-- Name: ix_similarity_index_chunk_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_similarity_index_chunk_id ON public.similarity_index_entries USING btree (chunk_id);


--
-- Name: ix_similarity_index_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_similarity_index_document_id ON public.similarity_index_entries USING btree (document_id);


--
-- Name: ix_similarity_index_lookup; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_similarity_index_lookup ON public.similarity_index_entries USING btree (organization_id, index_version, term_type, term);


--
-- Name: ix_similarity_index_org_version_term; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_similarity_index_org_version_term ON public.similarity_index_entries USING btree (organization_id, index_version, term);


--
-- Name: ix_similarity_matches_analysis_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_similarity_matches_analysis_id ON public.similarity_matches USING btree (analysis_id);


--
-- Name: ix_similarity_matches_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_similarity_matches_document_id ON public.similarity_matches USING btree (document_id);


--
-- Name: ix_similarity_matches_document_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_similarity_matches_document_version_id ON public.similarity_matches USING btree (document_version_id);


--
-- Name: ix_similarity_matches_evidence_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_similarity_matches_evidence_id ON public.similarity_matches USING btree (evidence_id);


--
-- Name: ix_similarity_matches_external_source_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_similarity_matches_external_source_id ON public.similarity_matches USING btree (external_source_id);


--
-- Name: ix_similarity_matches_group_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_similarity_matches_group_id ON public.similarity_matches USING btree (group_id);


--
-- Name: ix_similarity_matches_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_similarity_matches_organization_id ON public.similarity_matches USING btree (organization_id);


--
-- Name: ix_similarity_matches_source_document_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_similarity_matches_source_document_version_id ON public.similarity_matches USING btree (source_document_version_id);


--
-- Name: ix_similarity_matches_target_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_similarity_matches_target_document_id ON public.similarity_matches USING btree (target_document_id);


--
-- Name: ix_submissions_assignment_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_submissions_assignment_id ON public.submissions USING btree (assignment_id);


--
-- Name: ix_submissions_student_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_submissions_student_id ON public.submissions USING btree (student_id);


--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);


--
-- Name: aegis_edits aegis_edits_exact_target; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER aegis_edits_exact_target BEFORE INSERT OR UPDATE ON public.aegis_edits FOR EACH ROW EXECUTE FUNCTION app.enforce_analysis_target();


--
-- Name: analysis_runs analysis_runs_exact_target; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER analysis_runs_exact_target BEFORE INSERT OR UPDATE ON public.analysis_runs FOR EACH ROW EXECUTE FUNCTION app.enforce_analysis_target();


--
-- Name: analysis_runs analysis_runs_related_target; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER analysis_runs_related_target BEFORE INSERT OR UPDATE ON public.analysis_runs FOR EACH ROW EXECUTE FUNCTION app.enforce_related_analysis_target('job_id', 'jobs');


--
-- Name: authorship_signals authorship_signals_exact_target; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER authorship_signals_exact_target BEFORE INSERT OR UPDATE ON public.authorship_signals FOR EACH ROW EXECUTE FUNCTION app.enforce_analysis_target();


--
-- Name: citation_findings citation_findings_exact_target; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER citation_findings_exact_target BEFORE INSERT OR UPDATE ON public.citation_findings FOR EACH ROW EXECUTE FUNCTION app.enforce_analysis_target();


--
-- Name: citation_findings citation_findings_related_target; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER citation_findings_related_target BEFORE INSERT OR UPDATE ON public.citation_findings FOR EACH ROW EXECUTE FUNCTION app.enforce_related_analysis_target('claim_id', 'claims', 'citation_id', 'citations', 'reference_id', 'citation_references', 'source_id', 'citation_sources', 'evidence_id', 'evidence_nodes');


--
-- Name: citation_references citation_references_exact_target; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER citation_references_exact_target BEFORE INSERT OR UPDATE ON public.citation_references FOR EACH ROW EXECUTE FUNCTION app.enforce_analysis_target();


--
-- Name: citation_references citation_references_related_target; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER citation_references_related_target BEFORE INSERT OR UPDATE ON public.citation_references FOR EACH ROW EXECUTE FUNCTION app.enforce_related_analysis_target('source_id', 'citation_sources');


--
-- Name: citation_sources citation_sources_exact_target; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER citation_sources_exact_target BEFORE INSERT OR UPDATE ON public.citation_sources FOR EACH ROW EXECUTE FUNCTION app.enforce_analysis_target();


--
-- Name: citations citations_exact_target; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER citations_exact_target BEFORE INSERT OR UPDATE ON public.citations FOR EACH ROW EXECUTE FUNCTION app.enforce_analysis_target();


--
-- Name: citations citations_related_target; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER citations_related_target BEFORE INSERT OR UPDATE ON public.citations FOR EACH ROW EXECUTE FUNCTION app.enforce_related_analysis_target('claim_id', 'claims', 'reference_id', 'citation_references', 'source_id', 'citation_sources', 'evidence_id', 'evidence_nodes');


--
-- Name: claims claims_exact_target; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER claims_exact_target BEFORE INSERT OR UPDATE ON public.claims FOR EACH ROW EXECUTE FUNCTION app.enforce_analysis_target();


--
-- Name: claims claims_related_target; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER claims_related_target BEFORE INSERT OR UPDATE ON public.claims FOR EACH ROW EXECUTE FUNCTION app.enforce_related_analysis_target('evidence_id', 'evidence_nodes');


--
-- Name: detection_results detection_results_exact_target; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER detection_results_exact_target BEFORE INSERT OR UPDATE ON public.detection_results FOR EACH ROW EXECUTE FUNCTION app.enforce_analysis_target();


--
-- Name: detection_results detection_results_related_target; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER detection_results_related_target BEFORE INSERT OR UPDATE ON public.detection_results FOR EACH ROW EXECUTE FUNCTION app.enforce_related_analysis_target('job_id', 'jobs', 'analysis_run_id', 'analysis_runs');


--
-- Name: detection_segments detection_segments_exact_target; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER detection_segments_exact_target BEFORE INSERT OR UPDATE ON public.detection_segments FOR EACH ROW EXECUTE FUNCTION app.enforce_analysis_target();


--
-- Name: detection_segments detection_segments_related_target; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER detection_segments_related_target BEFORE INSERT OR UPDATE ON public.detection_segments FOR EACH ROW EXECUTE FUNCTION app.enforce_related_analysis_target('detection_result_id', 'detection_results');


--
-- Name: document_chunks document_chunks_exact_target; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER document_chunks_exact_target BEFORE INSERT OR UPDATE ON public.document_chunks FOR EACH ROW EXECUTE FUNCTION app.enforce_analysis_target();


--
-- Name: document_versions document_version_operation_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER document_version_operation_immutable BEFORE UPDATE ON public.document_versions FOR EACH ROW EXECUTE FUNCTION app.freeze_document_operation();


--
-- Name: document_versions document_versions_append_only; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER document_versions_append_only BEFORE DELETE OR UPDATE ON public.document_versions FOR EACH ROW EXECUTE FUNCTION app.prevent_document_version_mutation();


--
-- Name: evaluation_datasets evaluation_datasets_immutable_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER evaluation_datasets_immutable_guard BEFORE DELETE OR UPDATE ON public.evaluation_datasets FOR EACH ROW EXECUTE FUNCTION app.prevent_frozen_evaluation_dataset_mutation();


--
-- Name: evaluation_examples evaluation_examples_immutable_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER evaluation_examples_immutable_guard BEFORE INSERT OR DELETE OR UPDATE ON public.evaluation_examples FOR EACH ROW EXECUTE FUNCTION app.prevent_frozen_evaluation_dataset_mutation();


--
-- Name: evidence_edges evidence_edges_exact_target; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER evidence_edges_exact_target BEFORE INSERT OR UPDATE ON public.evidence_edges FOR EACH ROW EXECUTE FUNCTION app.enforce_analysis_target();


--
-- Name: evidence_edges evidence_edges_version_boundary; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER evidence_edges_version_boundary BEFORE INSERT OR UPDATE ON public.evidence_edges FOR EACH ROW EXECUTE FUNCTION app.enforce_edge_target();


--
-- Name: evidence_nodes evidence_nodes_exact_target; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER evidence_nodes_exact_target BEFORE INSERT OR UPDATE ON public.evidence_nodes FOR EACH ROW EXECUTE FUNCTION app.enforce_analysis_target();


--
-- Name: integrity_reports integrity_reports_exact_target; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER integrity_reports_exact_target BEFORE INSERT OR UPDATE ON public.integrity_reports FOR EACH ROW EXECUTE FUNCTION app.enforce_analysis_target();


--
-- Name: jobs jobs_exact_target; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER jobs_exact_target BEFORE INSERT OR UPDATE ON public.jobs FOR EACH ROW EXECUTE FUNCTION app.enforce_analysis_target();


--
-- Name: processed_documents processed_documents_exact_target; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER processed_documents_exact_target BEFORE INSERT OR UPDATE ON public.processed_documents FOR EACH ROW EXECUTE FUNCTION app.enforce_analysis_target();


--
-- Name: processed_documents processed_documents_frozen; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER processed_documents_frozen BEFORE DELETE OR UPDATE ON public.processed_documents FOR EACH ROW EXECUTE FUNCTION app.freeze_processed_document();


--
-- Name: provenance_events provenance_events_append_only; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER provenance_events_append_only BEFORE DELETE OR UPDATE ON public.provenance_events FOR EACH ROW EXECUTE FUNCTION app.prevent_provenance_events_mutation();


--
-- Name: provenance_events provenance_events_exact_target; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER provenance_events_exact_target BEFORE INSERT OR UPDATE ON public.provenance_events FOR EACH ROW EXECUTE FUNCTION app.enforce_analysis_target();


--
-- Name: provenance_exports provenance_exports_append_only; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER provenance_exports_append_only BEFORE DELETE OR UPDATE ON public.provenance_exports FOR EACH ROW EXECUTE FUNCTION app.prevent_provenance_exports_mutation();


--
-- Name: provenance_exports provenance_exports_exact_target; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER provenance_exports_exact_target BEFORE INSERT OR UPDATE ON public.provenance_exports FOR EACH ROW EXECUTE FUNCTION app.enforce_analysis_target();


--
-- Name: provenance_reports provenance_reports_append_only; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER provenance_reports_append_only BEFORE DELETE OR UPDATE ON public.provenance_reports FOR EACH ROW EXECUTE FUNCTION app.prevent_provenance_reports_mutation();


--
-- Name: provenance_reports provenance_reports_exact_target; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER provenance_reports_exact_target BEFORE INSERT OR UPDATE ON public.provenance_reports FOR EACH ROW EXECUTE FUNCTION app.enforce_analysis_target();


--
-- Name: similarity_analyses similarity_analyses_exact_target; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER similarity_analyses_exact_target BEFORE INSERT OR UPDATE ON public.similarity_analyses FOR EACH ROW EXECUTE FUNCTION app.enforce_analysis_target();


--
-- Name: similarity_matches similarity_exact_evidence; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER similarity_exact_evidence BEFORE INSERT OR DELETE OR UPDATE ON public.similarity_matches FOR EACH ROW EXECUTE FUNCTION app.validate_similarity_evidence();


--
-- Name: similarity_index_entries similarity_index_chunk_target; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER similarity_index_chunk_target BEFORE INSERT OR UPDATE ON public.similarity_index_entries FOR EACH ROW EXECUTE FUNCTION app.enforce_related_analysis_target('chunk_id', 'document_chunks');


--
-- Name: similarity_index_entries similarity_index_entries_exact_target; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER similarity_index_entries_exact_target BEFORE INSERT OR UPDATE ON public.similarity_index_entries FOR EACH ROW EXECUTE FUNCTION app.enforce_analysis_target();


--
-- Name: similarity_matches similarity_matches_exact_target; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER similarity_matches_exact_target BEFORE INSERT OR UPDATE ON public.similarity_matches FOR EACH ROW EXECUTE FUNCTION app.enforce_analysis_target();


--
-- Name: similarity_matches similarity_matches_related_target; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER similarity_matches_related_target BEFORE INSERT OR UPDATE ON public.similarity_matches FOR EACH ROW EXECUTE FUNCTION app.enforce_related_analysis_target('analysis_id', 'similarity_analyses', 'evidence_id', 'evidence_nodes');


--
-- Name: similarity_analyses similarity_snapshot_run_target; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER similarity_snapshot_run_target BEFORE INSERT OR UPDATE ON public.similarity_analyses FOR EACH ROW EXECUTE FUNCTION app.enforce_related_analysis_target('analysis_run_id', 'analysis_runs');


--
-- Name: similarity_analyses similarity_snapshots_frozen; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER similarity_snapshots_frozen BEFORE DELETE OR UPDATE ON public.similarity_analyses FOR EACH ROW EXECUTE FUNCTION app.freeze_similarity_snapshot();


--
-- Name: aegis_edits aegis_edits_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.aegis_edits
    ADD CONSTRAINT aegis_edits_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: aegis_edits aegis_edits_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.aegis_edits
    ADD CONSTRAINT aegis_edits_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: analysis_runs analysis_runs_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analysis_runs
    ADD CONSTRAINT analysis_runs_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: analysis_runs analysis_runs_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analysis_runs
    ADD CONSTRAINT analysis_runs_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.jobs(id) ON DELETE SET NULL;


--
-- Name: analysis_runs analysis_runs_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analysis_runs
    ADD CONSTRAINT analysis_runs_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: api_keys api_keys_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT api_keys_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: api_keys api_keys_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT api_keys_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: assignments assignments_created_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assignments
    ADD CONSTRAINT assignments_created_by_id_fkey FOREIGN KEY (created_by_id) REFERENCES public.users(id);


--
-- Name: assignments assignments_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assignments
    ADD CONSTRAINT assignments_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: audit_logs audit_logs_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE SET NULL;


--
-- Name: audit_logs audit_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: authorship_profiles authorship_profiles_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.authorship_profiles
    ADD CONSTRAINT authorship_profiles_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: authorship_signals authorship_signals_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.authorship_signals
    ADD CONSTRAINT authorship_signals_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: authorship_signals authorship_signals_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.authorship_signals
    ADD CONSTRAINT authorship_signals_profile_id_fkey FOREIGN KEY (profile_id) REFERENCES public.authorship_profiles(id) ON DELETE CASCADE;


--
-- Name: billing_events billing_events_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.billing_events
    ADD CONSTRAINT billing_events_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: citations citations_claim_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citations
    ADD CONSTRAINT citations_claim_id_fkey FOREIGN KEY (claim_id) REFERENCES public.claims(id) ON DELETE SET NULL;


--
-- Name: citations citations_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citations
    ADD CONSTRAINT citations_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: claims claims_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.claims
    ADD CONSTRAINT claims_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: compliance_reports compliance_reports_generated_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.compliance_reports
    ADD CONSTRAINT compliance_reports_generated_by_id_fkey FOREIGN KEY (generated_by_id) REFERENCES public.users(id);


--
-- Name: compliance_reports compliance_reports_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.compliance_reports
    ADD CONSTRAINT compliance_reports_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: detection_results detection_results_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.detection_results
    ADD CONSTRAINT detection_results_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: detection_results detection_results_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.detection_results
    ADD CONSTRAINT detection_results_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.jobs(id) ON DELETE CASCADE;


--
-- Name: detection_segments detection_segments_detection_result_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.detection_segments
    ADD CONSTRAINT detection_segments_detection_result_id_fkey FOREIGN KEY (detection_result_id) REFERENCES public.detection_results(id) ON DELETE CASCADE;


--
-- Name: document_chunks document_chunks_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_chunks
    ADD CONSTRAINT document_chunks_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: document_versions document_versions_created_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_versions
    ADD CONSTRAINT document_versions_created_by_id_fkey FOREIGN KEY (created_by_id) REFERENCES public.users(id);


--
-- Name: document_versions document_versions_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_versions
    ADD CONSTRAINT document_versions_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: documents documents_assignment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_assignment_id_fkey FOREIGN KEY (assignment_id) REFERENCES public.assignments(id) ON DELETE SET NULL;


--
-- Name: documents documents_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: documents documents_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: documents documents_submission_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_submission_id_fkey FOREIGN KEY (submission_id) REFERENCES public.submissions(id) ON DELETE SET NULL;


--
-- Name: evaluation_examples evaluation_examples_dataset_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evaluation_examples
    ADD CONSTRAINT evaluation_examples_dataset_id_fkey FOREIGN KEY (dataset_id) REFERENCES public.evaluation_datasets(id) ON DELETE CASCADE;


--
-- Name: evidence_nodes evidence_nodes_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evidence_nodes
    ADD CONSTRAINT evidence_nodes_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: aegis_edits fk_aegis_edits_document_version; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.aegis_edits
    ADD CONSTRAINT fk_aegis_edits_document_version FOREIGN KEY (document_version_id) REFERENCES public.document_versions(id) ON DELETE CASCADE;


--
-- Name: aegis_edits fk_aegis_edits_organization; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.aegis_edits
    ADD CONSTRAINT fk_aegis_edits_organization FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: aegis_edits fk_aegis_edits_parent; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.aegis_edits
    ADD CONSTRAINT fk_aegis_edits_parent FOREIGN KEY (parent_edit_id) REFERENCES public.aegis_edits(id) ON DELETE SET NULL;


--
-- Name: analysis_runs fk_analysis_runs_document_version_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analysis_runs
    ADD CONSTRAINT fk_analysis_runs_document_version_id FOREIGN KEY (document_version_id) REFERENCES public.document_versions(id) ON DELETE RESTRICT;


--
-- Name: authorship_profiles fk_authorship_profiles_organization; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.authorship_profiles
    ADD CONSTRAINT fk_authorship_profiles_organization FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: authorship_signals fk_authorship_signals_document_version; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.authorship_signals
    ADD CONSTRAINT fk_authorship_signals_document_version FOREIGN KEY (document_version_id) REFERENCES public.document_versions(id) ON DELETE RESTRICT;


--
-- Name: authorship_signals fk_authorship_signals_evidence; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.authorship_signals
    ADD CONSTRAINT fk_authorship_signals_evidence FOREIGN KEY (evidence_id) REFERENCES public.evidence_nodes(id) ON DELETE SET NULL;


--
-- Name: authorship_signals fk_authorship_signals_organization; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.authorship_signals
    ADD CONSTRAINT fk_authorship_signals_organization FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: citation_findings fk_citation_findings_citation; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citation_findings
    ADD CONSTRAINT fk_citation_findings_citation FOREIGN KEY (citation_id) REFERENCES public.citations(id) ON DELETE CASCADE;


--
-- Name: citation_findings fk_citation_findings_claim; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citation_findings
    ADD CONSTRAINT fk_citation_findings_claim FOREIGN KEY (claim_id) REFERENCES public.claims(id) ON DELETE CASCADE;


--
-- Name: citation_findings fk_citation_findings_document; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citation_findings
    ADD CONSTRAINT fk_citation_findings_document FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: citation_findings fk_citation_findings_document_version; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citation_findings
    ADD CONSTRAINT fk_citation_findings_document_version FOREIGN KEY (document_version_id) REFERENCES public.document_versions(id) ON DELETE RESTRICT;


--
-- Name: citation_findings fk_citation_findings_evidence; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citation_findings
    ADD CONSTRAINT fk_citation_findings_evidence FOREIGN KEY (evidence_id) REFERENCES public.evidence_nodes(id) ON DELETE SET NULL;


--
-- Name: citation_findings fk_citation_findings_organization; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citation_findings
    ADD CONSTRAINT fk_citation_findings_organization FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: citation_findings fk_citation_findings_reference; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citation_findings
    ADD CONSTRAINT fk_citation_findings_reference FOREIGN KEY (reference_id) REFERENCES public.citation_references(id) ON DELETE SET NULL;


--
-- Name: citation_findings fk_citation_findings_source; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citation_findings
    ADD CONSTRAINT fk_citation_findings_source FOREIGN KEY (source_id) REFERENCES public.citation_sources(id) ON DELETE SET NULL;


--
-- Name: citation_references fk_citation_references_document; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citation_references
    ADD CONSTRAINT fk_citation_references_document FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: citation_references fk_citation_references_document_version; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citation_references
    ADD CONSTRAINT fk_citation_references_document_version FOREIGN KEY (document_version_id) REFERENCES public.document_versions(id) ON DELETE RESTRICT;


--
-- Name: citation_references fk_citation_references_organization; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citation_references
    ADD CONSTRAINT fk_citation_references_organization FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: citation_references fk_citation_references_source; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citation_references
    ADD CONSTRAINT fk_citation_references_source FOREIGN KEY (source_id) REFERENCES public.citation_sources(id) ON DELETE SET NULL;


--
-- Name: citation_sources fk_citation_sources_document_id_core; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citation_sources
    ADD CONSTRAINT fk_citation_sources_document_id_core FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE RESTRICT;


--
-- Name: citation_sources fk_citation_sources_document_version; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citation_sources
    ADD CONSTRAINT fk_citation_sources_document_version FOREIGN KEY (document_version_id) REFERENCES public.document_versions(id) ON DELETE RESTRICT;


--
-- Name: citation_sources fk_citation_sources_organization; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citation_sources
    ADD CONSTRAINT fk_citation_sources_organization FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: citations fk_citations_document_version; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citations
    ADD CONSTRAINT fk_citations_document_version FOREIGN KEY (document_version_id) REFERENCES public.document_versions(id) ON DELETE RESTRICT;


--
-- Name: citations fk_citations_evidence; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citations
    ADD CONSTRAINT fk_citations_evidence FOREIGN KEY (evidence_id) REFERENCES public.evidence_nodes(id) ON DELETE SET NULL;


--
-- Name: citations fk_citations_organization; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citations
    ADD CONSTRAINT fk_citations_organization FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: citations fk_citations_reference; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citations
    ADD CONSTRAINT fk_citations_reference FOREIGN KEY (reference_id) REFERENCES public.citation_references(id) ON DELETE SET NULL;


--
-- Name: citations fk_citations_source; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citations
    ADD CONSTRAINT fk_citations_source FOREIGN KEY (source_id) REFERENCES public.citation_sources(id) ON DELETE SET NULL;


--
-- Name: claims fk_claims_document_version; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.claims
    ADD CONSTRAINT fk_claims_document_version FOREIGN KEY (document_version_id) REFERENCES public.document_versions(id) ON DELETE RESTRICT;


--
-- Name: claims fk_claims_evidence; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.claims
    ADD CONSTRAINT fk_claims_evidence FOREIGN KEY (evidence_id) REFERENCES public.evidence_nodes(id) ON DELETE SET NULL;


--
-- Name: claims fk_claims_organization; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.claims
    ADD CONSTRAINT fk_claims_organization FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: detection_results fk_detection_results_analysis_run; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.detection_results
    ADD CONSTRAINT fk_detection_results_analysis_run FOREIGN KEY (analysis_run_id) REFERENCES public.analysis_runs(id) ON DELETE SET NULL;


--
-- Name: detection_results fk_detection_results_document_version; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.detection_results
    ADD CONSTRAINT fk_detection_results_document_version FOREIGN KEY (document_version_id) REFERENCES public.document_versions(id) ON DELETE RESTRICT;


--
-- Name: detection_results fk_detection_results_organization; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.detection_results
    ADD CONSTRAINT fk_detection_results_organization FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: detection_segments fk_detection_segments_document_id_core; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.detection_segments
    ADD CONSTRAINT fk_detection_segments_document_id_core FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE RESTRICT;


--
-- Name: detection_segments fk_detection_segments_document_version_id_core; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.detection_segments
    ADD CONSTRAINT fk_detection_segments_document_version_id_core FOREIGN KEY (document_version_id) REFERENCES public.document_versions(id) ON DELETE RESTRICT;


--
-- Name: detection_segments fk_detection_segments_organization_id_core; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.detection_segments
    ADD CONSTRAINT fk_detection_segments_organization_id_core FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: document_chunks fk_document_chunks_document_version; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_chunks
    ADD CONSTRAINT fk_document_chunks_document_version FOREIGN KEY (document_version_id) REFERENCES public.document_versions(id) ON DELETE RESTRICT;


--
-- Name: document_chunks fk_document_chunks_organization; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_chunks
    ADD CONSTRAINT fk_document_chunks_organization FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: document_versions fk_document_versions_previous; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_versions
    ADD CONSTRAINT fk_document_versions_previous FOREIGN KEY (previous_version_id) REFERENCES public.document_versions(id) ON DELETE SET NULL;


--
-- Name: document_versions fk_document_versions_uploaded_by; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_versions
    ADD CONSTRAINT fk_document_versions_uploaded_by FOREIGN KEY (uploaded_by_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: evidence_edges fk_evidence_edges_document_id_core; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evidence_edges
    ADD CONSTRAINT fk_evidence_edges_document_id_core FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE RESTRICT;


--
-- Name: evidence_edges fk_evidence_edges_document_version_id_core; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evidence_edges
    ADD CONSTRAINT fk_evidence_edges_document_version_id_core FOREIGN KEY (document_version_id) REFERENCES public.document_versions(id) ON DELETE RESTRICT;


--
-- Name: evidence_edges fk_evidence_edges_organization; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evidence_edges
    ADD CONSTRAINT fk_evidence_edges_organization FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: evidence_edges fk_evidence_edges_source_node; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evidence_edges
    ADD CONSTRAINT fk_evidence_edges_source_node FOREIGN KEY (source_node_id) REFERENCES public.evidence_nodes(node_id) ON DELETE CASCADE;


--
-- Name: evidence_edges fk_evidence_edges_target_node; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evidence_edges
    ADD CONSTRAINT fk_evidence_edges_target_node FOREIGN KEY (target_node_id) REFERENCES public.evidence_nodes(node_id) ON DELETE CASCADE;


--
-- Name: evidence_nodes fk_evidence_nodes_document_version; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evidence_nodes
    ADD CONSTRAINT fk_evidence_nodes_document_version FOREIGN KEY (document_version_id) REFERENCES public.document_versions(id) ON DELETE RESTRICT;


--
-- Name: evidence_nodes fk_evidence_nodes_organization; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evidence_nodes
    ADD CONSTRAINT fk_evidence_nodes_organization FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: integrity_reports fk_integrity_reports_document_version; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.integrity_reports
    ADD CONSTRAINT fk_integrity_reports_document_version FOREIGN KEY (document_version_id) REFERENCES public.document_versions(id) ON DELETE RESTRICT;


--
-- Name: integrity_reports fk_integrity_reports_organization; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.integrity_reports
    ADD CONSTRAINT fk_integrity_reports_organization FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: jobs fk_jobs_document_version_id_core; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT fk_jobs_document_version_id_core FOREIGN KEY (document_version_id) REFERENCES public.document_versions(id) ON DELETE RESTRICT;


--
-- Name: processed_documents fk_processed_documents_document_version; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.processed_documents
    ADD CONSTRAINT fk_processed_documents_document_version FOREIGN KEY (document_version_id) REFERENCES public.document_versions(id) ON DELETE RESTRICT;


--
-- Name: processed_documents fk_processed_documents_organization; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.processed_documents
    ADD CONSTRAINT fk_processed_documents_organization FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: provenance_events fk_provenance_events_analysis_run; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provenance_events
    ADD CONSTRAINT fk_provenance_events_analysis_run FOREIGN KEY (analysis_run_id) REFERENCES public.analysis_runs(id) ON DELETE SET NULL;


--
-- Name: provenance_events fk_provenance_events_document_version; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provenance_events
    ADD CONSTRAINT fk_provenance_events_document_version FOREIGN KEY (document_version_id) REFERENCES public.document_versions(id) ON DELETE RESTRICT;


--
-- Name: provenance_events fk_provenance_events_organization; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provenance_events
    ADD CONSTRAINT fk_provenance_events_organization FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: provenance_reports fk_provenance_reports_document_version; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provenance_reports
    ADD CONSTRAINT fk_provenance_reports_document_version FOREIGN KEY (document_version_id) REFERENCES public.document_versions(id) ON DELETE RESTRICT;


--
-- Name: provenance_reports fk_provenance_reports_organization; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provenance_reports
    ADD CONSTRAINT fk_provenance_reports_organization FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: similarity_matches fk_similarity_analysis; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.similarity_matches
    ADD CONSTRAINT fk_similarity_analysis FOREIGN KEY (analysis_id) REFERENCES public.similarity_analyses(id) ON DELETE CASCADE;


--
-- Name: similarity_index_entries fk_similarity_index_chunk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.similarity_index_entries
    ADD CONSTRAINT fk_similarity_index_chunk FOREIGN KEY (chunk_id) REFERENCES public.document_chunks(id) ON DELETE CASCADE;


--
-- Name: similarity_index_entries fk_similarity_index_document; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.similarity_index_entries
    ADD CONSTRAINT fk_similarity_index_document FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: similarity_index_entries fk_similarity_index_document_version; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.similarity_index_entries
    ADD CONSTRAINT fk_similarity_index_document_version FOREIGN KEY (document_version_id) REFERENCES public.document_versions(id) ON DELETE RESTRICT;


--
-- Name: similarity_index_entries fk_similarity_index_organization; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.similarity_index_entries
    ADD CONSTRAINT fk_similarity_index_organization FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: similarity_matches fk_similarity_matches_document_version; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.similarity_matches
    ADD CONSTRAINT fk_similarity_matches_document_version FOREIGN KEY (document_version_id) REFERENCES public.document_versions(id) ON DELETE RESTRICT;


--
-- Name: similarity_matches fk_similarity_matches_evidence; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.similarity_matches
    ADD CONSTRAINT fk_similarity_matches_evidence FOREIGN KEY (evidence_id) REFERENCES public.evidence_nodes(id) ON DELETE SET NULL;


--
-- Name: similarity_matches fk_similarity_matches_organization; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.similarity_matches
    ADD CONSTRAINT fk_similarity_matches_organization FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: similarity_matches fk_similarity_matches_target_document; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.similarity_matches
    ADD CONSTRAINT fk_similarity_matches_target_document FOREIGN KEY (target_document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: similarity_analyses fk_similarity_snapshot_run; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.similarity_analyses
    ADD CONSTRAINT fk_similarity_snapshot_run FOREIGN KEY (analysis_run_id) REFERENCES public.analysis_runs(id) ON DELETE RESTRICT;


--
-- Name: similarity_matches fk_similarity_source_version; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.similarity_matches
    ADD CONSTRAINT fk_similarity_source_version FOREIGN KEY (source_document_version_id) REFERENCES public.document_versions(id) ON DELETE RESTRICT;


--
-- Name: users fk_users_last_active_organization_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT fk_users_last_active_organization_id FOREIGN KEY (last_active_organization_id) REFERENCES public.organizations(id) ON DELETE SET NULL;


--
-- Name: users fk_users_personal_organization_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT fk_users_personal_organization_id FOREIGN KEY (personal_organization_id) REFERENCES public.organizations(id) ON DELETE SET NULL;


--
-- Name: integrity_reports integrity_reports_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.integrity_reports
    ADD CONSTRAINT integrity_reports_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: jobs jobs_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT jobs_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE SET NULL;


--
-- Name: jobs jobs_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT jobs_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: memberships memberships_invited_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memberships
    ADD CONSTRAINT memberships_invited_by_id_fkey FOREIGN KEY (invited_by_id) REFERENCES public.users(id);


--
-- Name: memberships memberships_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memberships
    ADD CONSTRAINT memberships_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: memberships memberships_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memberships
    ADD CONSTRAINT memberships_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: processed_documents processed_documents_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.processed_documents
    ADD CONSTRAINT processed_documents_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: provenance_events provenance_events_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provenance_events
    ADD CONSTRAINT provenance_events_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: provenance_events provenance_events_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provenance_events
    ADD CONSTRAINT provenance_events_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: provenance_exports provenance_exports_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provenance_exports
    ADD CONSTRAINT provenance_exports_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: provenance_exports provenance_exports_document_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provenance_exports
    ADD CONSTRAINT provenance_exports_document_version_id_fkey FOREIGN KEY (document_version_id) REFERENCES public.document_versions(id) ON DELETE RESTRICT;


--
-- Name: provenance_exports provenance_exports_exported_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provenance_exports
    ADD CONSTRAINT provenance_exports_exported_by_id_fkey FOREIGN KEY (exported_by_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- Name: provenance_exports provenance_exports_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provenance_exports
    ADD CONSTRAINT provenance_exports_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: provenance_reports provenance_reports_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provenance_reports
    ADD CONSTRAINT provenance_reports_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: provenance_reports provenance_reports_signed_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provenance_reports
    ADD CONSTRAINT provenance_reports_signed_by_id_fkey FOREIGN KEY (signed_by_id) REFERENCES public.users(id);


--
-- Name: refresh_tokens refresh_tokens_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refresh_tokens
    ADD CONSTRAINT refresh_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: similarity_analyses similarity_analyses_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.similarity_analyses
    ADD CONSTRAINT similarity_analyses_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: similarity_analyses similarity_analyses_document_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.similarity_analyses
    ADD CONSTRAINT similarity_analyses_document_version_id_fkey FOREIGN KEY (document_version_id) REFERENCES public.document_versions(id) ON DELETE RESTRICT;


--
-- Name: similarity_analyses similarity_analyses_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.similarity_analyses
    ADD CONSTRAINT similarity_analyses_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: similarity_matches similarity_matches_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.similarity_matches
    ADD CONSTRAINT similarity_matches_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: similarity_matches similarity_matches_source_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.similarity_matches
    ADD CONSTRAINT similarity_matches_source_document_id_fkey FOREIGN KEY (source_document_id) REFERENCES public.documents(id) ON DELETE SET NULL;


--
-- Name: submissions submissions_assignment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT submissions_assignment_id_fkey FOREIGN KEY (assignment_id) REFERENCES public.assignments(id) ON DELETE CASCADE;


--
-- Name: submissions submissions_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT submissions_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE SET NULL;


--
-- Name: submissions submissions_graded_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT submissions_graded_by_id_fkey FOREIGN KEY (graded_by_id) REFERENCES public.users(id);


--
-- Name: submissions submissions_student_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT submissions_student_id_fkey FOREIGN KEY (student_id) REFERENCES public.users(id);


--
-- Name: aegis_edits; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.aegis_edits ENABLE ROW LEVEL SECURITY;

--
-- Name: aegis_edits aegis_edits_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY aegis_edits_tenant_isolation ON public.aegis_edits USING ((EXISTS ( SELECT 1
   FROM public.documents
  WHERE (((documents.id)::text = (aegis_edits.document_id)::text) AND ((documents.organization_id)::text = app.current_organization_id()))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM public.documents
  WHERE (((documents.id)::text = (aegis_edits.document_id)::text) AND ((documents.organization_id)::text = app.current_organization_id())))));


--
-- Name: analysis_runs; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.analysis_runs ENABLE ROW LEVEL SECURITY;

--
-- Name: analysis_runs analysis_runs_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY analysis_runs_tenant_isolation ON public.analysis_runs USING (((organization_id)::text = app.current_organization_id())) WITH CHECK (((organization_id)::text = app.current_organization_id()));


--
-- Name: api_keys; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.api_keys ENABLE ROW LEVEL SECURITY;

--
-- Name: api_keys api_keys_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY api_keys_tenant_isolation ON public.api_keys USING (((organization_id)::text = app.current_organization_id())) WITH CHECK (((organization_id)::text = app.current_organization_id()));


--
-- Name: assignments; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.assignments ENABLE ROW LEVEL SECURITY;

--
-- Name: assignments assignments_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY assignments_tenant_isolation ON public.assignments USING (((organization_id)::text = app.current_organization_id())) WITH CHECK (((organization_id)::text = app.current_organization_id()));


--
-- Name: audit_logs; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;

--
-- Name: audit_logs audit_logs_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY audit_logs_tenant_isolation ON public.audit_logs USING ((((organization_id)::text = app.current_organization_id()) OR ((organization_id IS NULL) AND ((user_id)::text = app.current_user_id())))) WITH CHECK ((((organization_id)::text = app.current_organization_id()) OR ((organization_id IS NULL) AND ((user_id)::text = app.current_user_id()))));


--
-- Name: authorship_profiles; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.authorship_profiles ENABLE ROW LEVEL SECURITY;

--
-- Name: authorship_profiles authorship_profiles_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY authorship_profiles_tenant_isolation ON public.authorship_profiles USING (((organization_id)::text = app.current_organization_id())) WITH CHECK (((organization_id)::text = app.current_organization_id()));


--
-- Name: authorship_signals; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.authorship_signals ENABLE ROW LEVEL SECURITY;

--
-- Name: authorship_signals authorship_signals_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY authorship_signals_tenant_isolation ON public.authorship_signals USING ((EXISTS ( SELECT 1
   FROM public.documents
  WHERE (((documents.id)::text = (authorship_signals.document_id)::text) AND ((documents.organization_id)::text = app.current_organization_id()))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM public.documents
  WHERE (((documents.id)::text = (authorship_signals.document_id)::text) AND ((documents.organization_id)::text = app.current_organization_id())))));


--
-- Name: billing_events; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.billing_events ENABLE ROW LEVEL SECURITY;

--
-- Name: billing_events billing_events_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY billing_events_tenant_isolation ON public.billing_events USING (((organization_id)::text = app.current_organization_id())) WITH CHECK (((organization_id)::text = app.current_organization_id()));


--
-- Name: citation_findings; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.citation_findings ENABLE ROW LEVEL SECURITY;

--
-- Name: citation_findings citation_findings_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY citation_findings_tenant_isolation ON public.citation_findings USING (((organization_id)::text = app.current_organization_id())) WITH CHECK (((organization_id)::text = app.current_organization_id()));


--
-- Name: citation_references; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.citation_references ENABLE ROW LEVEL SECURITY;

--
-- Name: citation_references citation_references_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY citation_references_tenant_isolation ON public.citation_references USING (((organization_id)::text = app.current_organization_id())) WITH CHECK (((organization_id)::text = app.current_organization_id()));


--
-- Name: citation_sources; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.citation_sources ENABLE ROW LEVEL SECURITY;

--
-- Name: citation_sources citation_sources_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY citation_sources_tenant_isolation ON public.citation_sources USING (((organization_id)::text = app.current_organization_id())) WITH CHECK (((organization_id)::text = app.current_organization_id()));


--
-- Name: citations; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.citations ENABLE ROW LEVEL SECURITY;

--
-- Name: citations citations_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY citations_tenant_isolation ON public.citations USING ((EXISTS ( SELECT 1
   FROM public.documents
  WHERE (((documents.id)::text = (citations.document_id)::text) AND ((documents.organization_id)::text = app.current_organization_id()))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM public.documents
  WHERE (((documents.id)::text = (citations.document_id)::text) AND ((documents.organization_id)::text = app.current_organization_id())))));


--
-- Name: claims; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.claims ENABLE ROW LEVEL SECURITY;

--
-- Name: claims claims_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY claims_tenant_isolation ON public.claims USING ((EXISTS ( SELECT 1
   FROM public.documents
  WHERE (((documents.id)::text = (claims.document_id)::text) AND ((documents.organization_id)::text = app.current_organization_id()))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM public.documents
  WHERE (((documents.id)::text = (claims.document_id)::text) AND ((documents.organization_id)::text = app.current_organization_id())))));


--
-- Name: compliance_reports; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.compliance_reports ENABLE ROW LEVEL SECURITY;

--
-- Name: compliance_reports compliance_reports_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY compliance_reports_tenant_isolation ON public.compliance_reports USING (((organization_id)::text = app.current_organization_id())) WITH CHECK (((organization_id)::text = app.current_organization_id()));


--
-- Name: detection_results; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.detection_results ENABLE ROW LEVEL SECURITY;

--
-- Name: detection_results detection_results_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY detection_results_tenant_isolation ON public.detection_results USING ((EXISTS ( SELECT 1
   FROM public.documents
  WHERE (((documents.id)::text = (detection_results.document_id)::text) AND ((documents.organization_id)::text = app.current_organization_id()))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM public.documents
  WHERE (((documents.id)::text = (detection_results.document_id)::text) AND ((documents.organization_id)::text = app.current_organization_id())))));


--
-- Name: detection_segments; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.detection_segments ENABLE ROW LEVEL SECURITY;

--
-- Name: detection_segments detection_segments_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY detection_segments_tenant_isolation ON public.detection_segments USING ((EXISTS ( SELECT 1
   FROM (public.detection_results
     JOIN public.documents ON (((documents.id)::text = (detection_results.document_id)::text)))
  WHERE (((detection_results.id)::text = (detection_segments.detection_result_id)::text) AND ((documents.organization_id)::text = app.current_organization_id()))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM (public.detection_results
     JOIN public.documents ON (((documents.id)::text = (detection_results.document_id)::text)))
  WHERE (((detection_results.id)::text = (detection_segments.detection_result_id)::text) AND ((documents.organization_id)::text = app.current_organization_id())))));


--
-- Name: document_chunks; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.document_chunks ENABLE ROW LEVEL SECURITY;

--
-- Name: document_chunks document_chunks_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY document_chunks_tenant_isolation ON public.document_chunks USING ((EXISTS ( SELECT 1
   FROM public.documents
  WHERE (((documents.id)::text = (document_chunks.document_id)::text) AND ((documents.organization_id)::text = app.current_organization_id()))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM public.documents
  WHERE (((documents.id)::text = (document_chunks.document_id)::text) AND ((documents.organization_id)::text = app.current_organization_id())))));


--
-- Name: document_versions; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.document_versions ENABLE ROW LEVEL SECURITY;

--
-- Name: document_versions document_versions_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY document_versions_tenant_isolation ON public.document_versions USING ((EXISTS ( SELECT 1
   FROM public.documents
  WHERE (((documents.id)::text = (document_versions.document_id)::text) AND ((documents.organization_id)::text = app.current_organization_id()))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM public.documents
  WHERE (((documents.id)::text = (document_versions.document_id)::text) AND ((documents.organization_id)::text = app.current_organization_id())))));


--
-- Name: documents; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;

--
-- Name: documents documents_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY documents_tenant_isolation ON public.documents USING (((organization_id)::text = app.current_organization_id())) WITH CHECK (((organization_id)::text = app.current_organization_id()));


--
-- Name: evidence_edges; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.evidence_edges ENABLE ROW LEVEL SECURITY;

--
-- Name: evidence_edges evidence_edges_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY evidence_edges_tenant_isolation ON public.evidence_edges USING (((organization_id)::text = app.current_organization_id())) WITH CHECK (((organization_id)::text = app.current_organization_id()));


--
-- Name: evidence_nodes; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.evidence_nodes ENABLE ROW LEVEL SECURITY;

--
-- Name: evidence_nodes evidence_nodes_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY evidence_nodes_tenant_isolation ON public.evidence_nodes USING ((EXISTS ( SELECT 1
   FROM public.documents
  WHERE (((documents.id)::text = (evidence_nodes.document_id)::text) AND ((documents.organization_id)::text = app.current_organization_id()))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM public.documents
  WHERE (((documents.id)::text = (evidence_nodes.document_id)::text) AND ((documents.organization_id)::text = app.current_organization_id())))));


--
-- Name: integrity_reports; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.integrity_reports ENABLE ROW LEVEL SECURITY;

--
-- Name: integrity_reports integrity_reports_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY integrity_reports_tenant_isolation ON public.integrity_reports USING ((EXISTS ( SELECT 1
   FROM public.documents
  WHERE (((documents.id)::text = (integrity_reports.document_id)::text) AND ((documents.organization_id)::text = app.current_organization_id()))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM public.documents
  WHERE (((documents.id)::text = (integrity_reports.document_id)::text) AND ((documents.organization_id)::text = app.current_organization_id())))));


--
-- Name: jobs; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.jobs ENABLE ROW LEVEL SECURITY;

--
-- Name: jobs jobs_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY jobs_tenant_isolation ON public.jobs USING (((organization_id)::text = app.current_organization_id())) WITH CHECK (((organization_id)::text = app.current_organization_id()));


--
-- Name: processed_documents; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.processed_documents ENABLE ROW LEVEL SECURITY;

--
-- Name: processed_documents processed_documents_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY processed_documents_tenant_isolation ON public.processed_documents USING ((EXISTS ( SELECT 1
   FROM public.documents
  WHERE (((documents.id)::text = (processed_documents.document_id)::text) AND ((documents.organization_id)::text = app.current_organization_id()))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM public.documents
  WHERE (((documents.id)::text = (processed_documents.document_id)::text) AND ((documents.organization_id)::text = app.current_organization_id())))));


--
-- Name: provenance_events; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.provenance_events ENABLE ROW LEVEL SECURITY;

--
-- Name: provenance_events provenance_events_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY provenance_events_tenant_isolation ON public.provenance_events USING ((EXISTS ( SELECT 1
   FROM public.documents
  WHERE (((documents.id)::text = (provenance_events.document_id)::text) AND ((documents.organization_id)::text = app.current_organization_id()))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM public.documents
  WHERE (((documents.id)::text = (provenance_events.document_id)::text) AND ((documents.organization_id)::text = app.current_organization_id())))));


--
-- Name: provenance_exports; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.provenance_exports ENABLE ROW LEVEL SECURITY;

--
-- Name: provenance_exports provenance_exports_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY provenance_exports_tenant_isolation ON public.provenance_exports USING (((organization_id)::text = app.current_organization_id())) WITH CHECK (((organization_id)::text = app.current_organization_id()));


--
-- Name: provenance_reports; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.provenance_reports ENABLE ROW LEVEL SECURITY;

--
-- Name: provenance_reports provenance_reports_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY provenance_reports_tenant_isolation ON public.provenance_reports USING ((EXISTS ( SELECT 1
   FROM public.documents
  WHERE (((documents.id)::text = (provenance_reports.document_id)::text) AND ((documents.organization_id)::text = app.current_organization_id()))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM public.documents
  WHERE (((documents.id)::text = (provenance_reports.document_id)::text) AND ((documents.organization_id)::text = app.current_organization_id())))));


--
-- Name: similarity_analyses; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.similarity_analyses ENABLE ROW LEVEL SECURITY;

--
-- Name: similarity_analyses similarity_analyses_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY similarity_analyses_tenant_isolation ON public.similarity_analyses USING (((organization_id)::text = app.current_organization_id())) WITH CHECK (((organization_id)::text = app.current_organization_id()));


--
-- Name: similarity_index_entries; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.similarity_index_entries ENABLE ROW LEVEL SECURITY;

--
-- Name: similarity_index_entries similarity_index_entries_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY similarity_index_entries_tenant_isolation ON public.similarity_index_entries USING (((organization_id)::text = app.current_organization_id())) WITH CHECK (((organization_id)::text = app.current_organization_id()));


--
-- Name: similarity_matches; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.similarity_matches ENABLE ROW LEVEL SECURITY;

--
-- Name: similarity_matches similarity_matches_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY similarity_matches_tenant_isolation ON public.similarity_matches USING ((EXISTS ( SELECT 1
   FROM public.documents
  WHERE (((documents.id)::text = (similarity_matches.document_id)::text) AND ((documents.organization_id)::text = app.current_organization_id()))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM public.documents
  WHERE (((documents.id)::text = (similarity_matches.document_id)::text) AND ((documents.organization_id)::text = app.current_organization_id())))));


--
-- Name: submissions; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.submissions ENABLE ROW LEVEL SECURITY;

--
-- Name: submissions submissions_tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY submissions_tenant_isolation ON public.submissions USING ((EXISTS ( SELECT 1
   FROM public.assignments
  WHERE (((assignments.id)::text = (submissions.assignment_id)::text) AND ((assignments.organization_id)::text = app.current_organization_id()))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM public.assignments
  WHERE (((assignments.id)::text = (submissions.assignment_id)::text) AND ((assignments.organization_id)::text = app.current_organization_id())))));


--
-- Name: SCHEMA app; Type: ACL; Schema: -; Owner: -
--

GRANT USAGE ON SCHEMA app TO azaeron_app;


--
-- Name: SCHEMA public; Type: ACL; Schema: -; Owner: -
--

GRANT USAGE ON SCHEMA public TO azaeron_app;


--
-- Name: TABLE aegis_edits; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.aegis_edits TO azaeron_app;


--
-- Name: TABLE alembic_version; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.alembic_version TO azaeron_app;


--
-- Name: TABLE analysis_runs; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.analysis_runs TO azaeron_app;


--
-- Name: TABLE api_keys; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.api_keys TO azaeron_app;


--
-- Name: TABLE assignments; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.assignments TO azaeron_app;


--
-- Name: TABLE audit_logs; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.audit_logs TO azaeron_app;


--
-- Name: TABLE authorship_profiles; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.authorship_profiles TO azaeron_app;


--
-- Name: TABLE authorship_signals; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.authorship_signals TO azaeron_app;


--
-- Name: TABLE billing_events; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.billing_events TO azaeron_app;


--
-- Name: TABLE citation_findings; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.citation_findings TO azaeron_app;


--
-- Name: TABLE citation_references; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.citation_references TO azaeron_app;


--
-- Name: TABLE citation_sources; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.citation_sources TO azaeron_app;


--
-- Name: TABLE citations; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.citations TO azaeron_app;


--
-- Name: TABLE claims; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.claims TO azaeron_app;


--
-- Name: TABLE compliance_reports; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.compliance_reports TO azaeron_app;


--
-- Name: TABLE detection_results; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.detection_results TO azaeron_app;


--
-- Name: TABLE detection_segments; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.detection_segments TO azaeron_app;


--
-- Name: TABLE document_chunks; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.document_chunks TO azaeron_app;


--
-- Name: TABLE document_versions; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.document_versions TO azaeron_app;


--
-- Name: TABLE documents; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.documents TO azaeron_app;


--
-- Name: TABLE evaluation_datasets; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.evaluation_datasets TO azaeron_app;


--
-- Name: TABLE evaluation_examples; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.evaluation_examples TO azaeron_app;


--
-- Name: TABLE evidence_edges; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.evidence_edges TO azaeron_app;


--
-- Name: TABLE evidence_nodes; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.evidence_nodes TO azaeron_app;


--
-- Name: TABLE integrity_reports; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.integrity_reports TO azaeron_app;


--
-- Name: TABLE jobs; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.jobs TO azaeron_app;


--
-- Name: TABLE memberships; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.memberships TO azaeron_app;


--
-- Name: TABLE model_registry; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.model_registry TO azaeron_app;


--
-- Name: TABLE organizations; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.organizations TO azaeron_app;


--
-- Name: TABLE processed_documents; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.processed_documents TO azaeron_app;


--
-- Name: TABLE provenance_events; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.provenance_events TO azaeron_app;


--
-- Name: TABLE provenance_exports; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.provenance_exports TO azaeron_app;


--
-- Name: TABLE provenance_reports; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.provenance_reports TO azaeron_app;


--
-- Name: TABLE refresh_tokens; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.refresh_tokens TO azaeron_app;


--
-- Name: TABLE similarity_analyses; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.similarity_analyses TO azaeron_app;


--
-- Name: TABLE similarity_index_entries; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.similarity_index_entries TO azaeron_app;


--
-- Name: TABLE similarity_matches; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.similarity_matches TO azaeron_app;


--
-- Name: TABLE submissions; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.submissions TO azaeron_app;


--
-- Name: TABLE users; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.users TO azaeron_app;


--
-- Name: DEFAULT PRIVILEGES FOR SEQUENCES; Type: DEFAULT ACL; Schema: public; Owner: -
--

ALTER DEFAULT PRIVILEGES FOR ROLE azaeron IN SCHEMA public GRANT ALL ON SEQUENCES TO azaeron_app;


--
-- Name: DEFAULT PRIVILEGES FOR TABLES; Type: DEFAULT ACL; Schema: public; Owner: -
--

ALTER DEFAULT PRIVILEGES FOR ROLE azaeron IN SCHEMA public GRANT SELECT,INSERT,DELETE,UPDATE ON TABLES TO azaeron_app;


--
-- PostgreSQL database dump complete
--

\unrestrict KRpyhOxorLyMmwjmn6pcfbQKTdkjhyJf2D7ogjOjgv3lC1hVhLjmUSZevN7V7om

