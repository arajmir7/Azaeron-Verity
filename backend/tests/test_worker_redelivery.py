"""Terminal delivery must survive storage relocation without rerunning work."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.jobs.models import JobStatus
from app.workers import tasks


@pytest.mark.parametrize(
    "status", [JobStatus.COMPLETED, JobStatus.CANCELLED, JobStatus.FAILED]
)
def test_terminal_job_redelivery_after_relocation(monkeypatch, status):
    class Session:
        bind = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    session = Session()
    monkeypatch.setattr(tasks, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(tasks, "_run_with_job_lock", lambda job, action: action())
    job = SimpleNamespace(
        status=status, input_data={"storage_key": "versions/legacy/new.txt"}
    )
    monkeypatch.setattr(tasks.JobService, "get_job", AsyncMock(return_value=job))
    target = AsyncMock(
        side_effect=AssertionError("Terminal jobs must not reopen storage")
    )
    monkeypatch.setattr(tasks.AnalysisTarget, "resolve", target)
    tasks.process_document.run("job", "doc", "uploads/old.txt", "org", "version")
    target.assert_not_called()
    assert job.status == status


def test_delivery_before_transaction_commit_retries(monkeypatch):
    class Session:
        bind = None
        rollback = AsyncMock()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr(tasks, "AsyncSessionLocal", Session)
    monkeypatch.setattr(tasks, "_run_with_job_lock", lambda job, action: action())
    monkeypatch.setattr(tasks.JobService, "get_job", AsyncMock(return_value=None))

    class RetryExpected(Exception):
        pass

    def retry(**kwargs):
        assert kwargs["countdown"] == 2
        raise RetryExpected()

    monkeypatch.setattr(tasks.process_document, "retry", retry)
    with pytest.raises(RetryExpected):
        tasks.process_document.run(
            "job", "doc", "uploads/fixture.txt", "org", "version"
        )
