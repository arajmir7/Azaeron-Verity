"""AZAERON application configuration."""

from urllib.parse import urlsplit
import os

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator, model_validator
import secrets


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    APP_NAME: str = "AZAERON VERITY"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    # `DEBUG` is commonly injected by shells/CI with non-boolean values.  Keep
    # the application setting namespaced and accept the legacy name only when it
    # is a real boolean.
    DEBUG: bool = Field(default=False, validation_alias="AZAERON_DEBUG")
    LOG_LEVEL: str = "INFO"
    ZERO_EXTERNAL_AI_API: bool = True
    INFERENCE_ENABLED: bool = False
    MODEL_REGISTRY_PATH: str = "/etc/azaeron/models/registry.json"
    INFERENCE_ENDPOINT: str = "https://inference-runtime:8000"
    INFERENCE_VERIFY_ENDPOINT: str = "https://verification-runtime:8000"
    INFERENCE_MODEL_ENDPOINTS: dict[str, str] = {}
    IDENTITY_ENCRYPTION_KEY: str | None = None
    USAGE_ENCRYPTION_KEY: str | None = None
    EMAIL_ENABLED: bool = False
    EMAIL_PUBLIC_URL: str = "http://localhost:3000"
    SMTP_HOST: str = "mailpit"
    SMTP_PORT: int = 1025
    SMTP_FROM: str = "security@azaeron.local"
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_STARTTLS: bool = True
    INFERENCE_CA_FILE: str | None = None
    INFERENCE_CERT_FILE: str | None = None
    INFERENCE_KEY_FILE: str | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_external_ai_configuration(cls, values):
        # Check legacy/unknown environment settings too: extra='ignore' must
        # never silently accept a hosted inference endpoint or credential.
        prohibited = {
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "OPENAI_API_BASE",
            "AZURE_OPENAI_API_KEY",
            "AZURE_OPENAI_ENDPOINT",
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_BASE_URL",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "MISTRAL_API_KEY",
            "COHERE_API_KEY",
            "GROQ_API_KEY",
            "TOGETHER_API_KEY",
            "FIREWORKS_API_KEY",
            "OPENROUTER_API_KEY",
            "HF_INFERENCE_ENDPOINT",
            "HUGGINGFACEHUB_API_TOKEN",
            "EMBEDDING_API_URL",
            "RERANK_API_URL",
            "DETECTOR_API_URL",
            "HUMANIZER_API_URL",
        }
        supplied = dict(os.environ)
        supplied.update(values)
        configured = sorted(key for key in prohibited if supplied.get(key))
        if configured:
            raise ValueError(
                "External AI configuration is prohibited: " + ", ".join(configured)
            )
        return values

    # Security
    SECRET_KEY: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    REFRESH_SECRET_KEY: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    PASSWORD_MIN_LENGTH: int = 12
    PASSWORD_HASH_ALGORITHM: str = "bcrypt"

    # Database
    DATABASE_URL: str = (
        "postgresql+asyncpg://azaeron:azaeron_dev_password@localhost:5432/azaeron"
    )
    # Used only by Alembic in deployment. Runtime services must use the
    # non-superuser DATABASE_URL account so PostgreSQL RLS is enforceable.
    MIGRATION_DATABASE_URL: str | None = None
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_POOL_RECYCLE: int = 3600
    DATABASE_POOL_TIMEOUT_SECONDS: int = 10
    DATABASE_CONNECT_TIMEOUT_SECONDS: int = 5
    DATABASE_COMMAND_TIMEOUT_SECONDS: int = 30

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CONNECT_TIMEOUT_SECONDS: int = 2
    REDIS_SOCKET_TIMEOUT_SECONDS: int = 2

    # Object Storage
    MINIO_ENDPOINT: str = "localhost:9000"
    # Optional browser-reachable endpoint for presigned URLs. Keep the
    # service-to-service endpoint private inside the Docker/network boundary.
    MINIO_PUBLIC_ENDPOINT: str | None = None
    MINIO_REGION: str = "us-east-1"
    MINIO_ACCESS_KEY: str = "azaeronminio"
    MINIO_SECRET_KEY: str = "azaeronminio123"
    MINIO_BUCKET: str = "azaeron-documents"
    MINIO_SECURE: bool = False
    # Worker-only principal. API/upload credentials cannot erase objects.
    PRIVACY_MINIO_ACCESS_KEY: str | None = None
    PRIVACY_MINIO_SECRET_KEY: str | None = None
    MAX_UPLOAD_SIZE_MB: int = 100
    MAX_DOCUMENT_TEXT_CHARS: int = 2_000_000
    MAX_DOCUMENT_PAGES: int = 500
    MAX_DOCX_UNCOMPRESSED_MB: int = 200

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000"
    TRUSTED_HOSTS: str = "localhost,127.0.0.1,testserver"
    COOKIE_SECURE: bool | None = None
    COOKIE_DOMAIN: str | None = None

    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    METRICS_TOKEN: str | None = None

    # Operations
    HEALTHCHECK_TIMEOUT_SECONDS: int = 5
    WORKER_HEALTH_TIMEOUT_SECONDS: int = 5
    WORKER_HEARTBEAT_TTL_SECONDS: int = 30
    WORKER_HEARTBEAT_KEY_PREFIX: str = "azaeron:worker:heartbeat"
    READINESS_REQUIRE_WORKER: bool = False
    RELEASE_ID: str = Field(
        default="development",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9._-]+$",
    )
    OTEL_SERVICE_NAME: str = "azaeron-api"
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = None
    OTEL_EXPORTER_OTLP_INSECURE: bool = True
    OTEL_EXPORTER_OTLP_TIMEOUT_SECONDS: int = 5
    OTEL_TRACE_SAMPLE_RATIO: float = Field(default=1.0, ge=0, le=1)
    CELERY_TASK_TIME_LIMIT_SECONDS: int = 900
    CELERY_TASK_SOFT_TIME_LIMIT_SECONDS: int = 840
    CELERY_MAX_RETRY_BACKOFF_SECONDS: int = 300
    CELERY_RETRY_BACKOFF_BASE_SECONDS: int = 30
    DEAD_LETTER_QUEUE_KEY: str = "azaeron:dead-letter:document-processing"
    DEAD_LETTER_QUEUE_TTL_SECONDS: int = 2_592_000

    # File Validation
    ALLOWED_EXTENSIONS: str = ".pdf,.docx,.txt,.md,.html"
    ALLOWED_MIME_TYPES: str = (
        "application/pdf,"
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
        "text/plain,"
        "text/markdown,"
        "text/html"
    )

    # ML / Detection
    DETECTION_CONFIDENCE_THRESHOLD: float = 0.6
    MIN_DOCUMENT_LENGTH_FOR_ANALYSIS: int = 50

    # Audit
    AUDIT_LOG_RETENTION_DAYS: int = 365

    # Vector Search
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    VECTOR_DIMENSION: int = 384
    SIMILARITY_MODEL_PATH: str = "model_assets/all-MiniLM-L6-v2"

    @field_validator("CORS_ORIGINS")
    @classmethod
    def parse_cors_origins(cls, v):
        return [origin.strip() for origin in v.split(",")]

    @field_validator("TRUSTED_HOSTS")
    @classmethod
    def parse_trusted_hosts(cls, v):
        return [host.strip() for host in v.split(",")]

    @field_validator("ALLOWED_EXTENSIONS")
    @classmethod
    def parse_extensions(cls, v):
        return [ext.strip().lower() for ext in v.split(",")]

    @field_validator("ALLOWED_MIME_TYPES")
    @classmethod
    def parse_mime_types(cls, v):
        return [mt.strip().lower() for mt in v.split(",")]

    @property
    def cookie_secure(self) -> bool:
        return (
            self.ENVIRONMENT == "production"
            if self.COOKIE_SECURE is None
            else self.COOKIE_SECURE
        )

    @model_validator(mode="after")
    def validate_production_secrets(self):
        if not self.ZERO_EXTERNAL_AI_API:
            raise ValueError("ZERO_EXTERNAL_AI_API must remain true")
        insecure = (
            "azaeron-super-secret-key",
            "azaeron-refresh-secret-key",
            "change-me",
        )
        if self.ENVIRONMENT == "production":
            if self.DEBUG:
                raise ValueError("Production must disable debug logging")
            required = {"SECRET_KEY", "REFRESH_SECRET_KEY"}
            if not required.issubset(self.model_fields_set):
                raise ValueError(
                    "Production requires explicitly supplied SECRET_KEY and REFRESH_SECRET_KEY"
                )
            if (
                len(self.SECRET_KEY) < 32
                or len(self.REFRESH_SECRET_KEY) < 32
                or any(
                    value.startswith(insecure)
                    for value in (self.SECRET_KEY, self.REFRESH_SECRET_KEY)
                )
            ):
                raise ValueError(
                    "Production requires independently generated SECRET_KEY and REFRESH_SECRET_KEY"
                )
            if self.SECRET_KEY == self.REFRESH_SECRET_KEY:
                raise ValueError("Production access and refresh secrets must differ")
            if not self.cookie_secure:
                raise ValueError("Production requires secure authentication cookies")
            if not self.MINIO_SECURE:
                raise ValueError("Production requires TLS for object storage")
            if os.getenv("CELERY_WORKER", "").lower() == "true" and (
                not self.PRIVACY_MINIO_ACCESS_KEY
                or not self.PRIVACY_MINIO_SECRET_KEY
                or len(self.PRIVACY_MINIO_SECRET_KEY) < 32
                or self.PRIVACY_MINIO_ACCESS_KEY == self.MINIO_ACCESS_KEY
            ):
                raise ValueError(
                    "Production workers require independent storage maintenance credentials"
                )
            if not self.MINIO_PUBLIC_ENDPOINT:
                raise ValueError(
                    "Production requires a browser-reachable object-storage endpoint"
                )
            if any(
                origin == "*" or not origin.startswith("https://")
                for origin in self.CORS_ORIGINS
            ):
                raise ValueError(
                    "Production CORS origins must be explicit HTTPS origins"
                )
            if any(host == "*" for host in self.TRUSTED_HOSTS):
                raise ValueError("Production trusted hosts must be explicit")
            if self.MINIO_ACCESS_KEY in {
                "azaeronminio",
                "azaeronapp",
            } or self.MINIO_SECRET_KEY in {"azaeronminio123", "azaeronapp123"}:
                raise ValueError(
                    "Production requires non-default object-storage credentials"
                )
            if not self.METRICS_TOKEN or len(self.METRICS_TOKEN) < 32:
                raise ValueError("Production requires a dedicated metrics bearer token")
            if not self.OTEL_EXPORTER_OTLP_ENDPOINT:
                raise ValueError("Production requires an OTLP tracing endpoint")
            if not self.READINESS_REQUIRE_WORKER:
                raise ValueError("Production readiness must verify worker health")
            database_user = urlsplit(self.DATABASE_URL).username
            if database_user != "azaeron_app":
                raise ValueError(
                    "Production runtime DATABASE_URL must use the non-owner azaeron_app role"
                )
            database_password = urlsplit(self.DATABASE_URL).password
            if not database_password or database_password in {
                "azaeron_app_dev_password",
                "change-me",
                "azaeron_dev_password",
            }:
                raise ValueError(
                    "Production runtime DATABASE_URL requires a non-default database password"
                )
        return self

    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=True, extra="ignore", hide_input_in_errors=True
    )


settings = Settings()
