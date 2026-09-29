"""Bounded agent metrics without actor IDs, prompts or document content."""

from prometheus_client import Histogram, Counter

QUEUE_WAIT = Histogram(
    "azaeron_agent_queue_wait_seconds",
    "Admission to worker start.",
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 180),
)
FIRST_TOKEN = Histogram(
    "azaeron_agent_first_token_seconds",
    "Worker start to first actual runtime token.",
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60),
)
RUN_DURATION = Histogram(
    "azaeron_agent_duration_seconds",
    "Complete agent execution duration.",
    ("outcome",),
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 180),
)
TOOL_DURATION = Histogram(
    "azaeron_agent_tool_seconds",
    "Internal tool duration.",
    ("tool",),
    buckets=(0.01, 0.1, 0.5, 1, 2, 5, 10, 30, 60, 120),
)
TOKENS = Counter(
    "azaeron_agent_tokens_total",
    "Reported runtime tokens on settled runs.",
    ("direction",),
)
FAILURES = Counter(
    "azaeron_agent_failures_total",
    "Terminal unavailable or failed agent runs.",
    ("status",),
)
