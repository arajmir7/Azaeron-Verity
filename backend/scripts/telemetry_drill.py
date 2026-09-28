"""Exercise actual prefork recycling and exported counters on an isolated worker."""

import json
import time
import httpx
from prometheus_client.parser import text_string_to_metric_families
from app.core.config import settings
from app.workers.celery_app import celery_app


def counter(name, **labels):
    body = httpx.get("http://celery-worker:9100/metrics", timeout=10).text
    return sum(
        sample.value
        for family in text_string_to_metric_families(body)
        for sample in family.samples
        if sample.name == name
        and all(sample.labels.get(k) == v for k, v in labels.items())
    )


def pids():
    stats = celery_app.control.inspect(timeout=5).stats()
    assert stats and len(stats) == 1, "Exactly one isolated worker required"
    return set(next(iter(stats.values()))["pool"]["processes"])


def main():
    assert settings.ENVIRONMENT == "development"
    before = pids()
    previous = counter(
        "azaeron_celery_tasks_total", task="failure_gate_sleep", state="SUCCESS"
    )
    jobs = [
        celery_app.send_task(
            "app.workers.tasks.failure_gate_sleep",
            args=[0.002],
            queue="document_processing",
        )
        for _ in range(120)
    ]
    for job in jobs:
        assert job.get(timeout=60) == "completed"
    for _ in range(30):
        measured = counter(
            "azaeron_celery_tasks_total", task="failure_gate_sleep", state="SUCCESS"
        )
        if measured >= previous + len(jobs):
            break
        time.sleep(1)
    assert measured == previous + len(jobs), (measured, previous)
    after = pids()
    assert before.isdisjoint(after), (before, after)
    print(
        json.dumps(
            {
                "result": "PASS",
                "delivered": len(jobs),
                "exported_success_increase": measured - previous,
                "both_prefork_children_recycled": True,
                "counter_preserved_across_recycle": True,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
